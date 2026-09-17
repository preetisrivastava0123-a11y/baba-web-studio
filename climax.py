# -*- coding: utf-8 -*-
"""
climax.py - Baba Web Studio  |  v3 "Particle Drone Show"
========================================================

Zero external image assets. The Lord Shiva figure is generated from pure
vector math at runtime (trishul + crescent moon + damru + coiled snake with
flared hood), sampled into ~2600 glowing particles that start dispersed
across the canvas and swirl into formation during the first ~2 seconds.

Sequence
--------
    0.0 - 2.0s   particles converge from dispersion into the Shiva outline
    2.0s +       divine aura: multi-coloured rays + expanding light rings
                 radiating outward, hues cycling gold -> neon blue -> fiery
                 orange, with a rainbow sweep running through the figure
    throughout   fire sparks streaming from the snake hood toward the viewer,
                 fireworks bursts synced to the audio booms
    lower third  metallic red SUBSCRIBE button + bell + Devanagari CTA

DEVANAGARI SAFETY NOTE  (do not "optimise" this away)
-----------------------------------------------------
PIL's ``stroke_width=`` runs FreeType's outline stroker on the *shaped glyph
outline*. On conjuncts like "स्क्रा" that stroker fuses the half-form with the
following consonant, so "सब्सक्राइब" renders as "सब्सत्राइब" — at ANY stroke
width, thin included. Confirmed on the two-line wrapped CTA.

So this module NEVER passes stroke_width to draw.text(). The glyph mask is
drawn exactly once, fill only. All rim / outline / shadow look is rebuilt
afterwards from a GAUSSIAN BLUR of that finished bitmap, composited UNDER it.
Blurring a finished bitmap cannot change glyph topology, so shaping is
guaranteed identical to the plain render. ``assert_glyph_mask_untouched()``
proves it numerically.

Public API (backwards compatible)
---------------------------------
    generate_climax(duration, cta_text, watermark_path, target_size,
                    is_draft=True, motif_path=None, with_audio=True,
                    show_subscribe=True, seed=None) -> VideoClip

Self-contained: does not import engine.py.
Deps: numpy, opencv-python, Pillow, moviepy==1.0.3
"""

import os
import re
import sys
import math
import wave
import atexit
import tempfile
import uuid

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

from moviepy.editor import VideoClip, AudioFileClip

__all__ = [
    "generate_climax",
    "build_shiva_mask",
    "render_devanagari_text_image",
    "assert_glyph_mask_untouched",
]

# --------------------------------------------------------------------------
# PALETTE / CONSTANTS
# --------------------------------------------------------------------------
BG_TOP = (10, 5, 28)
BG_MID = (34, 8, 52)
BG_BOTTOM = (66, 14, 40)

CTA_TEXT_COLOR = (255, 214, 92)
CTA_RIM_COLOR = (150, 74, 12)
CTA_SHADOW_COLOR = (0, 0, 0)

SUBSCRIBE_RED = (229, 9, 20)
SUBSCRIBE_RED_HI = (255, 62, 62)
SUBSCRIBE_TEXT = (255, 255, 255)
BELL_COLOR = (255, 255, 255)

# divine hue cycle: gold -> neon blue -> fiery orange -> violet  (HSV degrees)
DIVINE_HUES = [45.0, 196.0, 22.0, 280.0, 45.0]

FIREWORK_PALETTE = [
    (255, 96, 72), (255, 196, 66), (120, 226, 255),
    (168, 255, 132), (255, 128, 226), (255, 255, 236),
]
FLAME_PALETTE = [
    (255, 246, 214), (255, 206, 96), (255, 142, 34),
    (255, 86, 24), (214, 40, 18), (255, 170, 60),
]

GRAVITY = 260.0
SPARK_DRAG = 1.35
FORM_TIME = 2.0          # seconds for the drone formation

# The channel's standard sign-off line. The emoji render as the hand-drawn
# icons in _EMOJI_ICONS above (not font glyphs), and are stripped out again
# automatically for whichever TTS backend speaks it - see _strip_for_speech.
DEFAULT_CTA_TEXT = (
    "\u2728 वीडियो देखने के लिए धन्यवाद! \u2728 "
    "\U0001F44D चैनल को लाइक और सब्सक्राइब करें। \U0001F514 "
    "\U0001F64F कमेंट में 'हर हर महादेव' जरूर लिखें! \U0001F549\ufe0f "
    "\U0001F338 आपका दिन शुभ हो! \U0001F33A"
)

DESIGN_W, DESIGN_H = 1000, 1400   # Shiva vector design space

