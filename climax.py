# -*- coding: utf-8 -*-
"""
climax.py - Baba Web Studio
Independent module that generates the ending "climax / outro" segment:
fireworks + confetti particle animation, centered Hindi/Devanagari CTA
text, and an optional channel logo/watermark overlay.

Public API
----------
generate_climax(duration, cta_text, watermark_path, target_size, is_draft=True) -> VideoClip

This module is self-contained: it does NOT import engine.py. It has its
own Devanagari-safe text rendering helper (Playwright/Chromium first,
PIL+raqm fallback, plain PIL as last resort) so it can be developed,
tested, and swapped independently of the main pipeline.
"""

import os
import io
import math
import random
import tempfile
import uuid

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from moviepy.editor import (
    VideoClip,
    ImageClip,
    CompositeVideoClip,
)

# --------------------------------------------------------------------------
# CONSTANTS
# --------------------------------------------------------------------------
CLIMAX_BG_TOP = (18, 8, 46)       # deep purple
CLIMAX_BG_BOTTOM = (60, 10, 70)   # magenta-ish
CTA_TEXT_COLOR = (255, 215, 0)    # gold
CTA_STROKE_COLOR = (0, 0, 0)

FIREWORK_COLORS = [
    (255, 80, 80), (255, 200, 60), (100, 220, 255),
    (150, 255, 120), (255, 120, 220), (255, 255, 255),
]
CONFETTI_COLORS = [
    (255, 99, 71), (255, 215, 0), (64, 224, 208),
    (186, 85, 211), (60, 179, 113), (255, 165, 0),
]

_DEVANAGARI_FONT_CANDIDATES = [
    "C:\\Windows\\Fonts\\Nirmala.ttf",
    "C:\\Windows\\Fonts\\Mangal.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # last-resort (no Devanagari glyphs)
]


# --------------------------------------------------------------------------
# DEVANAGARI-SAFE TEXT RENDERING
# --------------------------------------------------------------------------
def _resolve_font_path():
    for path in _DEVANAGARI_FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _render_text_png_via_playwright(text, font_size, color_hex, canvas_w, canvas_h):
    """
    Best-quality path: render HTML/CSS via headless Chromium so Devanagari
    conjuncts/matras shape correctly. Returns a PIL RGBA Image, or None if
    Playwright is unavailable / fails, so the caller can fall back.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    html = f"""
    <html>
      <head>
        <style>
          html, body {{
            margin: 0; padding: 0; background: transparent;
            width: {canvas_w}px; height: {canvas_h}px;
            display: flex; align-items: center; justify-content: center;
          }}
          #txt {{
            font-family: 'Noto Sans Devanagari', 'Nirmala UI', 'Mangal', sans-serif;
            font-size: {font_size}px;
            font-weight: 700;
            color: {color_hex};
            text-align: center;
            text-shadow: 0 0 8px rgba(0,0,0,0.85), 0 0 2px rgba(0,0,0,0.95);
            padding: 0 24px;
            line-height: 1.25;
          }}
        </style>
      </head>
      <body><div id="txt">{text}</div></body>
    </html>
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": canvas_w, "height": canvas_h})
            page.set_content(html)
            png_bytes = page.screenshot(omit_background=True)
            browser.close()
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        return img
    except Exception:
        return None