_DEVANAGARI_FONT_CANDIDATES = [
    "C:\\Windows\\Fonts\\Nirmala.ttf",
    "C:\\Windows\\Fonts\\NirmalaB.ttf",
    "C:\\Windows\\Fonts\\Mangal.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    "/usr/share/fonts/truetype/samyak-fonts/Samyak-Devanagari.ttf",
]
_LATIN_BOLD_FONT_CANDIDATES = [
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "C:\\Windows\\Fonts\\segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

_TEMP_FILES = []


def _register_temp(path):
    _TEMP_FILES.append(path)
    return path


@atexit.register
def _cleanup_temp():
    for p in _TEMP_FILES:
        try:
            os.remove(p)
        except Exception:
            pass


# ==========================================================================
# 1. SHIVA VECTOR GEOMETRY  (pure math - no PNG, no external asset)
# ==========================================================================
def _bezier(p0, p1, p2, n=70):
    t = np.linspace(0.0, 1.0, n)[:, None]
    p0 = np.array(p0, np.float32)
    p1 = np.array(p1, np.float32)
    p2 = np.array(p2, np.float32)
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2


def _stroke(mask, pts, thickness, val=255):
    cv2.polylines(mask, [np.round(np.array(pts)).astype(np.int32)],
                  False, val, max(1, int(thickness)), cv2.LINE_AA)


HOOD_CENTER_DESIGN = (742.0, 512.0)
HOOD_RADIUS_DESIGN = 165.0


def build_shiva_mask():
    """
    Rasterise the Shiva composition into a DESIGN_H x DESIGN_W uint8 mask,
    entirely from parametric curves and polygons:
        * trishul  - shaft, crossbar, centre spear, two outward-curving prongs
        * crescent moon (chandra) - circle difference
        * damru - two opposed triangles + waist band + bead string
        * snake - sinusoidal coil around the shaft, flared cobra hood, head
    """
    m = np.zeros((DESIGN_H, DESIGN_W), np.uint8)

    # ---- trishul ----
    _stroke(m, [(500, 330), (500, 1360)], 20)          # shaft
    _stroke(m, [(348, 330), (652, 330)], 18)           # crossbar
    _stroke(m, [(500, 330), (500, 170)], 16)           # centre stem
    cv2.fillPoly(m, [np.array([[474, 215], [500, 52], [526, 215]], np.int32)], 255)
    for s in (-1, 1):
        curve = _bezier((500 + s * 152, 332), (500 + s * 236, 232), (500 + s * 205, 120))
        _stroke(m, curve, 15)
        tx, ty = float(curve[-1][0]), float(curve[-1][1])
        cv2.fillPoly(m, [np.array([[tx - 26, ty + 10],
                                   [tx, ty - 108],
                                   [tx + 26, ty + 10]], np.int32)], 255)

    # ---- crescent moon ----
    moon = np.zeros_like(m)
    cv2.circle(moon, (178, 190), 84, 255, -1)
    cv2.circle(moon, (222, 162), 79, 0, -1)
    m = np.maximum(m, moon)

    # ---- damru ----
    cv2.fillPoly(m, [np.array([[702, 850], [878, 850], [790, 958]], np.int32)], 255)
    cv2.fillPoly(m, [np.array([[702, 1066], [878, 1066], [790, 958]], np.int32)], 255)
    _stroke(m, [(750, 958), (830, 958)], 18)
    _stroke(m, [(790, 1066), (812, 1126)], 7)
    cv2.circle(m, (812, 1131), 13, 255, -1)

    # ---- snake: sinusoidal coil around the shaft ----
    u = np.linspace(0.0, 1.0, 260)
    body = np.stack([500 + 140 * np.sin(u * 2.35 * math.pi), 1350 - 770 * u], axis=1)
    for i in range(len(body) - 1):
        _stroke(m, [body[i], body[i + 1]], round(30 - 19 * (i / len(body)) ** 0.8))
    neck = _bezier(body[-1], (body[-1][0] + 90, body[-1][1] - 90), (742, 612), 40)
    for i in range(len(neck) - 1):
        _stroke(m, [neck[i], neck[i + 1]], max(9, int(13 - 3 * i / len(neck))))

    hx, hy = int(HOOD_CENTER_DESIGN[0]), int(HOOD_CENTER_DESIGN[1])
    hood = np.zeros_like(m)
    cv2.ellipse(hood, (hx, hy), (132, 98), 0, 0, 360, 255, -1)          # flared hood
    cv2.fillPoly(hood, [np.array([[hx - 78, hy + 52], [hx + 78, hy + 52],
                                  [hx + 26, hy + 118], [hx - 26, hy + 118]], np.int32)], 255)
    cv2.ellipse(hood, (hx, hy - 86), (50, 44), 0, 0, 360, 255, -1)      # head
    m = np.maximum(m, hood)
    cv2.circle(m, (hx - 19, hy - 96), 8, 0, -1)                          # eyes
    cv2.circle(m, (hx + 19, hy - 96), 8, 0, -1)

    return m


def _resample_contour(pts, n):
    """Arc-length resampling so outline particles are evenly spaced."""
    pts = pts.astype(np.float32)
    if len(pts) < 2 or n <= 0:
        return np.repeat(pts[:1] if len(pts) else np.zeros((1, 2), np.float32),
                         max(1, n), axis=0)
    closed = np.vstack([pts, pts[:1]])
    seg = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    if total <= 0:
        return np.repeat(pts[:1], n, axis=0)
    want = np.linspace(0.0, total, n, endpoint=False)
    idx = np.clip(np.searchsorted(cum, want, side="right") - 1, 0, len(seg) - 1)
    frac = ((want - cum[idx]) / np.maximum(seg[idx], 1e-6))[:, None]
    return closed[idx] + (closed[idx + 1] - closed[idx]) * frac


def build_shiva_particles(n_particles, w, h, fig_h, center_xy, rng):
    """
    Sample the vector figure into particle home coordinates.

    ~72% sit on the contour (crisp drone-show outline), ~28% fill the
    interior at lower brightness so the silhouette reads as solid light.
    """
    mask = build_shiva_mask()
    scale = fig_h / float(DESIGN_H)

    n_out = int(n_particles * 0.72)
    n_fill = max(0, n_particles - n_out)

    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    contours = [c.reshape(-1, 2) for c in contours if len(c) >= 8]
    if not contours:
        raise RuntimeError("shiva mask produced no contours")
    lengths = np.array([cv2.arcLength(c.reshape(-1, 1, 2).astype(np.int32), True)
                        for c in contours], np.float64)
    share = np.maximum(1, np.round(lengths / lengths.sum() * n_out).astype(int))

    out_pts = np.concatenate([_resample_contour(c, int(k))
                              for c, k in zip(contours, share)], axis=0)[:n_out]
    # sub-pixel jitter so the outline does not look like a printed stroke
    out_pts = out_pts + rng.normal(0, 1.6, out_pts.shape).astype(np.float32)

    ys, xs = np.nonzero(cv2.erode(mask, np.ones((7, 7), np.uint8)))
    if len(xs) and n_fill:
        pick = rng.integers(0, len(xs), n_fill)
        fill_pts = np.stack([xs[pick], ys[pick]], 1).astype(np.float32)
        fill_pts += rng.normal(0, 2.0, fill_pts.shape).astype(np.float32)
    else:
        fill_pts = np.zeros((0, 2), np.float32)

    pts = np.concatenate([out_pts, fill_pts], axis=0).astype(np.float32)
    is_outline = np.concatenate([np.ones(len(out_pts), bool),
                                 np.zeros(len(fill_pts), bool)])

    cx, cy = center_xy
    home = np.empty_like(pts)
    home[:, 0] = cx + (pts[:, 0] - DESIGN_W * 0.5) * scale
    home[:, 1] = cy + (pts[:, 1] - DESIGN_H * 0.5) * scale

    hood_cx = cx + (HOOD_CENTER_DESIGN[0] - DESIGN_W * 0.5) * scale
    hood_cy = cy + (HOOD_CENTER_DESIGN[1] - DESIGN_H * 0.5) * scale

    return dict(home=home, is_outline=is_outline,
                hood_center=(hood_cx, hood_cy),
                hood_radius=HOOD_RADIUS_DESIGN * scale,
                center=(float(cx), float(cy)), scale=scale)


def build_mandala_particles(n_particles, w, h, radius, center_xy, rng):
    """
    Particle homes for the motif mode: concentric lotus/mandala rings that sit
    ENTIRELY OUTSIDE the motif radius, so the drone layer frames the artwork
    instead of covering its face. Rose curves r = R(1 + a*cos(k*theta)).
    """
    cx, cy = center_xy
    rings = [
        (1.06, 0.00, 0,  0.20),   # (radius factor, petal amp, petal count, share)
        (1.26, 0.13, 12, 0.28),
        (1.55, 0.19, 8,  0.30),
        (1.86, 0.09, 24, 0.22),
    ]
    homes, outline = [], []
    for rf, amp, k, share in rings:
        cnt = max(8, int(n_particles * share))
        th = np.linspace(0, 2 * math.pi, cnt, endpoint=False)
        th = th + rng.uniform(0, 2 * math.pi)
        rr = radius * rf * (1.0 + amp * np.cos(k * th)) if k else np.full(cnt, radius * rf)
        jitter = rng.normal(0, radius * 0.012, cnt)
        homes.append(np.stack([cx + np.cos(th) * (rr + jitter),
                               cy + np.sin(th) * (rr + jitter) * 0.94], 1))
        outline.append(np.ones(cnt, bool))

    home = np.concatenate(homes, 0).astype(np.float32)
    return dict(home=home,
                is_outline=np.concatenate(outline),
                hood_center=(float(cx), float(cy)),
                hood_radius=float(radius),
                center=(float(cx), float(cy)),
                scale=radius / max(1.0, HOOD_RADIUS_DESIGN))


def build_formation(field, w, h, rng):
    """Dispersed start positions + swirl parameters for the convergence."""
    n = len(field["home"])
    cx, cy = field["center"]
    home = field["home"]

    ang = rng.uniform(0, 2 * math.pi, n)
    rad = np.sqrt(rng.uniform(0.18, 1.0, n)) * math.hypot(w, h) * 0.60
    start = np.stack([cx + np.cos(ang) * rad,
                      cy + np.sin(ang) * rad * 0.85], 1).astype(np.float32)

    r0 = np.hypot(start[:, 0] - cx, start[:, 1] - cy)
    a0 = np.arctan2(start[:, 1] - cy, start[:, 0] - cx)
    r1 = np.hypot(home[:, 0] - cx, home[:, 1] - cy)
    a1 = np.arctan2(home[:, 1] - cy, home[:, 0] - cx)
    da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi

    span = max(1.0, float(home[:, 1].max() - home[:, 1].min()))
    field.update(
        start=start,
        r0=r0.astype(np.float32), a0=a0.astype(np.float32),
        r1=r1.astype(np.float32), da=da.astype(np.float32),
        swirl=(rng.uniform(0.8, 2.2, n) * rng.choice([-1.0, 1.0], n)).astype(np.float32),
        delay=rng.uniform(0.0, 0.55, n).astype(np.float32),
        speed=rng.uniform(0.85, 1.25, n).astype(np.float32),
        hue_off=rng.uniform(0, 360, n).astype(np.float32),
        wave=((home[:, 1] - home[:, 1].min()) / span).astype(np.float32),
        twinkle=rng.uniform(0, 2 * math.pi, n).astype(np.float32),
        orbit_r=rng.uniform(1.0, 4.5, n).astype(np.float32),
        orbit_f=rng.uniform(0.5, 1.6, n).astype(np.float32),
        orbit_p=rng.uniform(0, 2 * math.pi, n).astype(np.float32),
    )
    return field


def _particle_positions(field, t):
    """Vectorised position + formation progress for every particle at time t."""
    k = np.clip((t - field["delay"]) * field["speed"] /
                max(0.2, FORM_TIME - 0.55), 0.0, 1.0)
    e = (k * k * (3.0 - 2.0 * k)) ** 0.85        # eased smoothstep

    cx, cy = field["center"]
    r = field["r0"] + (field["r1"] - field["r0"]) * e
    a = field["a0"] + field["da"] * e + field["swirl"] * (1.0 - e) ** 2
    x = cx + np.cos(a) * r
    y = cy + np.sin(a) * r

    settled = k >= 1.0
    if settled.any():
        ph = t * field["orbit_f"] * 2.0 + field["orbit_p"]
        x = np.where(settled, field["home"][:, 0] + np.cos(ph) * field["orbit_r"], x)
        y = np.where(settled, field["home"][:, 1] + np.sin(ph) * field["orbit_r"], y)
    return x, y, e


def _particle_colors(field, t, formed):
    """
    Hue = slow gold->neon-blue->orange->violet cycle, plus a rainbow wave
    sweeping down the figure, plus a per-particle offset. Vectorised HSV->RGB.
    """
    n = len(field["home"])
    pos = (t * 0.32) % (len(DIVINE_HUES) - 1)
    i = int(pos)
    base = DIVINE_HUES[i] + (DIVINE_HUES[i + 1] - DIVINE_HUES[i]) * (pos - i)

    hue = (base + 190.0 * np.sin(field["wave"] * 3.4 - t * 1.5)
           + field["hue_off"] * 0.22) % 360.0
    sat = np.where(field["is_outline"], 0.62, 0.80).astype(np.float32) * (0.55 + 0.45 * formed)
    val = (np.where(field["is_outline"], 1.0, 0.72).astype(np.float32)
           * (0.70 + 0.30 * np.sin(t * 5.0 + field["twinkle"])))

    hsv = np.empty((1, n, 3), np.float32)
    hsv[0, :, 0] = hue
    hsv[0, :, 1] = np.clip(sat, 0, 1)
    hsv[0, :, 2] = np.clip(val, 0, 1)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[0] * 255.0


# ==========================================================================
# 2. DIVINE AURA RAYS  (multi-coloured, expanding)
# ==========================================================================
class _AuraField(object):
    """Precomputed polar grids so the per-frame ray maths is pure numpy."""

    def __init__(self, pw, ph, cx, cy, n_rays=18):
        yy, xx = np.mgrid[0:ph, 0:pw].astype(np.float32)
        dx, dy = xx - cx, yy - cy
        self.r = np.sqrt(dx * dx + dy * dy)
        self.theta = np.arctan2(dy, dx)
        self.theta_deg = (np.degrees(self.theta) + 360.0) % 360.0
        self.n_rays = max(4, int(n_rays))
        self.rmax = float(max(1.0, self.r.max()))
        self.hsv = np.empty((ph, pw, 3), np.float32)

    def render(self, t, gain=1.0):
        fan = (0.5 + 0.5 * np.cos(self.n_rays * self.theta + t * 0.85)) ** 3.0
        fan2 = (0.5 + 0.5 * np.cos((self.n_rays // 2 + 1) * self.theta - t * 1.35)) ** 4.0
        rays = fan * 0.75 + fan2 * 0.45

        rn = self.r / self.rmax
        falloff = np.clip(1.0 - rn, 0, 1) ** 1.9
        core = np.exp(-(rn * 5.5) ** 2) * 0.9

        ring = np.zeros_like(rn)
        for k in range(3):
            phase = (t * 0.34 + k / 3.0) % 1.0
            ring += np.exp(-((rn - phase) ** 2) / 0.0035) * (1.0 - phase) * 0.75

        inten = np.clip((rays * falloff + core + ring) * gain, 0, 2.6)

        # hue follows angle + time -> many colours radiating at once
        self.hsv[..., 0] = (self.theta_deg * 1.6 + t * 55.0) % 360.0
        self.hsv[..., 1] = np.clip(0.30 + 0.55 * (1.0 - falloff), 0, 1)
        self.hsv[..., 2] = np.clip(inten, 0, 1)
        return cv2.cvtColor(self.hsv, cv2.COLOR_HSV2RGB) * (inten[..., None] * 46.0)


# ==========================================================================
# 3. FIRE / SPARK / FIREWORK FIELDS
# ==========================================================================
def _build_snake_fire(n, hood_center, hood_radius, rng, r_lo=0.55, r_hi=1.0):
    """High-velocity fire sparks streaming out of the hood toward the viewer."""
    return dict(
        ang=rng.uniform(-0.65, math.pi + 0.65, n).astype(np.float32),
        r0=(hood_radius * rng.uniform(r_lo, r_hi, n)).astype(np.float32),
        acc=rng.uniform(260, 780, n).astype(np.float32),
        vy=rng.uniform(-40, 130, n).astype(np.float32),
        life=rng.uniform(0.55, 1.5, n).astype(np.float32),
        off=rng.uniform(0, 3.0, n).astype(np.float32),
        wob=rng.uniform(8, 34, n).astype(np.float32),
        wfq=rng.uniform(2.5, 7.0, n).astype(np.float32),
        col=np.array([FLAME_PALETTE[i] for i in
                      rng.integers(0, len(FLAME_PALETTE), n)], np.float32),
        cx=float(hood_center[0]), cy=float(hood_center[1]),
    )


def _build_fireworks(duration, w, h, n_bursts, sparks_per, rng, avoid=None):
    scale = w / 1080.0
    t0, x0, y0, vx, vy, life, col, siz = [], [], [], [], [], [], [], []
    burst_times = []
    for i in range(n_bursts):
        span = max(0.6, duration - FORM_TIME - 0.8)
        bt = FORM_TIME + 0.15 + span * (i + rng.uniform(0.15, 0.85)) / max(1, n_bursts)
        burst_times.append(float(bt))
        if avoid is None:
            bx = rng.uniform(w * 0.10, w * 0.90)
            by = rng.uniform(h * 0.06, h * 0.42)
        else:
            # place on an annulus around the figure so a burst can never
            # detonate on top of it (a retry loop can and did give up)
            ax, ay, ar = avoid
            a_ = rng.uniform(0, 2 * math.pi)
            rr = ar * rng.uniform(1.10, 1.95)
            bx = min(max(ax + math.cos(a_) * rr, w * 0.08), w * 0.92)
            by = min(max(ay + math.sin(a_) * rr * 0.75, h * 0.05), h * 0.62)
            if math.hypot(bx - ax, by - ay) < ar:      # clamped back inside
                bx = w * 0.08 if bx < ax else w * 0.92
                by = min(max(ay + math.copysign(ar * 1.1, math.sin(a_)),
                             h * 0.05), h * 0.62)
        base = np.array(FIREWORK_PALETTE[rng.integers(0, len(FIREWORK_PALETTE))], np.float32)
        n = int(sparks_per * rng.uniform(0.8, 1.25))
        ang = rng.uniform(0, 2 * math.pi, n)
        vmax = rng.uniform(430, 700) * scale
        shell = rng.random(n) < 0.55
        spd = np.where(shell, rng.uniform(0.74, 1.0, n),
                       np.sqrt(rng.uniform(0.04, 0.74, n))) * vmax
        squash = rng.uniform(0.82, 1.0)

        t0.append(np.full(n, bt, np.float32))
        x0.append(np.full(n, bx, np.float32))
        y0.append(np.full(n, by, np.float32))
        vx.append((np.cos(ang) * spd).astype(np.float32))
        vy.append((np.sin(ang) * spd * squash).astype(np.float32))
        life.append(rng.uniform(1.15, 1.95, n).astype(np.float32))
        col.append(np.clip(base[None, :] * rng.uniform(0.72, 1.28, (n, 1)),
                           0, 255).astype(np.float32))
        siz.append(rng.uniform(0.7, 1.9, n).astype(np.float32))

    if not t0:
        e = np.zeros(0, np.float32)
        return dict(t0=e, x0=e, y0=e, vx=e, vy=e, life=e, siz=e, phase=e,
                    col=np.zeros((0, 3), np.float32)), []

    fw = dict(t0=np.concatenate(t0), x0=np.concatenate(x0), y0=np.concatenate(y0),
              vx=np.concatenate(vx), vy=np.concatenate(vy), life=np.concatenate(life),
              col=np.concatenate(col, 0), siz=np.concatenate(siz))
    fw["phase"] = rng.uniform(0, 2 * math.pi, fw["t0"].size).astype(np.float32)
    return fw, sorted(burst_times)


def _scatter(layer, xs, ys, cols, weights, pw, ph):
    """Additive point scatter into a float32 (ph,pw,3) layer via bincount."""
    if xs.size == 0:
        return
    ix = xs.astype(np.int32)
    iy = ys.astype(np.int32)
    ok = (ix >= 0) & (ix < pw) & (iy >= 0) & (iy < ph) & (weights > 0.004)
    if not ok.any():
        return
    flat = (iy[ok] * pw + ix[ok]).astype(np.int64)
    wt = weights[ok]
    cl = cols[ok]
    size = pw * ph
    for c in range(3):
        layer[..., c] += np.bincount(flat, weights=cl[:, c] * wt,
                                     minlength=size).reshape(ph, pw)


# ==========================================================================
# 4. BACKGROUND
# ==========================================================================
def _make_background(w, h):
    top = np.array(BG_TOP, np.float32)
    mid = np.array(BG_MID, np.float32)
    bot = np.array(BG_BOTTOM, np.float32)
    ramp = np.linspace(0.0, 1.0, h, dtype=np.float32).reshape(h, 1)
    lo = np.clip(ramp * 2.0, 0, 1)
    hi = np.clip((ramp - 0.5) * 2.0, 0, 1)
    grad = np.where(ramp < 0.5,
                    top[None, :] * (1 - lo) + mid[None, :] * lo,
                    mid[None, :] * (1 - hi) + bot[None, :] * hi).astype(np.float32)
    frame = np.repeat(grad[:, None, :], w, axis=1)

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - w * 0.5) / (w * 0.72)) ** 2 + ((yy - h * 0.45) / (h * 0.72)) ** 2)
    frame *= np.clip(1.15 - 0.55 * r ** 1.7, 0.32, 1.22)[..., None]

    rng = np.random.default_rng(7)
    stars = np.zeros((h, w), np.float32)
    n = int(w * h / 5200)
    stars[rng.integers(0, h, n), rng.integers(0, w, n)] = rng.uniform(40, 150, n)
    frame += (cv2.GaussianBlur(stars, (0, 0), 0.9)[..., None]
              * np.array([0.9, 0.9, 1.0], np.float32))
    return np.clip(frame, 0, 255)


# ==========================================================================
# 5. TEXT  --  STROKE-FREE GLYPH MASK + BLUR-DERIVED RIM
# ==========================================================================
def _resolve_font_path(candidates):
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def _load_font(candidates, size):
    path = _resolve_font_path(candidates)
    if path:
        engines = []
        layout = getattr(ImageFont, "Layout", None)
        if layout is not None:
            engines.append({"layout_engine": layout.RAQM})
        legacy = getattr(ImageFont, "LAYOUT_RAQM", None)
        if legacy is not None:
            engines.append({"layout_engine": legacy})
        engines.append({})
        for kw in engines:
            try:
                return ImageFont.truetype(path, size, **kw)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def _text_width(draw, text, font):
    try:
        return draw.textlength(text, font=font)
    except Exception:
        b = draw.textbbox((0, 0), text, font=font)
        return b[2] - b[0]


# --------------------------------------------------------------------------
# Hand-drawn emoji-replacement icons for CTA text.
#
# Emoji glyphs have no reliable cross-platform answer here: Windows'
# Nirmala.ttf has none, most bare Linux containers (Streamlit Cloud
# included, unless the operator adds a font to packages.txt) have no
# color-emoji font either, and PIL doesn't fall back to a system emoji
# font for a glyph missing from the loaded font - it draws a tofu box.
# So instead of gambling on font availability, the handful of emoji this
# module's CTA text actually uses are hand-drawn as plain filled shapes,
# in the exact same style as the SUBSCRIBE button's bell icon below. Each
# one is drawn straight onto the CTA's own text mask (fill=255), so it
# rides through the SAME colourize -> rim -> glow -> shadow pipeline as
# the Devanagari glyphs next to it - one consistent look, zero extra
# compositing, and it works identically on every platform.
# --------------------------------------------------------------------------
_VARIATION_SELECTORS = ("\ufe0f", "\ufe0e", "\u200d")


def _petal_points(cx, cy, angle, length, width, n=12):
    """A symmetric pointed-oval (vesica/petal) shape pointing along `angle`
    from (cx,cy): tapers to zero width at both t=0 and t=1. Reused for the
    flower petals, the thumb, and the folded-hands icon below."""
    pts = []
    for i in range(n + 1):
        t = i / n
        lx, ly = length * t, (width / 2.0) * math.sin(math.pi * t)
        pts.append((lx, ly))
    for i in range(n, -1, -1):
        t = i / n
        lx, ly = length * t, -(width / 2.0) * math.sin(math.pi * t)
        pts.append((lx, ly))
    ca, sa = math.cos(angle), math.sin(angle)
    return [(cx + lx * ca - ly * sa, cy + lx * sa + ly * ca) for lx, ly in pts]


def _icon_sparkle(draw, box):
    x0, y0, x1, y1 = box
    cx, cy, R = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2
    pts = []
    for i in range(8):
        ang = i * math.pi / 4 - math.pi / 2
        r = R if i % 2 == 0 else R * 0.38
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    draw.polygon(pts, fill=255)
    draw.ellipse([cx + R * 0.5, cy - R * 1.0, cx + R * 0.82, cy - R * 0.68], fill=255)


def _icon_thumbs_up(draw, box):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    fx0, fy0, fx1, fy1 = x0 + w * 0.22, y0 + h * 0.46, x1 - w * 0.02, y1 - h * 0.04
    draw.rounded_rectangle([fx0, fy0, fx1, fy1], radius=h * 0.15, fill=255)
    tx0, ty0, tx1, ty1 = x0 + w * 0.08, y0 + h * 0.04, x0 + w * 0.46, y0 + h * 0.58
    draw.rounded_rectangle([tx0, ty0, tx1, ty1], radius=(tx1 - tx0) * 0.45, fill=255)
    for frac in (0.42, 0.68):     # knuckle creases so the fist reads as fingers
        yy = fy0 + (fy1 - fy0) * frac
        draw.line([(fx0 + w * 0.05, yy), (fx1 - w * 0.04, yy)],
                  fill=0, width=max(1, int(h * 0.025)))


def _icon_bell_glyph(draw, box):
    """Same silhouette as _make_bell_icon (SUBSCRIBE button), drawn
    straight onto an existing L-mode mask instead of its own RGBA tile."""
    x0, y0, x1, y1 = box
    s = x1 - x0
    draw.pieslice([x0 + s * 0.16, y0 + s * 0.14, x0 + s * 0.84, y0 + s * 0.82], 180, 360, fill=255)
    draw.polygon([(x0 + s * 0.16, y0 + s * 0.48), (x0 + s * 0.84, y0 + s * 0.48),
                  (x0 + s * 0.92, y0 + s * 0.70), (x0 + s * 0.08, y0 + s * 0.70)], fill=255)
    draw.rounded_rectangle([x0 + s * 0.06, y0 + s * 0.68, x0 + s * 0.94, y0 + s * 0.78],
                           s * 0.05, fill=255)
    draw.ellipse([x0 + s * 0.42, y0 + s * 0.79, x0 + s * 0.58, y0 + s * 0.95], fill=255)
    draw.ellipse([x0 + s * 0.44, y0 + s * 0.06, x0 + s * 0.56, y0 + s * 0.18], fill=255)


def _icon_namaste(draw, box):
    """Folded hands: a single vertical vesica + a few short finger lines."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, y0 + h * 0.62
    pts = _petal_points(cx, cy, angle=-math.pi / 2, length=h * 0.62, width=w * 0.62, n=12)
    draw.polygon(pts, fill=255)
    tip_y = cy - h * 0.62
    for i in (-1.4, -0.5, 0.5, 1.4):
        fx = cx + i * w * 0.085
        draw.line([(fx, tip_y + h * 0.05), (fx, tip_y - h * 0.12)],
                  fill=255, width=max(2, int(w * 0.055)))


def _icon_om(draw, box):
    """Approximates the sacred syllable as a swirl (a ring opened into a
    'C' with a tail ball) plus a crescent and dot above - the same three
    structural parts as the real glyph, simplified for icon size."""
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + (y1 - y0) * 0.10
    R = (x1 - x0) / 2 * 0.60
    draw.ellipse([cx - R, cy - R, cx + R, cy + R], fill=255)
    ir = R * 0.50
    draw.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=0)
    wedge = [(cx + R * 0.08, cy - R * 1.3), (cx + R * 1.3, cy - R * 0.15),
             (cx + R * 1.3, cy + R * 0.70), (cx + R * 0.08, cy + R * 0.20)]
    draw.polygon(wedge, fill=0)
    tx, ty, tr = cx + R * 0.72, cy + R * 0.48, R * 0.32
    draw.ellipse([tx - tr, ty - tr, tx + tr, ty + tr], fill=255)
    mR = R * 0.60
    mcx, mcy = cx - R * 0.05, cy - R * 1.62
    draw.ellipse([mcx - mR, mcy - mR, mcx + mR, mcy + mR], fill=255)
    draw.ellipse([mcx - mR + mR * 0.58, mcy - mR * 1.05, mcx + mR + mR * 0.58, mcy + mR * 0.95], fill=0)
    dR = R * 0.20
    dcx, dcy = cx - R * 0.05, mcy - mR * 1.35
    draw.ellipse([dcx - dR, dcy - dR, dcx + dR, dcy + dR], fill=255)


def _icon_flower(draw, box, n_petals=5, width_ratio=0.85, stamen=False):
    x0, y0, x1, y1 = box
    cx, cy, R = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2
    length = R * 0.92
    width = length * width_ratio
    for i in range(n_petals):
        ang = -math.pi / 2 + i * 2 * math.pi / n_petals
        draw.polygon(_petal_points(cx, cy, ang, length, width, n=10), fill=255)
    gap_w = max(1, R * 0.07)      # thin radial gaps keep petals visually separate
    for i in range(n_petals):
        ang = -math.pi / 2 + (i + 0.5) * 2 * math.pi / n_petals
        ex, ey = cx + math.cos(ang) * length * 1.05, cy + math.sin(ang) * length * 1.05
        draw.line([(cx, cy), (ex, ey)], fill=0, width=int(gap_w))
    draw.ellipse([cx - R * 0.16, cy - R * 0.16, cx + R * 0.16, cy + R * 0.16], fill=255)
    if stamen:
        tipx, tipy = cx, cy - length * 1.15
        draw.line([(cx, cy), (tipx, tipy)], fill=255, width=max(1, int(R * 0.1)))
        draw.ellipse([tipx - R * 0.12, tipy - R * 0.12, tipx + R * 0.12, tipy + R * 0.12], fill=255)


_EMOJI_ICONS = {
    "\u2728": _icon_sparkle,                                                    # ✨
    "\U0001F44D": _icon_thumbs_up,                                              # 👍
    "\U0001F514": _icon_bell_glyph,                                             # 🔔
    "\U0001F64F": _icon_namaste,                                                # 🙏
    "\U0001F549": _icon_om,                                                     # 🕉
    "\U0001F338": lambda d, b: _icon_flower(d, b, n_petals=5, width_ratio=0.72, stamen=False),  # 🌸
    "\U0001F33A": lambda d, b: _icon_flower(d, b, n_petals=5, width_ratio=0.55, stamen=True),   # 🌺
}


def _is_decorative_symbol(ch):
    """True for codepoints outside normal text ranges that also aren't one
    of our hand-drawn icons - dropped silently rather than handed to the
    Devanagari font (which would render them as a tofu box)."""
    cp = ord(ch)
    if cp < 0x2000:
        return False
    if 0x0900 <= cp <= 0x097F or 0xA8E0 <= cp <= 0xA8FF:   # Devanagari (+ extended)
        return False
    ranges = ((0x2190, 0x2BFF), (0x1F000, 0x1FFFF), (0x2600, 0x27BF), (0xFE00, 0xFE0F))
    return any(lo <= cp <= hi for lo, hi in ranges)


def _split_runs(word, skipped):
    """word -> [('text', str) | ('icon', codepoint), ...]. Variation
    selectors/ZWJ vanish with zero width; unknown decorative symbols are
    dropped (and recorded into `skipped`) instead of becoming a tofu box."""
    runs, buf = [], ""
    for ch in word:
        if ch in _VARIATION_SELECTORS:
            continue
        if ch in _EMOJI_ICONS:
            if buf:
                runs.append(("text", buf)); buf = ""
            runs.append(("icon", ch))
        elif _is_decorative_symbol(ch):
            skipped.add(ch)
        else:
            buf += ch
    if buf:
        runs.append(("text", buf))
    return runs


def _run_width(draw, run, font, icon_size):
    kind, val = run
    return icon_size if kind == "icon" else _text_width(draw, val, font)


def _word_width(draw, runs, font, icon_size):
    return sum(_run_width(draw, r, font, icon_size) for r in runs)


def _wrap_words_mixed(draw, text, font, max_width, icon_size, skipped):
    words = [w for w in (_split_runs(w, skipped) for w in text.split(" ") if w) if w]
    if not words:
        return [[]]
    space_w = _run_width(draw, ("text", " "), font, icon_size)
    lines, cur, cur_w = [], [], 0.0
    for w in words:
        ww = _word_width(draw, w, font, icon_size)
        add_w = ww + (space_w if cur else 0.0)
        if cur and cur_w + add_w > max_width:
            lines.append(cur)
            cur, cur_w = [w], ww
        else:
            cur.append(w)
            cur_w += add_w
    if cur:
        lines.append(cur)
    return lines


def _draw_plain_mask(text, font, canvas_w, canvas_h, line_gap_ratio=0.26):
    """
    Draw the text ONCE, fill only. No stroke_width anywhere on the
    Devanagari glyphs. Also lays out the handful of hand-drawn icons in
    _EMOJI_ICONS inline with the text (see module note above) - they're
    drawn as plain filled shapes on this same mask, so decoration applied
    afterwards treats them exactly like any other glyph.

    Returns (mask uint8 array, list_of_line_strings, skipped_codepoints).
    """
    mask = Image.new("L", (canvas_w, canvas_h), 0)
    draw = ImageDraw.Draw(mask)
    try:
        asc, desc = font.getmetrics()
        line_h = asc + desc
    except Exception:
        line_h = int(getattr(font, "size", 32) * 1.25)
    icon_size = line_h * 0.82

    skipped = set()
    lines = _wrap_words_mixed(draw, text, font, int(canvas_w * 0.90), icon_size, skipped)

    gap = int(line_h * line_gap_ratio)
    total = len(lines) * line_h + (len(lines) - 1) * gap
    y = (canvas_h - total) / 2.0
    space_w = _run_width(draw, ("text", " "), font, icon_size)

    line_strings = []
    for line_words in lines:
        line_w = sum(_word_width(draw, w, font, icon_size) for w in line_words) \
                 + space_w * max(0, len(line_words) - 1)
        x = (canvas_w - line_w) / 2.0
        icon_top = y + (line_h - icon_size) / 2.0
        parts = []
        for wi, word_runs in enumerate(line_words):
            if wi > 0:
                x += space_w
            for kind, val in word_runs:
                if kind == "text":
                    # <<< fill only. NO stroke_width. NO second pass. >>>
                    draw.text((x, y), val, font=font, fill=255, anchor="la")
                    x += _run_width(draw, (kind, val), font, icon_size)
                    parts.append(val)
                else:
                    _EMOJI_ICONS[val](draw, (x, icon_top, x + icon_size, icon_top + icon_size))
                    x += icon_size
        line_strings.append("".join(parts))
        y += line_h + gap
    return np.array(mask, np.uint8), line_strings, skipped


def _strip_for_speech(text):
    """Emoji and decorative symbols read badly (or not at all) through
    edge-tts / gTTS - some skip them, some stumble. This is used as the
    default spoken line whenever the caller passes cta_text with emoji but
    no separate voice_text, so a caller who only customises the on-screen
    CTA still gets a clean spoken line for free."""
    if not text:
        return text
    kept = [ch for ch in text
            if not (ch in _VARIATION_SELECTORS or ch in _EMOJI_ICONS
                   or _is_decorative_symbol(ch))]
    return re.sub(r"[ \t]+", " ", "".join(kept)).strip()


def _mask_to_rgba(mask, fill_rgb, rim_rgb=None, shadow_rgb=(0, 0, 0),
                  rim_strength=1.0, glow_rgb=None, glow_strength=0.0):
    """Decoration is derived from blur(mask) and composited strictly UNDER it."""
    h, w = mask.shape
    a = mask.astype(np.float32) / 255.0
    base = max(1.0, min(h, w) * 0.010)
    out_rgb = np.zeros((h, w, 3), np.float32)
    out_a = np.zeros((h, w), np.float32)

    def _under(rgb, alpha):
        nonlocal out_rgb, out_a
        keep = 1.0 - out_a
        out_rgb = out_rgb + rgb * alpha[..., None] * keep[..., None]
        out_a = out_a + alpha * keep

    def _over(rgb, alpha):
        nonlocal out_rgb, out_a
        inv = 1.0 - alpha
        out_rgb = rgb * alpha[..., None] + out_rgb * inv[..., None]
        out_a = alpha + out_a * inv

    _over(np.array(fill_rgb, np.float32)[None, None, :], a)

    if rim_rgb is not None and rim_strength > 0:
        blur = cv2.GaussianBlur(a, (0, 0), sigmaX=base * 1.15, sigmaY=base * 1.15)
        _under(np.array(rim_rgb, np.float32)[None, None, :],
               np.clip(blur * 2.35 - a, 0, 1) * rim_strength)

    if glow_rgb is not None and glow_strength > 0:
        g = cv2.GaussianBlur(a, (0, 0), sigmaX=base * 4.0, sigmaY=base * 4.0)
        _under(np.array(glow_rgb, np.float32)[None, None, :],
               np.clip(g * 1.6 - a, 0, 1) * glow_strength)

    if shadow_rgb is not None:
        sh = cv2.GaussianBlur(a, (0, 0), sigmaX=base * 2.1, sigmaY=base * 2.1)
        off = max(1, int(base * 1.6))
        sh = np.roll(np.roll(sh, off, 0), off, 1)
        sh[:off, :] = 0.0
        sh[:, :off] = 0.0
        _under(np.array(shadow_rgb, np.float32)[None, None, :],
               np.clip(sh * 1.25, 0, 1) * 0.92)

    rgba = np.zeros((h, w, 4), np.uint8)
    safe = np.maximum(out_a, 1e-6)
    rgba[..., :3] = np.clip(out_rgb / safe[..., None], 0, 255).astype(np.uint8)
    rgba[..., 3] = np.clip(out_a * 255.0, 0, 255).astype(np.uint8)
    return rgba


def render_devanagari_text_image(text, font_size, color_rgb, canvas_w, canvas_h):
    """v1-compatible helper, now on the stroke-free path."""
    font = _load_font(_DEVANAGARI_FONT_CANDIDATES, font_size)
    mask, _, _skipped = _draw_plain_mask(text, font, canvas_w, canvas_h)
    return Image.fromarray(_mask_to_rgba(
        mask, color_rgb, rim_rgb=CTA_RIM_COLOR, rim_strength=1.0,
        glow_rgb=(255, 170, 40), glow_strength=0.40,
        shadow_rgb=CTA_SHADOW_COLOR), "RGBA")


def assert_glyph_mask_untouched(text="सब्सक्राइब", font_size=64, canvas=(900, 260)):
    """Proves the rim/shadow never altered a single opaque glyph pixel."""
    font = _load_font(_DEVANAGARI_FONT_CANDIDATES, font_size)
    mask, _, _ = _draw_plain_mask(text, font, canvas[0], canvas[1])
    rgba = _mask_to_rgba(mask, CTA_TEXT_COLOR, rim_rgb=CTA_RIM_COLOR,
                         glow_rgb=(255, 170, 40), glow_strength=0.40)
    # only fully-opaque pixels; the 1px antialiased edge is *meant* to blend
    solid = mask == 255
    assert solid.any(), "glyph mask is empty - no Devanagari font found"
    assert (rgba[..., 3][solid] == 255).all(), "decoration eroded glyph alpha"
    for c in range(3):
        assert (rgba[..., c][solid] == CTA_TEXT_COLOR[c]).all(), "rim bled into glyph body"
    return mask


# ==========================================================================
# 6. UI TILES
# ==========================================================================
def _rounded_rect(draw, box, radius, fill):
    try:
        draw.rounded_rectangle(box, radius=radius, fill=fill)
    except Exception:
        draw.rectangle(box, fill=fill)


def _make_bell_icon(size):
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = BELL_COLOR + (255,)
    d.pieslice([s * 0.16, s * 0.14, s * 0.84, s * 0.82], 180, 360, fill=c)
    d.polygon([(s * 0.16, s * 0.48), (s * 0.84, s * 0.48),
               (s * 0.92, s * 0.70), (s * 0.08, s * 0.70)], fill=c)
    _rounded_rect(d, [s * 0.06, s * 0.68, s * 0.94, s * 0.78], s * 0.05, c)
    d.ellipse([s * 0.42, s * 0.79, s * 0.58, s * 0.95], fill=c)
    d.ellipse([s * 0.44, s * 0.06, s * 0.56, s * 0.18], fill=c)
    return img


def _make_subscribe_tile(btn_w, btn_h):
    """Metallic red pill + bell + outer glow. RGBA uint8."""
    pad = int(btn_h * 0.75)
    W, H = btn_w + pad * 2, btn_h + pad * 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = pad, pad, pad + btn_w, pad + btn_h
    r = btn_h * 0.22

    _rounded_rect(d, [x0, y0, x1, y1], r, SUBSCRIBE_RED + (255,))

    # Metallic sheen. ImageDraw REPLACES the destination pixel, alpha included -
    # drawing a translucent band straight onto the button punches a hole through
    # it. Draw the translucent bands on their own layer and alpha_composite.
    sheen = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheen)
    _rounded_rect(sd, [x0 + btn_h * 0.06, y0 + btn_h * 0.07,
                       x1 - btn_h * 0.06, y0 + btn_h * 0.44], r * 0.7,
                  SUBSCRIBE_RED_HI + (95,))
    _rounded_rect(sd, [x0 + btn_h * 0.06, y0 + btn_h * 0.66,
                       x1 - btn_h * 0.06, y1 - btn_h * 0.07], r * 0.7, (120, 0, 6, 70))
    img.alpha_composite(sheen)

    bell_size = int(btn_h * 0.56)
    bell = _make_bell_icon(bell_size)
    label = "SUBSCRIBE"
    font = _load_font(_LATIN_BOLD_FONT_CANDIDATES, int(btn_h * 0.42))
    try:
        tw = d.textlength(label, font=font)
    except Exception:
        b = d.textbbox((0, 0), label, font=font)
        tw = b[2] - b[0]
    gap = btn_h * 0.26
    tx = x0 + (btn_w - (tw + gap + bell_size)) / 2.0
    ty = y0 + btn_h / 2.0
    d.text((tx, ty), label, font=font, fill=SUBSCRIBE_TEXT + (255,), anchor="lm")
    img.alpha_composite(bell, (int(tx + tw + gap), int(ty - bell_size / 2.0)))

    arr = np.array(img).astype(np.float32)
    a = arr[..., 3] / 255.0
    glow = np.clip(cv2.GaussianBlur(a, (0, 0), sigmaX=btn_h * 0.30,
                                    sigmaY=btn_h * 0.30) * 1.5 - a, 0, 1) * 0.85
    keep = 1.0 - a
    out_a = a + glow * keep
    out_rgb = (arr[..., :3] * a[..., None]
               + np.array(SUBSCRIBE_RED_HI, np.float32)[None, None, :]
               * glow[..., None] * keep[..., None])
    safe = np.maximum(out_a, 1e-6)
    res = np.zeros((H, W, 4), np.uint8)
    res[..., :3] = np.clip(out_rgb / safe[..., None], 0, 255).astype(np.uint8)
    res[..., 3] = np.clip(out_a * 255, 0, 255).astype(np.uint8)
    return res


def resolve_asset(path):
    """
    Resolve an asset name against the caller's cwd and this module's folder,
    so a bare "shiva_motif.png" works whether engine.py is launched from the
    project root or from anywhere else. Returns None when nothing is found.
    """
    if not path:
        return None
    cands = [path,
             os.path.join(os.getcwd(), path),
             os.path.join(os.path.dirname(os.path.abspath(__file__)), path)]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def _make_mini_subscribe_tile(width, tint=(255, 255, 255)):
    """Tiny metallic SUBSCRIBE pill for the background rain."""
    w_ = max(14, int(width))
    h_ = max(6, int(w_ * 0.34))
    ss = 4                                        # supersample, then area-downsample
    img = Image.new("RGBA", (w_ * ss, h_ * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w_, h_ = w_ * ss, h_ * ss
    r = h_ * 0.34
    _rounded_rect(d, [0, 0, w_ - 1, h_ - 1], r, SUBSCRIBE_RED + (255,))
    # translucent parts go on their own layer (see _make_subscribe_tile)
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(over)
    _rounded_rect(od, [1, 1, w_ - 2, h_ * 0.46], r * 0.8, SUBSCRIBE_RED_HI + (130,))
    # a white bar standing in for the wordmark (real text is illegible this small)
    _rounded_rect(od, [w_ * 0.16, h_ * 0.34, w_ * 0.84, h_ * 0.66], h_ * 0.16,
                  tint + (235,))
    img.alpha_composite(over)
    return cv2.resize(np.array(img, np.uint8), (w_ // ss, h_ // ss),
                      interpolation=cv2.INTER_AREA)


def _make_mini_bell_tile(size, tint=(255, 236, 178)):
    """
    Tiny metallic bell for the background rain. Drawn 4x oversize and
    area-downsampled - at rain scale a direct rasterisation collapses the
    dome and lip into an unreadable triangle.
    """
    s_ = max(8, int(size))
    big = _make_bell_icon(s_ * 4)
    arr = np.array(big, np.uint8)
    arr = cv2.resize(arr, (s_, s_), interpolation=cv2.INTER_AREA)
    out = arr.copy()
    out[..., 0] = tint[0]
    out[..., 1] = tint[1]
    out[..., 2] = tint[2]
    return out


def _build_subscribe_rain(n, w, h, short, rng, is_draft=False):
    """Continuous downward-floating subscribe buttons + bells behind the scene."""
    base = max(20, int(short * 0.078))
    tiles = []
    for k in (0.62, 0.85, 1.12):
        tiles.append(_make_mini_subscribe_tile(base * k))
    for k, tint in ((0.44, (255, 236, 178)),      # gold
                    (0.60, (226, 238, 255)),      # chrome
                    (0.80, (255, 236, 178))):
        tiles.append(_make_mini_bell_tile(base * k, tint))
    kind = rng.integers(0, len(tiles), n)
    span = h + max(t.shape[0] for t in tiles) * 2
    return dict(
        tiles=tiles,
        kind=kind,
        x0=rng.uniform(-0.04 * w, 1.04 * w, n).astype(np.float32),
        y0=rng.uniform(0, span, n).astype(np.float32),
        speed=rng.uniform(h * 0.035, h * 0.115, n).astype(np.float32),
        amp=rng.uniform(4, 26, n).astype(np.float32),
        frq=rng.uniform(0.35, 1.25, n).astype(np.float32),
        phase=rng.uniform(0, 2 * math.pi, n).astype(np.float32),
        gain=rng.uniform(0.30, 0.66, n).astype(np.float32),
        span=float(span),
    )


def _load_rgba(path, target_w):
    if not path or not os.path.exists(path):
        return None
    try:
        img = Image.open(path).convert("RGBA")
        ratio = target_w / float(img.width)
        img = img.resize((int(target_w), max(1, int(img.height * ratio))), Image.LANCZOS)
        return np.array(img, np.uint8)
    except Exception:
        return None


def _blend_tile_over_accum(acc_rgb, acc_a, tile, x, y):
    """Source OVER dest. Call order = bottom layer first, topmost last."""
    H, W = acc_a.shape
    th, tw = tile.shape[:2]
    x0, y0 = int(x), int(y)
    sx0, sy0 = max(0, -x0), max(0, -y0)
    dx0, dy0 = max(0, x0), max(0, y0)
    cw, ch = min(tw - sx0, W - dx0), min(th - sy0, H - dy0)
    if cw <= 0 or ch <= 0:
        return
    src = tile[sy0:sy0 + ch, sx0:sx0 + cw].astype(np.float32)
    sa = src[..., 3] / 255.0
    inv = 1.0 - sa
    acc_rgb[dy0:dy0 + ch, dx0:dx0 + cw] = (
        src[..., :3] * sa[..., None]
        + acc_rgb[dy0:dy0 + ch, dx0:dx0 + cw] * inv[..., None])
    acc_a[dy0:dy0 + ch, dx0:dx0 + cw] = sa + acc_a[dy0:dy0 + ch, dx0:dx0 + cw] * inv


def _paste_over_frame(frame, tile, x, y, gain=1.0):
    H, W = frame.shape[:2]
    th, tw = tile.shape[:2]
    x0, y0 = int(x), int(y)
    sx0, sy0 = max(0, -x0), max(0, -y0)
    dx0, dy0 = max(0, x0), max(0, y0)
    cw, ch = min(tw - sx0, W - dx0), min(th - sy0, H - dy0)
    if cw <= 0 or ch <= 0:
        return
    src = tile[sy0:sy0 + ch, sx0:sx0 + cw].astype(np.float32)
    sa = (src[..., 3] / 255.0)[..., None] * float(gain)
    region = frame[dy0:dy0 + ch, dx0:dx0 + cw]
    frame[dy0:dy0 + ch, dx0:dx0 + cw] = src[..., :3] * sa + region * (1.0 - sa)


# ==========================================================================
# 7. AUDIO SYNTHESIS
# ==========================================================================
def _lowpass(sig, k):
    k = max(1, int(k))
    return sig if k == 1 else np.convolve(sig, np.ones(k, np.float32) / k,
                                          mode="same").astype(np.float32)


def _mix(dst, src, start_idx, gain=1.0):
    s = max(0, int(start_idx))
    if s >= dst.size or src.size == 0:
        return
    e = min(dst.size, s + src.size)
    dst[s:e] += src[:e - s] * gain


def _boom(sr, rng, dur=1.6):
    t = np.arange(int(sr * dur), dtype=np.float32) / sr
    f = 92.0 * np.exp(-3.1 * t) + 27.0
    body = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-2.9 * t)
    sub = np.sin(2 * np.pi * 42 * t) * np.exp(-4.4 * t) * 0.55
    crack = _lowpass(rng.standard_normal(t.size).astype(np.float32), 9) * np.exp(-17.0 * t)
    tail = _lowpass(rng.standard_normal(t.size).astype(np.float32), 55) * np.exp(-2.1 * t)
    return (0.95 * body + sub + 0.50 * crack + 0.28 * tail).astype(np.float32)


def _bell(sr, rng, f0=1046.5, dur=2.6):
    t = np.arange(int(sr * dur), dtype=np.float32) / sr
    sig = np.zeros_like(t)
    for r, a, d in zip([1.0, 2.0, 2.76, 5.40, 8.93],
                       [1.00, 0.55, 0.40, 0.20, 0.10],
                       [2.1, 2.7, 3.5, 5.0, 7.5]):
        sig += a * np.sin(2 * np.pi * f0 * r * t) * np.exp(-d * t)
    strike = rng.standard_normal(t.size).astype(np.float32) * np.exp(-70.0 * t) * 0.20
    return ((sig / 2.25) + strike).astype(np.float32)


def _formation_swell(sr, rng, dur=2.4):
    """Rising shimmer while the drones converge, landing on a soft gong."""
    n = max(1, int(sr * dur))
    t = np.arange(n, dtype=np.float32) / sr
    k = np.clip(t / max(1e-3, dur), 0, 1)
    f = 240.0 * np.exp(np.log(1400.0 / 240.0) * k)
    swirl = np.sin(2 * np.pi * np.cumsum(f) / sr) * (k ** 1.6) * 0.35
    air = _lowpass(rng.standard_normal(n).astype(np.float32), 24) * (k ** 2.2) * 0.30
    gong = np.zeros(n, np.float32)
    gi = int(n * 0.80)
    gt = t[:n - gi]
    for r, a, d in zip([1.0, 1.52, 2.41, 3.7], [1.0, 0.5, 0.3, 0.16], [1.1, 1.7, 2.6, 4.0]):
        gong[gi:] += a * np.sin(2 * np.pi * 146.8 * r * gt) * np.exp(-d * gt)
    return (swirl + air + gong * 0.42).astype(np.float32)


def _run_with_timeout(fn, timeout_s):
    """
    Run fn() with a hard wall-clock timeout, from any calling thread
    (Streamlit worker threads included - unlike signal.alarm, which only
    works on the main thread). On timeout we stop waiting immediately;
    shutdown(wait=False) means we do NOT block for the stuck network call
    to finish, we just let it die in the background.
    """
    import concurrent.futures
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        fut = ex.submit(fn)
        return fut.result(timeout=timeout_s)
    finally:
        ex.shutdown(wait=False)


def _synthesize_tts_edge(text, out_path, voice="hi-IN-SwaraNeural"):
    """Backend 1: edge-tts (Microsoft Bing speech endpoint). Raises on failure."""
    import asyncio
    import edge_tts

    async def _run():
        await edge_tts.Communicate(text, voice).save(out_path)

    try:
        asyncio.run(_run())
    except RuntimeError:
        # already inside a running loop (notebook / async host / some app servers)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 512:
        raise RuntimeError("edge-tts produced no audio")
    return out_path


def _synthesize_tts_gtts(text, out_path, lang="hi"):
    """Backend 2 (fallback): gTTS (Google Translate speech endpoint)."""
    from gtts import gTTS
    gTTS(text=text, lang=lang).save(out_path)
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 512:
        raise RuntimeError("gTTS produced no audio")
    return out_path


# Cascade order: edge-tts first (it's the higher-quality neural voice), then
# gTTS. Each entry is (name, fn(text, out_path) -> out_path). Add more
# backends here (e.g. a local/offline TTS) and the cascade picks them up
# automatically - _voice_track tries them in order and stops at the first
# one that actually produces audio.
_TTS_BACKENDS = [
    ("edge-tts", lambda text, out, voice, lang: _synthesize_tts_edge(text, out, voice=voice)),
    ("gTTS", lambda text, out, voice, lang: _synthesize_tts_gtts(text, out, lang=lang)),
]


def _decode_audio_mono(path, sr):
    """Decode any ffmpeg-readable file (mp3 from either TTS backend) to a
    mono float32 array at `sr`, via MoviePy's AudioFileClip as requested."""
    clip = AudioFileClip(path)
    try:
        arr = clip.to_soundarray(fps=sr)
    finally:
        try:
            clip.close()
        except Exception:
            pass
    arr = np.asarray(arr, np.float32)
    if arr.ndim == 2:
        arr = arr.mean(axis=1)
    return arr.astype(np.float32)


def _voice_track(text, voice, sr, gtts_lang="hi", timeout_s=14.0):
    """
    Try each backend in _TTS_BACKENDS in order; use the first one that
    produces real audio within `timeout_s`. Returns
        (mono float32 voice, None, backend_name)          on success, or
        (None, combined_reason_string, None)               if every backend failed.
    Never raises - no network, a blocked endpoint, a missing package, or a
    hung request must never take the whole render down with it.
    """
    if not text:
        return None, "no cta_text", None

    reasons = []
    for name, fn in _TTS_BACKENDS:
        mp3 = os.path.join(tempfile.gettempdir(),
                           "climax_tts_%s_%s.mp3" % (name.replace("-", ""), uuid.uuid4().hex[:8]))
        try:
            _run_with_timeout(lambda: fn(text, mp3, voice, gtts_lang), timeout_s)
            _register_temp(mp3)
            v = _decode_audio_mono(mp3, sr)
            if v.size == 0:
                raise RuntimeError("decoded to an empty track")
            peak = float(np.max(np.abs(v))) or 1.0
            return (v / peak * 0.92).astype(np.float32), None, name
        except ImportError:
            reasons.append("%s: package not installed" % name)
        except TimeoutError:
            reasons.append("%s: timed out after %.0fs" % (name, timeout_s))
        except Exception as e:
            # concurrent.futures raises its own TimeoutError on Python <3.11
            # under a different name depending on version; string-match it
            # too so both resolve to the same clean message.
            if type(e).__name__ == "TimeoutError":
                reasons.append("%s: timed out after %.0fs" % (name, timeout_s))
            else:
                reasons.append("%s: %s: %s" % (name, type(e).__name__, str(e)[:80]))
    return None, "all TTS backends failed - " + " | ".join(reasons), None


def _duck(bed, voice_env, depth=0.62):
    """Sidechain: pull the music down wherever the voice is speaking."""
    return bed * (1.0 - depth * np.clip(voice_env, 0, 1))


def _synthesize_audio(duration, boom_times, chime_times, seed=0, sr=44100,
                      voice_text=None, voice_name="hi-IN-SwaraNeural",
                      voice_start=None, on_status=None, gtts_lang="hi",
                      tts_timeout_s=14.0):
    rng = np.random.default_rng(seed + 991)
    n = int(sr * duration)
    t = np.arange(n, dtype=np.float32) / sr
    out = np.zeros(n, np.float32)

    for f, amp in [(110.0, 0.30), (164.81, 0.22), (220.0, 0.17), (329.63, 0.09)]:
        out += amp * np.sin(2 * np.pi * f * t + 0.4 * np.sin(2 * np.pi * 0.11 * t + f))
    out *= 0.22 + 0.78 * np.clip(t / max(1e-3, duration * 0.8), 0, 1)

    prog = np.clip(t / max(1e-3, duration), 0, 1)
    fr = 170.0 * np.exp(np.log(1500.0 / 170.0) * prog)
    out += 0.16 * np.sin(2 * np.pi * np.cumsum(fr) / sr) * (prog ** 2.2)
    out += 0.11 * _lowpass(rng.standard_normal(n).astype(np.float32), 30) * (prog ** 3.0)

    _mix(out, _formation_swell(sr, rng, dur=min(FORM_TIME + 0.4, duration)), 0, gain=0.85)

    boom = _boom(sr, rng)
    for bt in boom_times:
        _mix(out, boom * float(rng.uniform(0.75, 1.15)), int(bt * sr), gain=0.85)
    for i, ct in enumerate(chime_times):
        _mix(out, _bell(sr, rng, f0=1046.5 * (1.0 if i % 2 == 0 else 1.335)),
             int(ct * sr), gain=0.42)

    # ---- Hindi AI voiceover, ducked into the bed ----
    # Tries edge-tts first, then falls back to gTTS if edge-tts's endpoint is
    # blocked (e.g. Streamlit Cloud blocking speech.platform.bing.com), errors,
    # or hangs past tts_timeout_s. See _TTS_BACKENDS / _voice_track above.
    if voice_text:
        voice, reason, backend = _voice_track(voice_text, voice_name, sr,
                                              gtts_lang=gtts_lang,
                                              timeout_s=tts_timeout_s)
        if voice is None:
            if on_status:
                on_status("voiceover skipped (%s)" % reason)
        else:
            start = FORM_TIME + 0.6 if voice_start is None else float(voice_start)
            # pull the start earlier if the line would run past the clip
            start = min(start, max(0.15, duration - voice.size / float(sr) - 0.25))
            start = max(0.0, start)
            si = int(start * sr)
            if voice.size > n - si:                 # still too long -> fade its tail
                voice = voice[:max(1, n - si)].copy()
                tail = min(voice.size, int(sr * 0.25))
                if tail > 1:
                    voice[-tail:] *= np.linspace(1.0, 0.0, tail, dtype=np.float32)

            env = np.zeros(n, np.float32)
            mag = np.abs(voice)
            k = max(1, int(sr * 0.12))
            mag = _lowpass(mag, k)
            mag = mag / (float(mag.max()) or 1.0)
            env[si:si + mag.size] = mag[:max(0, n - si)]
            env = _lowpass(env, max(1, int(sr * 0.05)))
            out = _duck(out, env)
            _mix(out, voice, si, gain=1.0)
            if on_status:
                on_status("voiceover mixed via %s at %.2fs (%.2fs long)"
                          % (backend, start, voice.size / float(sr)))

    fade = int(sr * min(0.85, duration * 0.18))
    if fade:
        out[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    head = int(sr * 0.06)
    if head:
        out[:head] *= np.linspace(0.0, 1.0, head, dtype=np.float32)

    peak = float(np.max(np.abs(out))) or 1.0
    pcm = np.clip(np.tanh(out / peak * 1.35) * 0.88 * 32767.0, -32768, 32767).astype(np.int16)

    path = os.path.join(tempfile.gettempdir(), "climax_audio_%s.wav" % uuid.uuid4().hex[:10])
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return _register_temp(path)


# ==========================================================================
# 8. PUBLIC API
# ==========================================================================
def generate_climax(duration, cta_text, watermark_path, target_size,
                    is_draft=True, motif_path="shiva_motif.png", with_audio=True,
                    show_subscribe=True, seed=None, with_voice=True,
                    voice_name="hi-IN-SwaraNeural", voice_text=None,
                    subscribe_rain=True, on_status=None, gtts_lang="hi",
                    tts_timeout_s=14.0):
    """
    Build the particle drone-show climax VideoClip (video + synthesized audio).

    duration       : seconds (>= ~5s recommended so the formation can breathe)
    cta_text       : Devanagari CTA text, e.g. DEFAULT_CTA_TEXT below. May
                     include the emoji in _EMOJI_ICONS - they render as
                     hand-drawn icons (see the module note above) and are
                     stripped automatically for whichever TTS backend
                     speaks the line (see _strip_for_speech).
    watermark_path : optional channel logo PNG, bottom-right (may be None)
    target_size    : (width, height) - 9:16 and 16:9 handled automatically
    is_draft       : cheap preview (12 fps, quarter-res layers, fewer particles)
    motif_path     : centre artwork, default "shiva_motif.png" (resolved against
                     cwd and this module's folder). When it loads, it becomes
                     the centrepiece and the particles form mandala rings AROUND
                     it so nothing covers the motif. When it is missing, the
                     module falls back to the pure-vector particle Shiva figure.
    with_audio     : attach the synthesized audio bed
    show_subscribe : draw the pulsing SUBSCRIBE + bell UI
    seed           : int for reproducible layouts
    with_voice     : speak the CTA and duck it into the bed. Tries edge-tts
                     (voice_name) first; if that's blocked, errors, or hangs
                     past tts_timeout_s, falls back to gTTS (gtts_lang) -
                     see _TTS_BACKENDS. Either way a failure never breaks the
                     render, it just leaves the voiceover out (on_status says
                     why).
    voice_name     : edge-tts voice, default Hindi "hi-IN-SwaraNeural"
    voice_text     : override the spoken line (defaults to cta_text)
    subscribe_rain : background rain of tiny subscribe buttons + bells
    on_status      : optional callable(str) for non-fatal notices (TTS skipped…)
    gtts_lang      : gTTS language code used ONLY if edge-tts fails, default "hi"
    tts_timeout_s  : per-backend wall-clock timeout in seconds before the next
                     backend in the cascade is tried
    """
    def _say(msg):
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass
        else:
            sys.stderr.write("[climax] %s\n" % msg)
    duration = max(1.0, float(duration))
    w, h = int(target_size[0]), int(target_size[1])
    vertical = h >= w
    rng = np.random.default_rng(seed if seed is not None else 20260916)

    fps = 12 if is_draft else 30
    pdiv = 4 if is_draft else 2
    pw, ph = max(2, w // pdiv), max(2, h // pdiv)
    adiv = pdiv * 2
    aw, ah = max(2, w // adiv), max(2, h // adiv)

    n_particles = 900 if is_draft else 2600
    n_fire = 120 if is_draft else 420
    n_bursts = max(1, int(max(0.0, duration - FORM_TIME) * (0.5 if is_draft else 1.1)))
    sparks_per = 60 if is_draft else 140

    # ---------------- layout ----------------
    if vertical:
        fig_h = h * 0.46
        fig_cy = h * 0.325
        text_cy, btn_cy = 0.745, 0.875
    else:
        fig_h = h * 0.58
        fig_cy = h * 0.345
        text_cy, btn_cy = 0.775, 0.905

    short = min(w, h)
    font_size = max(22, int(short * 0.055))
    text_cw, text_ch = int(w * 0.90), int(h * 0.20)
    btn_w = int(short * 0.44)
    btn_h = max(8, int(btn_w * 0.26))

    # ---------------- centre artwork ----------------
    motif_file = resolve_asset(motif_path)
    motif_tile = _load_rgba(motif_file, int(min(w * 0.46, fig_h * 0.78)))
    if motif_path and motif_file is None:
        _say("motif '%s' not found - falling back to the vector particle figure"
             % motif_path)

    # ---------------- particle fields ----------------
    if motif_tile is not None:
        mh, mw = motif_tile.shape[:2]
        motif_r = 0.5 * math.hypot(mw, mh) * 0.60
        field = build_mandala_particles(n_particles, w, h, motif_r,
                                        (w * 0.5, fig_cy), rng)
        fig_r = motif_r * 2.0
    else:
        field = build_shiva_particles(n_particles, w, h, fig_h,
                                      (w * 0.5, fig_cy), rng)
        fig_r = fig_h * 0.55
    field = build_formation(field, w, h, rng)
    if motif_tile is not None:
        fire = _build_snake_fire(n_fire, field["hood_center"], field["hood_radius"],
                                 rng, r_lo=1.02, r_hi=1.30)
    else:
        fire = _build_snake_fire(n_fire, field["hood_center"], field["hood_radius"], rng)

    fw, burst_times = _build_fireworks(duration, w, h, n_bursts, sparks_per, rng,
                                       avoid=(w * 0.5, fig_cy, fig_r * 1.15))

    # particles-per-layer-pixel varies with figure size, aspect and draft mode;
    # without this the same count packed into a smaller figure blows out white
    _ref_density = 2600.0 / (441.0 ** 2)
    _density = n_particles / max(1.0, ((fig_r * 2.0) / pdiv) ** 2)
    dens_gain = float(np.clip(_ref_density / _density, 0.30, 3.0))

    aura = _AuraField(aw, ah, w * 0.5 / adiv, fig_cy / adiv,
                      n_rays=12 if is_draft else 20)

    # ---------------- static layers ----------------
    bg = _make_background(w, h)
    ui_rgb = np.zeros((h, w, 3), np.float32)
    ui_a = np.zeros((h, w), np.float32)

    motif_xy = None
    if motif_tile is not None:
        mh, mw = motif_tile.shape[:2]
        motif_xy = (int(w * 0.5 - mw / 2), int(fig_cy - mh / 2))

    if watermark_path and os.path.exists(watermark_path):
        wm = _load_rgba(watermark_path, int(w * 0.18))
        if wm is not None:
            m = int(w * 0.035)
            _blend_tile_over_accum(ui_rgb, ui_a, wm,
                                   w - wm.shape[1] - m, h - wm.shape[0] - m)

    # CTA text blended LAST so it sits above everything in the UI stack
    if cta_text:
        font = _load_font(_DEVANAGARI_FONT_CANDIDATES, font_size)
        mask, _, skipped_syms = _draw_plain_mask(cta_text, font, text_cw, text_ch)
        if skipped_syms:
            _say("CTA text: no icon for %d symbol(s), dropped: %s"
                 % (len(skipped_syms), " ".join(skipped_syms)))
        tile = _mask_to_rgba(mask, CTA_TEXT_COLOR,
                             rim_rgb=CTA_RIM_COLOR, rim_strength=1.0,
                             glow_rgb=(255, 168, 44), glow_strength=0.45,
                             shadow_rgb=CTA_SHADOW_COLOR)
        _blend_tile_over_accum(ui_rgb, ui_a, tile,
                               (w - text_cw) // 2, int(h * text_cy) - text_ch // 2)

    ui_a3 = ui_a[..., None]
    has_ui = bool(ui_a.any())
    sub_tile = _make_subscribe_tile(btn_w, btn_h) if show_subscribe else None

    # glowing aura pulse hugging the motif (additive, so it never hides the art)
    halo = None
    if motif_tile is not None:
        yy, xx = np.mgrid[0:ph, 0:pw].astype(np.float32)
        dd = np.sqrt((xx - w * 0.5 / pdiv) ** 2 + (yy - fig_cy / pdiv) ** 2)
        dn = dd / max(1.0, (fig_r * 0.5) / pdiv)
        halo = ((np.clip(1.0 - dn, 0, 1) ** 2.1) * 1.15
                + np.exp(-((dn - 1.0) ** 2) / 0.05) * 0.65)
        halo = halo[..., None] * np.array([255.0, 186.0, 82.0], np.float32)

    rain = (_build_subscribe_rain(14 if is_draft else 34, w, h, short, rng, is_draft)
            if subscribe_rain else None)

    # ---------------- timing ----------------
    gravity = GRAVITY * (h / 1920.0)
    chime_start = min(FORM_TIME + 0.3, max(0.3, duration - 0.3))
    chime_times = [round(float(x), 3) for x in
                   np.arange(chime_start, max(chime_start + 0.01, duration - 0.2), 2.4)]
    if not chime_times:
        chime_times = [min(0.6, duration * 0.4)]

    sig_core = max(0.6, pw * 0.0016)
    sig_glow = max(2.5, pw * 0.014)
    trail_off = (0.0, 0.05) if is_draft else (0.0, 0.032, 0.064, 0.098, 0.135)
    trail_gain = (1.0, 0.42) if is_draft else (1.0, 0.62, 0.40, 0.24, 0.12)

    # ---------------- frame generator ----------------
    def make_frame(t):
        part = np.zeros((ph, pw, 3), np.float32)   # gets core+glow bloom
        amb = np.zeros((ph, pw, 3), np.float32)    # already-soft layers

        # ---- drone particles forming the Shiva figure ----
        px, py, prog = _particle_positions(field, t)
        formed = float(np.mean(prog))
        cols = _particle_colors(field, t, prog)
        weight = ((0.30 + 0.70 * prog)
                  * np.where(field["is_outline"], 82.0, 38.0) * dens_gain)
        _scatter(part, px / pdiv, py / pdiv, cols, weight, pw, ph)

        if halo is not None:
            amb += halo * (0.42 + 0.30 * math.sin(t * 2.0)) * min(1.0, 0.35 + formed)

        # ---- divine aura rays, once the figure settles ----
        if formed > 0.25:
            gain = (np.clip((formed - 0.25) / 0.75, 0, 1)
                    * (0.42 + 0.30 * math.sin(t * 1.7)))
            if gain > 0.01:
                amb += cv2.resize(aura.render(t, gain=float(gain)), (pw, ph),
                                  interpolation=cv2.INTER_LINEAR)

        # ---- snake hood fire, streaming toward the viewer ----
        fa = (t + fire["off"]) % fire["life"]
        fk = fa / fire["life"]
        fr = fire["r0"] + 0.5 * fire["acc"] * fa * fa
        fx = (fire["cx"] + np.cos(fire["ang"]) * fr
              + fire["wob"] * np.sin(fa * fire["wfq"] + fire["off"]))
        fy = fire["cy"] + np.sin(fire["ang"]) * fr * 0.7 + fire["vy"] * fa
        falpha = ((np.clip(1.0 - fk, 0, 1) ** 1.3) * (0.30 + 1.7 * fk)
                  * min(1.0, formed * 1.6))
        _scatter(part, fx / pdiv, fy / pdiv, fire["col"], falpha * 110.0, pw, ph)

        # ---- fireworks ----
        if fw["t0"].size:
            age = t - fw["t0"]
            alive = (age >= 0.0) & (age < fw["life"])
            if alive.any():
                a = age[alive]
                life = fw["life"][alive]
                for off, gain in zip(trail_off, trail_gain):
                    aa = np.maximum(a - off, 0.0)
                    damp = (1.0 - np.exp(-SPARK_DRAG * aa)) / SPARK_DRAG
                    qx = fw["x0"][alive] + fw["vx"][alive] * damp
                    qy = (fw["y0"][alive] + fw["vy"][alive] * damp
                          + 0.5 * gravity * aa * aa)
                    frac = np.clip(aa / life, 0, 1)
                    flick = 0.72 + 0.28 * np.sin(aa * 34.0 + fw["phase"][alive])
                    _scatter(part, qx / pdiv, qy / pdiv, fw["col"][alive],
                             ((1.0 - frac) ** 1.9) * flick * fw["siz"][alive] * gain * 108.0,
                             pw, ph)

        core = cv2.GaussianBlur(part, (0, 0), sigmaX=sig_core, sigmaY=sig_core)
        glow = cv2.GaussianBlur(part, (0, 0), sigmaX=sig_glow, sigmaY=sig_glow)
        frame = bg + cv2.resize(core * 1.15 + glow * 0.50 + amb, (w, h),
                                interpolation=cv2.INTER_LINEAR)

        # ---- explosion flash ----
        if burst_times:
            dt = t - np.array(burst_times, np.float32)
            m = (dt >= 0) & (dt < 0.35)
            if m.any():
                frame += float(np.sum(np.exp(-11.0 * dt[m]))) * 24.0

        # ---- subscribe rain, drifting down behind the artwork ----
        if rain is not None:
            for i in range(rain["kind"].size):
                tile = rain["tiles"][rain["kind"][i]]
                ry = (rain["y0"][i] + rain["speed"][i] * t) % rain["span"] - tile.shape[0]
                rx = (rain["x0"][i]
                      + rain["amp"][i] * math.sin(t * rain["frq"][i] + rain["phase"][i]))
                _paste_over_frame(frame, tile, rx, ry, gain=float(rain["gain"][i]))

        # ---- centre artwork, fading up as the drones take formation ----
        if motif_xy is not None:
            _paste_over_frame(frame, motif_tile, motif_xy[0], motif_xy[1],
                              gain=min(1.0, 0.12 + 1.5 * formed))

        # ---- UI ----
        if has_ui:
            frame = frame * (1.0 - ui_a3) + ui_rgb

        if sub_tile is not None:
            past = [c for c in chime_times if c <= t]
            since = (t - past[-1]) if past else 99.0
            kick = math.exp(-5.0 * since) if since < 2.0 else 0.0
            scale = 1.0 + 0.085 * kick + 0.018 * math.sin(t * 3.1)
            th_, tw_ = sub_tile.shape[:2]
            nw, nh = max(2, int(tw_ * scale)), max(2, int(th_ * scale))
            tile = (cv2.resize(sub_tile, (nw, nh), interpolation=cv2.INTER_LINEAR)
                    if abs(scale - 1.0) > 0.004 else sub_tile)
            if kick > 0.02:
                tile = tile.copy()
                tile[..., :3] = np.clip(tile[..., :3].astype(np.float32) *
                                        (1.0 + 0.35 * kick), 0, 255).astype(np.uint8)
            _paste_over_frame(frame, tile, (w - nw) / 2.0, h * btn_cy - nh / 2.0)

        return np.clip(frame, 0, 255).astype(np.uint8)

    clip = VideoClip(make_frame, duration=duration).set_fps(fps)

    if with_audio:
        try:
            # voice_text, if given, is spoken exactly as passed. Otherwise the
            # on-screen cta_text (which may carry decorative emoji for the
            # visual, like the sparkle/bell/flower CTA below) is cleaned of
            # emoji/symbols first - TTS engines read those badly or not at all.
            spoken = (voice_text if voice_text is not None
                     else _strip_for_speech(cta_text)) if with_voice else None
            wav = _synthesize_audio(duration, burst_times, chime_times,
                                    seed=int(seed) if seed is not None else 0,
                                    sr=22050 if is_draft else 44100,
                                    voice_text=spoken, voice_name=voice_name,
                                    gtts_lang=gtts_lang, tts_timeout_s=tts_timeout_s,
                                    on_status=_say)
            clip = clip.set_audio(AudioFileClip(wav).set_duration(duration))
        except Exception:
            pass   # audio is a bonus; never fail the segment for it

    return clip


# ==========================================================================
# CLI:  python climax.py [shorts|long]
# ==========================================================================
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "shorts"
    size = (1080, 1920) if mode == "shorts" else (1920, 1080)

    try:
        assert_glyph_mask_untouched()
        print("[ok] glyph-mask integrity test passed")
    except AssertionError as e:
        print("[warn] glyph test:", e)

    clip = generate_climax(
        duration=12,
        cta_text=DEFAULT_CTA_TEXT,
        watermark_path=None,
        target_size=size,
        is_draft=False,
    )
    out = "climax_preview_%s.mp4" % mode
    clip.write_videofile(out, fps=30, codec="libx264", audio_codec="aac",
                         preset="medium", threads=4)
    print("wrote", out)