def _wrap_text_pil(draw, text, font, max_width):
    words = text.split(" ")
    lines, current = [], ""
    for w in words:
        trial = (current + " " + w).strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def _render_text_png_via_pil(text, font_size, color_rgb, canvas_w, canvas_h):
    """
    Fallback path: PIL. Tries the RAQM layout engine (correct Devanagari
    shaping) if the installed freetype/PIL build supports it; otherwise
    falls back to PIL's default layout (glyphs may render disconnected
    for complex conjuncts, but text will not be an empty box as long as
    a real Devanagari font file is found).
    """
    font_path = _resolve_font_path()
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font = None
    if font_path:
        try:
            font = ImageFont.truetype(font_path, font_size, layout_engine=ImageFont.LAYOUT_RAQM)
        except Exception:
            try:
                font = ImageFont.truetype(font_path, font_size)
            except Exception:
                font = None
    if font is None:
        font = ImageFont.load_default()

    max_width = int(canvas_w * 0.86)
    lines = _wrap_text_pil(draw, text, font, max_width)

    line_heights = []
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=font)
        line_heights.append(bbox[3] - bbox[1])
    total_h = sum(line_heights) + (len(lines) - 1) * int(font_size * 0.25)

    y = (canvas_h - total_h) / 2
    for ln, lh in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), ln, font=font)
        w = bbox[2] - bbox[0]
        x = (canvas_w - w) / 2
        # stroke/outline for legibility over animated background
        stroke_w = max(2, font_size // 18)
        draw.text((x, y), ln, font=font, fill=color_rgb + (255,),
                   stroke_width=stroke_w, stroke_fill=CTA_STROKE_COLOR + (255,))
        y += lh + int(font_size * 0.25)

    return img


def render_devanagari_text_image(text, font_size, color_rgb, canvas_w, canvas_h):
    """Try Chromium first, fall back to PIL. Always returns a PIL RGBA image."""
    hex_color = "#%02x%02x%02x" % color_rgb
    img = _render_text_png_via_playwright(text, font_size, hex_color, canvas_w, canvas_h)
    if img is None:
        img = _render_text_png_via_pil(text, font_size, color_rgb, canvas_w, canvas_h)
    return img


# --------------------------------------------------------------------------
# BACKGROUND CARD (vertical gradient)
# --------------------------------------------------------------------------
def _make_gradient_background(target_size):
    w, h = target_size
    top = np.array(CLIMAX_BG_TOP, dtype=np.float32)
    bottom = np.array(CLIMAX_BG_BOTTOM, dtype=np.float32)
    ramp = np.linspace(0, 1, h).reshape(h, 1)
    grad = (top * (1 - ramp) + bottom * ramp).astype(np.uint8)  # (h, 3)
    frame = np.repeat(grad[:, np.newaxis, :], w, axis=1)  # (h, w, 3)
    return frame  # static base frame, particles are drawn per-frame on top


# --------------------------------------------------------------------------
# PARTICLE SYSTEM (fireworks + confetti + floating balloons)
# --------------------------------------------------------------------------
class _Firework:
    __slots__ = ("x", "y0", "t_launch", "color", "n_sparks", "radius_max")

    def __init__(self, w, h, t_launch):
        self.x = random.uniform(w * 0.15, w * 0.85)
        self.y0 = random.uniform(h * 0.15, h * 0.45)
        self.t_launch = t_launch
        self.color = random.choice(FIREWORK_COLORS)
        self.n_sparks = random.randint(14, 22)
        self.radius_max = random.uniform(60, 110)


class _ConfettiPiece:
    __slots__ = ("x0", "speed_y", "speed_x_amp", "phase", "color", "size", "t_start")

    def __init__(self, w, t_start):
        self.x0 = random.uniform(0, w)
        self.speed_y = random.uniform(80, 160)
        self.speed_x_amp = random.uniform(15, 45)
        self.phase = random.uniform(0, 2 * math.pi)
        self.color = random.choice(CONFETTI_COLORS)
        self.size = random.randint(6, 12)
        self.t_start = t_start


def _build_particles(duration, target_size, is_draft):
    w, h = target_size
    n_fireworks = 3 if is_draft else 7
    n_confetti = 18 if is_draft else 45

    fireworks = [
        _Firework(w, h, t_launch=random.uniform(0, max(0.1, duration - 1.0)))
        for _ in range(n_fireworks)
    ]
    confetti = [
        _ConfettiPiece(w, t_start=random.uniform(0, max(0.1, duration * 0.6)))
        for _ in range(n_confetti)
    ]
    return fireworks, confetti


def _draw_particles_frame(base_frame, t, fireworks, confetti, target_size):
    w, h = target_size
    img = Image.fromarray(base_frame.copy())
    draw = ImageDraw.Draw(img, "RGBA")

    # Fireworks: expand + fade after launch
    for fw in fireworks:
        dt = t - fw.t_launch
        if dt < 0 or dt > 1.6:
            continue
        progress = dt / 1.6
        radius = fw.radius_max * min(1.0, progress * 1.4)
        alpha = max(0, int(255 * (1 - progress)))
        for i in range(fw.n_sparks):
            ang = (2 * math.pi * i) / fw.n_sparks
            sx = fw.x + radius * math.cos(ang)
            sy = fw.y0 + radius * math.sin(ang)
            r = 3 if progress < 0.7 else 2
            draw.ellipse(
                [sx - r, sy - r, sx + r, sy + r],
                fill=fw.color + (alpha,),
            )

    # Confetti: falls with gentle horizontal sway
    for c in confetti:
        dt = t - c.t_start
        if dt < 0:
            continue
        y = (c.speed_y * dt) % (h + 40) - 20
        x = c.x0 + c.speed_x_amp * math.sin(dt * 2.0 + c.phase)
        draw.rectangle(
            [x - c.size / 2, y - c.size / 2, x + c.size / 2, y + c.size / 2],
            fill=c.color + (230,),
        )

    return np.array(img.convert("RGB"))


# --------------------------------------------------------------------------
# PUBLIC API
# --------------------------------------------------------------------------
def generate_climax(duration, cta_text, watermark_path, target_size, is_draft=True):
    """
    Build and return the ending climax VideoClip.

    Parameters
    ----------
    duration        : float/int seconds for the climax segment
    cta_text        : Hindi/Devanagari CTA string (e.g. "धन्यवाद! लाइक और सब्सक्राइब करें")
    watermark_path  : path to a PNG channel logo, or None
    target_size     : (width, height) tuple matching the main video's output resolution
    is_draft        : if True, uses cheaper particle counts + lower fps for quick preview

    Returns
    -------
    moviepy VideoClip (already composited: background + particles + text + watermark),
    duration-limited, ready to be concatenated onto the main timeline in engine.py.
    """
    duration = max(1.0, float(duration))
    w, h = target_size
    fps = 12 if is_draft else 30

    base_frame = _make_gradient_background(target_size)
    fireworks, confetti = _build_particles(duration, target_size, is_draft)

    def make_frame(t):
        return _draw_particles_frame(base_frame, t, fireworks, confetti, target_size)

    bg_and_particles = VideoClip(make_frame, duration=duration).set_fps(fps)

    layers = [bg_and_particles]

    # Centered CTA text (Devanagari-safe)
    if cta_text:
        font_size = max(28, int(h * 0.055))
        text_canvas_w = int(w * 0.92)
        text_canvas_h = int(h * 0.32)
        text_img = render_devanagari_text_image(
            cta_text, font_size, CTA_TEXT_COLOR, text_canvas_w, text_canvas_h
        )
        text_np = np.array(text_img)  # RGBA
        text_clip = (
            ImageClip(text_np, transparent=True)
            .set_duration(duration)
            .set_position(("center", "center"))
        )
        # gentle pulse (scale 1.0 -> 1.05 -> 1.0) for a bit of life
        text_clip = text_clip.resize(lambda t: 1.0 + 0.04 * math.sin(t * 2.2))
        layers.append(text_clip)

    # Watermark / channel logo, bottom-right corner
    if watermark_path and os.path.exists(watermark_path):
        try:
            wm_target_w = int(w * 0.22)
            wm_clip = ImageClip(watermark_path).set_duration(duration)
            wm_clip = wm_clip.resize(width=wm_target_w)
            margin = int(w * 0.04)
            wm_clip = wm_clip.set_position(
                (w - wm_target_w - margin, h - wm_clip.h - margin)
            )
            layers.append(wm_clip)
        except Exception:
            # Watermark is decorative; never fail the whole climax segment for it.
            pass

    climax_clip = CompositeVideoClip(layers, size=target_size).set_duration(duration)
    return climax_clip
