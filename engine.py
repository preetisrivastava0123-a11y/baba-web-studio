# -*- coding: utf-8 -*-
"""
engine.py - Baba Web Studio
Production render pipeline. Consumes the payload dict built by app.py's
build_payload() and returns a path to the rendered .mp4.

Public API
----------
master_render_pipeline(
    payload: dict,
    loop_audio_path=None,
    is_mantra_mode=None,
    ticker_enabled=None,
    cta_type=None,
    custom_cta_text=None,
    **kwargs,
) -> str

Every new argument is OPTIONAL. If it is not passed explicitly, the value
is read out of the payload dict instead (see _resolve_runtime_options).
So both of these still work:

    engine.master_render_pipeline(payload)
    engine.master_render_pipeline(payload, is_mantra_mode=True,
                                  loop_audio_path="/tmp/mantra.mp3")

WHAT CHANGED IN THIS VERSION (1 / 2 / 3 / 4 / 5 / 6)
----------------------------------------------------------------------
(1) SIGNATURE - master_render_pipeline() now accepts loop_audio_path,
    is_mantra_mode, ticker_enabled, cta_type, custom_cta_text plus
    **kwargs for forward compatibility. _resolve_runtime_options()
    merges explicit kwargs with payload keys (kwargs win).

(2) AUDIO - when is_mantra_mode is True, the 10-15 sec mantra clip is
    looped across the FULL video duration and composited alongside the
    Track 3 background music. Volume balancing: the background music is
    ducked to BG_DUCK_VOLUME_WITH_MANTRA so the mantra voice stays clear
    on top. See build_mantra_loop_layer() and build_final_audio().

(3) TICKER - the ticker overlay is only composited when ticker_enabled
    is True. app.py's ticker box is now fully INDEPENDENT of the
    Script text (no more fall-back to the script) - it is enabled only
    when track5.ticker_text itself is non-empty. This module does not
    need to know why the ticker is on/off, it just honours the flag +
    text that app.py already resolved.

(4) CLIMAX - cta_type and custom_cta_text are now forwarded to
    climax.generate_climax() so climax.py can pick the right 3D/shimmer
    text style and the right TTS voice. A TypeError fallback keeps older
    climax.py signatures working.

(5) MANTRA ON-SCREEN TEXT (new) - app.py's Track 5 now has a
    'mantra_text' field that is completely independent of the mantra
    AUDIO loop, the subtitles, the ticker, and the CTA. When present, it
    is rendered as a static on-screen banner (own style/color/size) for
    the full duration of the main video. See build_mantra_text_overlay().

(6) QUALITY - app.py now only ever sends "720p" (draft) or the user's
    chosen "720p"/"1080p" (final download quality, default 1080p). The
    old hard-coded "360p" draft tier is gone from app.py, but this
    module still recognises it in TARGET_SIZES for backward
    compatibility with any older payload that still sends it.

(7) SUBTITLE + SCRIPT-FILE FIX (bug fix, not an app.py change) - two
    gaps were found while syncing this file with app.py and are now
    fixed:
      - Subtitles were never actually drawn on screen. app.py has
        always collected subtitle_font_color/subtitle_font_size, but no
        function in this file ever rendered them. build_subtitle_overlay()
        now does, as a static word-wrapped caption (no per-word timing
        data exists anywhere in the payload to sync it line-by-line).
      - track5.script_file_path (an uploaded PDF/DOCX) was accepted into
        the payload but never read - only the typed script_text box
        worked. resolve_script_text() now extracts text from the file
        when the text box is empty, and both the AI voice and the new
        subtitle overlay use it.

NOTE ON MOVIEPY VERSION
----------------------------------------------------------------------
This module targets MoviePy 1.x (`from moviepy.editor import ...`,
`.set_duration()`, `.fx(volumex, ...)`). If you ever upgrade to
MoviePy 2.x these imports and every .set_*/.fx() call must change.
Pin it in requirements.txt: moviepy==1.0.3

NOTE ON PAYLOAD SHAPE
----------------------------------------------------------------------
app.py puts climax fields at the TOP LEVEL of the payload
(payload['enable_climax'], payload['climax_duration'],
payload['climax_text'], payload['climax_watermark_path']). Newer app.py
versions ALSO add a nested payload['climax'] dict. This module reads the
top-level keys first and falls back to the nested dict, so both app.py
versions work.

DEVANAGARI TEXT
----------------------------------------------------------------------
PIL's default text layout does not shape Devanagari conjuncts/matras
correctly. This module renders all Hindi text (subtitles/ticker/mantra
text) through a Chromium/Playwright pass when available, falling back
to PIL + RAQM, then plain PIL as a last resort.
----------------------------------------------------------------------
"""

import os
import io
import asyncio
import tempfile
import traceback
import uuid

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from moviepy.editor import (
    VideoFileClip,
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    CompositeAudioClip,
    concatenate_videoclips,
    concatenate_audioclips,
    ColorClip,
)
from moviepy.audio.fx.all import audio_loop, volumex
from moviepy.video.fx.all import resize as vfx_resize  # noqa: F401 (available if needed)

import climax  # sibling module - handles the ending segment

# --------------------------------------------------------------------------
# CONSTANTS
# --------------------------------------------------------------------------
OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "baba_web_studio_renders")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# (ratio, quality) -> (width, height)
# "360p" is kept only for backward compatibility with older payloads;
# current app.py never sends it (draft = 720p, final = 720p/1080p).
TARGET_SIZES = {
    ("Shorts (9:16)", "1080p"): (1080, 1920),
    ("Shorts (9:16)", "720p"): (720, 1280),
    ("Shorts (9:16)", "360p"): (360, 640),
    ("Long (16:9)", "1080p"): (1920, 1080),
    ("Long (16:9)", "720p"): (1280, 720),
    ("Long (16:9)", "360p"): (640, 360),
}

TICKER_SPEED_PX_PER_SEC = {"Slow": 60, "Medium": 120, "Fast": 200}

MUSIC_MODE_VOLUME = {
    "🎵 Song": 1.0,
    "🎻 Instrument": 0.85,
    "🍃 Background Music": 0.55,
}

# --- (2) VOLUME BALANCING CONSTANTS -------------------------------------
# The mantra loop is a VOICE layer, so it sits on top and the background
# music gets ducked underneath it. Tune these two numbers if the mix
# sounds off: raise MANTRA_LOOP_VOLUME to make the mantra louder, or
# lower BG_DUCK_VOLUME_WITH_MANTRA to push the music further down.
MANTRA_LOOP_VOLUME = 0.95          # mantra voice level when mantra mode is ON
BG_DUCK_VOLUME_WITH_MANTRA = 0.30  # background music multiplier when mantra is ON
VOICE_DUCK_VOLUME_WITH_MANTRA = 0.85  # narration level if BOTH voice + mantra exist

# Map app.py's BUILTIN_SFX_LIBRARY labels -> local asset files.
BUILTIN_SFX_ASSETS = {
    "शंख (Shankh)": "assets/sfx/shankh.mp3",
    "डमरू (Damru)": "assets/sfx/damru.mp3",
    "घंटी (Ghanti)": "assets/sfx/ghanti.mp3",
    "सीटी (Whistle)": "assets/sfx/whistle.mp3",
    "तालियां (Applause)": "assets/sfx/applause.mp3",
}

# --- (4) CTA TYPE CONSTANTS ---------------------------------------------
CTA_TYPE_DEFAULT = "Default CTA"
CTA_TYPE_CUSTOM = "Custom CTA"
DEFAULT_CTA_TEXT = (
    "\u2728 वीडियो देखने के लिए धन्यवाद! \u2728 "
    "\U0001F44D चैनल को लाइक और सब्सक्राइब करें। \U0001F514 "
    "\U0001F64F कमेंट में 'हर हर महादेव' जरूर लिखें! \U0001F549\ufe0f "
    "\U0001F338 आपका दिन शुभ हो! \U0001F33A"
)

# --- (5) MANTRA ON-SCREEN TEXT STYLE PRESETS ----------------------------
# Matches app.py's MANTRA_TEXT_STYLES options exactly. Each preset only
# controls how the mantra TEXT looks - it has nothing to do with the
# mantra AUDIO loop.
MANTRA_TEXT_STYLE_PRESETS = {
    "Classic Bold": {
        "font_family": "'Noto Sans Devanagari', 'Nirmala UI', 'Mangal', sans-serif",
        "font_weight": "800",
        "font_style": "normal",
        "letter_spacing": "1px",
        "text_shadow": "0 0 10px rgba(0,0,0,0.85), 0 0 2px rgba(0,0,0,0.9)",
        "pil_stroke_color": (0, 0, 0),
        "pil_stroke_ratio": 20,
    },
    "Elegant Script": {
        "font_family": "'Noto Sans Devanagari', cursive, 'Mangal', sans-serif",
        "font_weight": "500",
        "font_style": "italic",
        "letter_spacing": "0.5px",
        "text_shadow": "0 0 8px rgba(0,0,0,0.7)",
        "pil_stroke_color": (20, 20, 20),
        "pil_stroke_ratio": 28,
    },
    "Modern Sans": {
        "font_family": "'Noto Sans Devanagari', 'Nirmala UI', sans-serif",
        "font_weight": "600",
        "font_style": "normal",
        "letter_spacing": "2px",
        "text_shadow": "0 2px 6px rgba(0,0,0,0.6)",
        "pil_stroke_color": (0, 0, 0),
        "pil_stroke_ratio": 24,
    },
    "Traditional Devanagari Calligraphy": {
        "font_family": "'Noto Sans Devanagari', 'Nirmala UI', 'Mangal', serif",
        "font_weight": "800",
        "font_style": "normal",
        "letter_spacing": "0px",
        "text_shadow": "0 0 16px rgba(255,215,0,0.55), 0 0 4px rgba(0,0,0,0.9)",
        "pil_stroke_color": (120, 72, 0),
        "pil_stroke_ratio": 16,
    },
}
DEFAULT_MANTRA_TEXT_STYLE = "Classic Bold"

_DEVANAGARI_FONT_CANDIDATES = [
    "C:\\Windows\\Fonts\\Nirmala.ttf",
    "C:\\Windows\\Fonts\\Mangal.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # last resort, no Devanagari glyphs
]


def _log(msg):
    print(f"[engine.py] {msg}")


# ==========================================================================
# (1) RUNTIME OPTIONS RESOLVER - explicit kwargs win, payload is fallback
# ==========================================================================
def _resolve_runtime_options(payload, loop_audio_path, is_mantra_mode,
                             ticker_enabled, cta_type, custom_cta_text):
    """
    Builds one options dict from (a) explicitly passed arguments and
    (b) the payload. An explicitly passed argument always wins; None
    means "not passed, look in the payload".

    Returns a plain dict so every downstream function takes one object
    instead of six loose arguments.
    """
    track5 = payload.get("track5", {}) or {}
    nested_climax = payload.get("climax", {}) or {}

    # --- loop audio path (mantra AUDIO only - unrelated to mantra text) ---
    if loop_audio_path is None:
        loop_audio_path = (
            payload.get("audio_file_path")
            or track5.get("mantra_audio_path")
            or nested_climax.get("audio_file_path")
        )

    # --- mantra / loop mode ---
    if is_mantra_mode is None:
        is_mantra_mode = bool(
            payload.get("is_loop_mode")
            or track5.get("mantra_is_loop_mode")
            or nested_climax.get("is_loop_mode")
        )
    is_mantra_mode = bool(is_mantra_mode)

    # A loop mode with no file is meaningless - turn it off rather than
    # crashing deeper in the audio mixer.
    if is_mantra_mode and not (loop_audio_path and os.path.exists(loop_audio_path)):
        _log("NOTE: is_mantra_mode=True lekin valid loop_audio_path nahi mila - mantra mode OFF kiya ja raha hai.")
        is_mantra_mode = False
        loop_audio_path = None

    # --- ticker enabled ---
    # app.py's ticker box is fully independent of the Script now: it is
    # enabled only when the ticker box itself has text. We simply trust
    # the flag app.py already computed; the legacy fallback below only
    # kicks in for payloads from an OLD app.py that never set the flag.
    if ticker_enabled is None:
        if "ticker_enabled" in payload:
            ticker_enabled = payload.get("ticker_enabled")
        elif "ticker_enabled" in track5:
            ticker_enabled = track5.get("ticker_enabled")
        else:
            # Legacy payloads have no flag: fall back to the old behaviour
            # (ticker shows whenever ticker_text is non-empty).
            ticker_enabled = bool((track5.get("ticker_text") or "").strip())
    ticker_enabled = bool(ticker_enabled)

    # --- CTA type ---
    if cta_type is None:
        cta_type = (
            track5.get("cta_mode")
            or nested_climax.get("cta_mode")
            or CTA_TYPE_DEFAULT
        )

    # --- custom CTA text ---
    if custom_cta_text is None:
        custom_cta_text = track5.get("custom_cta_text") or ""
    custom_cta_text = (custom_cta_text or "").strip()

    # --- resolved final CTA text that climax.py will actually render ---
    if cta_type == CTA_TYPE_CUSTOM and custom_cta_text:
        resolved_cta_text = custom_cta_text
    else:
        # payload['climax_text'] is what app.py already resolved; trust it,
        # then the nested dict, then the hardcoded default.
        resolved_cta_text = (
            (payload.get("climax_text") or "").strip()
            or (nested_climax.get("cta_text") or "").strip()
            or DEFAULT_CTA_TEXT
        )

    # --- (5) mantra on-screen TEXT - independent of everything above ---
    mantra_text = (track5.get("mantra_text") or "").strip()
    mantra_text_style = track5.get("mantra_text_style") or DEFAULT_MANTRA_TEXT_STYLE
    if mantra_text_style not in MANTRA_TEXT_STYLE_PRESETS:
        mantra_text_style = DEFAULT_MANTRA_TEXT_STYLE
    mantra_text_color = track5.get("mantra_text_color") or "#FFD700"
    try:
        mantra_text_size = int(track5.get("mantra_text_size") or 48)
    except (TypeError, ValueError):
        mantra_text_size = 48

    options = {
        "loop_audio_path": loop_audio_path,
        "is_mantra_mode": is_mantra_mode,
        "ticker_enabled": ticker_enabled,
        "cta_type": cta_type,
        "custom_cta_text": custom_cta_text,
        "resolved_cta_text": resolved_cta_text,
        "mantra_text": mantra_text,
        "mantra_text_style": mantra_text_style,
        "mantra_text_color": mantra_text_color,
        "mantra_text_size": mantra_text_size,
    }
    _log(f"Runtime options: {options}")
    return options


# ==========================================================================
# DEVANAGARI-SAFE TEXT RENDERING
# ==========================================================================
def _resolve_font_path(font_config=None):
    candidates = list((font_config or {}).get("preferred_fonts_resolved", []))
    if font_config:
        win_dir = font_config.get("windows_font_dir", "C:\\Windows\\Fonts")
        for fname in font_config.get("preferred_fonts", []):
            candidates.append(os.path.join(win_dir, fname))
        candidates.extend(font_config.get("linux_font_candidates", []))
    candidates.extend(_DEVANAGARI_FONT_CANDIDATES)
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _render_text_png_via_playwright(text, font_size, color_hex, canvas_w, canvas_h,
                                    bg_color_hex=None, align="center", style_name=None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    background_css = bg_color_hex if bg_color_hex else "transparent"
    style_preset = MANTRA_TEXT_STYLE_PRESETS.get(style_name, {}) if style_name else {}
    font_family = style_preset.get(
        "font_family", "'Noto Sans Devanagari', 'Nirmala UI', 'Mangal', sans-serif"
    )
    font_weight = style_preset.get("font_weight", "600")
    font_style = style_preset.get("font_style", "normal")
    letter_spacing = style_preset.get("letter_spacing", "0px")
    text_shadow = style_preset.get("text_shadow", "0 0 6px rgba(0,0,0,0.8)")

    html = f"""
    <html><head><style>
      html, body {{
        margin: 0; padding: 0; background: {background_css};
        width: {canvas_w}px; height: {canvas_h}px;
        display: flex; align-items: center; justify-content: {align};
      }}
      #txt {{
        font-family: {font_family};
        font-size: {font_size}px; font-weight: {font_weight};
        font-style: {font_style}; letter-spacing: {letter_spacing};
        color: {color_hex};
        white-space: nowrap; padding: 0 16px;
        text-shadow: {text_shadow};
      }}
    </style></head>
    <body><div id="txt">{text}</div></body></html>
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": canvas_w, "height": canvas_h})
            page.set_content(html)
            png_bytes = page.screenshot(omit_background=(bg_color_hex is None))
            browser.close()
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except Exception:
        return None


def _render_text_png_via_pil(text, font_size, color_rgb, canvas_w, canvas_h,
                             bg_rgba=(0, 0, 0, 0), font_config=None, style_name=None):
    font_path = _resolve_font_path(font_config)
    img = Image.new("RGBA", (canvas_w, canvas_h), bg_rgba)
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
        _log("WARNING: no Devanagari-capable font found; text may render as empty boxes.")
        font = ImageFont.load_default()

    style_preset = MANTRA_TEXT_STYLE_PRESETS.get(style_name, {}) if style_name else {}
    stroke_color = style_preset.get("pil_stroke_color", (0, 0, 0))
    stroke_ratio = style_preset.get("pil_stroke_ratio", 20)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (canvas_w - tw) / 2
    y = (canvas_h - th) / 2
    stroke_w = max(1, font_size // stroke_ratio)
    draw.text((x, y), text, font=font, fill=color_rgb + (255,),
              stroke_width=stroke_w, stroke_fill=stroke_color + (255,))
    return img


def render_hindi_text_image(text, font_size, color_rgb, canvas_w, canvas_h,
                            bg_color_rgb=None, font_config=None, style_name=None):
    """Chromium first (correct shaping), PIL+raqm fallback. Returns RGBA PIL Image.

    style_name (optional) selects one of MANTRA_TEXT_STYLE_PRESETS to control
    font weight/slant/letter-spacing/glow. Leave as None for the plain
    ticker/subtitle look.
    """
    if not text:
        return Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    hex_color = "#%02x%02x%02x" % color_rgb
    bg_hex = ("#%02x%02x%02x" % bg_color_rgb) if bg_color_rgb else None
    img = _render_text_png_via_playwright(
        text, font_size, hex_color, canvas_w, canvas_h, bg_hex, style_name=style_name
    )
    if img is None:
        bg_rgba = (bg_color_rgb + (255,)) if bg_color_rgb else (0, 0, 0, 0)
        img = _render_text_png_via_pil(text, font_size, color_rgb, canvas_w, canvas_h,
                                       bg_rgba, font_config, style_name=style_name)
    return img


def _hex_to_rgb(hex_str, default=(255, 255, 255)):
    try:
        hex_str = hex_str.lstrip("#")
        return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


# ==========================================================================
# TRACK 1 + TRACK 2 - VISUAL TIMELINE
# ==========================================================================
def _apply_ken_burns(image_clip, duration, zoom_amt=0.12):
    """Slow zoom-in over the clip's duration."""
    def scale_at(t):
        progress = t / max(duration, 0.001)
        return 1.0 + zoom_amt * progress
    return image_clip.resize(scale_at)


def _build_visual_clip_for_file(file_entry, target_size, ken_burns):
    path = file_entry["path"]
    ftype = file_entry["type"]
    w, h = target_size

    if ftype == "video":
        clip = VideoFileClip(path, audio=False)
        start = float(file_entry.get("start_sec", 0.0))
        end = float(file_entry.get("end_sec", 0.0))
        if end > start:
            clip = clip.subclip(start, min(end, clip.duration))
        clip = clip.resize((w, h))
        return clip
    else:
        duration = float(file_entry.get("image_duration", 5))
        clip = ImageClip(path).set_duration(duration)
        clip = clip.resize((w, h))
        if ken_burns:
            clip = _apply_ken_burns(clip, duration)
            # re-center after zoom so it doesn't drift off-canvas
            clip = clip.set_position(("center", "center"))
            clip = CompositeVideoClip(
                [ColorClip(target_size, color=(0, 0, 0)).set_duration(duration), clip],
                size=target_size,
            ).set_duration(duration)
        return clip


def build_track1_timeline(track1_payload, target_size):
    files = track1_payload.get("files", [])
    ken_burns = bool(track1_payload.get("ken_burns", True))
    if not files:
        raise ValueError("Track 1 mein koi file nahi hai (mandatory track).")

    clips = []
    for f in sorted(files, key=lambda x: x["order"]):
        try:
            clips.append(_build_visual_clip_for_file(f, target_size, ken_burns))
        except Exception as e:
            _log(f"WARNING: Track1 file skip ho gayi ({f.get('path')}): {e}")

    if not clips:
        raise ValueError("Track 1 ki koi bhi file successfully load nahi hui.")

    return concatenate_videoclips(clips, method="compose")


def overlay_track2_clips(base_video, track2_payload, target_size):
    """Track 2 clips overlay the main timeline as full-frame inserts during
    their specified [start_sec, end_sec] window (intro/meme/side clips)."""
    clips_data = track2_payload.get("clips", [])
    if not clips_data:
        return base_video

    layers = [base_video]
    for c in sorted(clips_data, key=lambda x: x["order"]):
        try:
            start = float(c["start_sec"])
            end = float(c["end_sec"])
            if end <= start:
                continue
            window = min(end, base_video.duration) - start
            if window <= 0:
                continue
            overlay = VideoFileClip(c["path"], audio=False).resize(target_size)
            if overlay.duration > window:
                overlay = overlay.subclip(0, window)
            overlay = overlay.set_start(start).set_duration(overlay.duration)
            layers.append(overlay)
        except Exception as e:
            _log(f"WARNING: Track2 clip skip ho gayi ({c.get('path')}): {e}")

    if len(layers) == 1:
        return base_video
    return CompositeVideoClip(layers, size=target_size).set_duration(base_video.duration)


# ==========================================================================
# (3) TRACK 5 - CONDITIONAL TICKER OVERLAY (bottom scrolling, Devanagari-safe)
# ==========================================================================
def build_ticker_overlay(track5_payload, target_size, total_duration, font_config,
                         ticker_enabled=True):
    """
    Returns a scrolling ticker VideoClip, or None when the ticker should
    be skipped entirely.

    Skipped when:
      - ticker_enabled is False (the ticker box in app.py was left empty -
        the ticker is fully independent of the Script now, it is NOT
        auto-disabled by narration and it does NOT fall back to the
        script text either), OR
      - ticker_text is empty/None.
    """
    if not ticker_enabled:
        _log("Ticker skip: ticker_enabled=False (ticker box khali chhoda gaya).")
        return None

    ticker_text = (track5_payload.get("ticker_text") or "").strip()
    if not ticker_text:
        _log("Ticker skip: ticker_text khali hai.")
        return None

    w, h = target_size
    band_h = max(36, int(h * 0.045))
    font_size = int(band_h * 0.62)
    bg_rgb = _hex_to_rgb(track5_payload.get("ticker_bg_color") or "#000000", (0, 0, 0))
    speed = TICKER_SPEED_PX_PER_SEC.get(track5_payload.get("ticker_speed") or "Medium", 120)

    # Render the ticker text once at natural width (repeated with spacing so
    # the scroll never shows a gap), then scroll a window over that strip.
    spacer = "      •      "
    repeated_text = (ticker_text + spacer) * 6
    strip_w = max(w * 3, len(repeated_text) * int(font_size * 0.62))

    strip_img = render_hindi_text_image(
        repeated_text, font_size, (255, 255, 255), strip_w, band_h,
        bg_color_rgb=bg_rgb, font_config=font_config,
    )
    strip_np = np.array(strip_img.convert("RGB"))  # (band_h, strip_w, 3)
    strip_w_actual = strip_np.shape[1]

    def make_frame(t):
        offset = int((speed * t) % strip_w_actual)
        # build a window of width w starting at offset, wrapping around
        if offset + w <= strip_w_actual:
            window = strip_np[:, offset:offset + w]
        else:
            first_part = strip_np[:, offset:]
            remaining = w - first_part.shape[1]
            second_part = strip_np[:, :remaining]
            window = np.concatenate([first_part, second_part], axis=1)
        return window

    from moviepy.editor import VideoClip
    ticker_clip = VideoClip(make_frame, duration=total_duration).set_fps(20)
    ticker_clip = ticker_clip.set_position((0, h - band_h))
    _log(f"Ticker overlay banaya (speed={speed}px/s, band_h={band_h}px).")
    return ticker_clip


# ==========================================================================
# (5) TRACK 5 - MANTRA ON-SCREEN TEXT OVERLAY (independent of mantra audio)
# ==========================================================================
def build_mantra_text_overlay(track5_payload, target_size, total_duration, font_config,
                              options=None):
    """
    Renders the optional mantra TEXT (e.g. "ॐ नमः शिवाय") as a static
    banner near the top of the frame, for the full duration of the main
    video.

    This is completely independent of:
      - the mantra AUDIO loop (build_mantra_loop_layer) - text can be
        shown with or without the audio, and vice versa,
      - the subtitles (spoken script),
      - the bottom ticker,
      - the climax CTA text.

    Returns an ImageClip, or None when there is no mantra text to show.
    """
    if options is not None:
        mantra_text = options.get("mantra_text", "")
        style_name = options.get("mantra_text_style", DEFAULT_MANTRA_TEXT_STYLE)
        color_hex = options.get("mantra_text_color", "#FFD700")
        font_size = int(options.get("mantra_text_size", 48))
    else:
        mantra_text = (track5_payload.get("mantra_text") or "").strip()
        style_name = track5_payload.get("mantra_text_style") or DEFAULT_MANTRA_TEXT_STYLE
        color_hex = track5_payload.get("mantra_text_color") or "#FFD700"
        font_size = int(track5_payload.get("mantra_text_size") or 48)

    mantra_text = (mantra_text or "").strip()
    if not mantra_text:
        _log("Mantra text overlay skip: mantra_text khali hai.")
        return None

    if style_name not in MANTRA_TEXT_STYLE_PRESETS:
        style_name = DEFAULT_MANTRA_TEXT_STYLE

    w, h = target_size
    color_rgb = _hex_to_rgb(color_hex, (255, 215, 0))
    band_h = max(int(font_size * 1.9), 64)

    img = render_hindi_text_image(
        mantra_text, font_size, color_rgb, w, band_h,
        bg_color_rgb=None, font_config=font_config, style_name=style_name,
    )
    img_np = np.array(img)  # RGBA, (band_h, w, 4)

    mantra_clip = ImageClip(img_np, transparent=True).set_duration(total_duration)
    # Sit in the upper area of the frame (~8% down) so it never collides
    # with subtitles (usually lower-third) or the bottom ticker.
    mantra_clip = mantra_clip.set_position(("center", int(h * 0.08)))
    _log(f"Mantra text overlay banaya: style={style_name} color={color_hex} "
         f"size={font_size} text='{mantra_text}'")
    return mantra_clip


# ==========================================================================
# (7) TRACK 5 - SUBTITLE OVERLAY (was completely missing before - the
# Script text has always been used for the AI voice, but nothing ever
# actually drew it on screen as a subtitle even though app.py collects
# subtitle_font_color/subtitle_font_size for exactly this purpose).
# ==========================================================================
def _render_subtitle_png_pil(text, font_size, color_rgb, canvas_w, canvas_h, font_config=None):
    """Multi-line, center-aligned Devanagari-safe caption via PIL + RAQM.

    (Subtitles need line-wrapping, so they use their own PIL renderer
    rather than the single-line render_hindi_text_image() used for the
    ticker/mantra text.)
    """
    font_path = _resolve_font_path(font_config)
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
        _log("WARNING: no Devanagari-capable font found for subtitles; may render as empty boxes.")
        font = ImageFont.load_default()

    bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=8)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (canvas_w - tw) / 2
    y = (canvas_h - th) / 2
    stroke_w = max(1, font_size // 18)
    draw.multiline_text(
        (x, y), text, font=font, fill=color_rgb + (255,), align="center", spacing=8,
        stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255),
    )
    return img


def build_subtitle_overlay(track5_payload, target_size, total_duration, font_config,
                           ticker_enabled=False):
    """
    Renders the resolved Script text (typed, or extracted from an
    uploaded PDF/DOCX - see resolve_script_text) as an on-screen
    subtitle caption for the full duration of the main video.

    NOTE: there is no per-word/per-line timing data anywhere in the
    payload, so this shows a single word-wrapped caption throughout the
    video rather than time-synced subtitle lines. If line-by-line timed
    subtitles are needed later, this is the function to extend (it would
    need timestamps from the TTS engine or a forced-alignment step).

    Returns an ImageClip, or None when there is no script text at all.
    """
    script_text = resolve_script_text(track5_payload)
    if not script_text:
        return None

    w, h = target_size
    font_size = int(track5_payload.get("subtitle_font_size") or 40)
    color_rgb = _hex_to_rgb(track5_payload.get("subtitle_font_color") or "#FFFFFF", (255, 255, 255))

    import textwrap
    max_chars_per_line = max(10, int(w / max(1, int(font_size * 0.55))))
    lines = textwrap.wrap(script_text, width=max_chars_per_line)
    if not lines:
        return None
    # Cap to 4 lines on screen at once so a long script doesn't take over
    # the frame - it's a caption, not the whole script dumped on screen.
    wrapped_text = "\n".join(lines[:4])

    line_count = wrapped_text.count("\n") + 1
    band_h = int(font_size * 1.35 * line_count) + 24

    img = _render_subtitle_png_pil(wrapped_text, font_size, color_rgb, w, band_h, font_config)
    img_np = np.array(img)

    subtitle_clip = ImageClip(img_np, transparent=True).set_duration(total_duration)

    # Sit just above the bottom ticker band when the ticker is active, so
    # the two never overlap; otherwise sit near the bottom of the frame.
    reserved_bottom = max(36, int(h * 0.045)) if ticker_enabled else 0
    y_pos = max(0, h - reserved_bottom - band_h - 16)
    subtitle_clip = subtitle_clip.set_position(("center", y_pos))

    _log(f"Subtitle overlay banaya ({line_count} lines, font_size={font_size}).")
    return subtitle_clip


# ==========================================================================
# (7) SCRIPT TEXT RESOLUTION - typed text, or extracted from PDF/DOCX
# ==========================================================================
def _extract_text_from_pdf(path):
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except ImportError:
        try:
            # fallback if only PyPDF2 is installed instead of pypdf
            import PyPDF2
            reader = PyPDF2.PdfReader(path)
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as e:
            _log(f"WARNING: PDF text extract fail (pypdf/PyPDF2 nahi mila ya error): {e}")
            return ""
    except Exception as e:
        _log(f"WARNING: PDF text extract fail: {e}")
        return ""


def _extract_text_from_docx(path):
    try:
        import docx  # python-docx
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        _log(f"WARNING: DOCX text extract fail: {e}")
        return ""


def resolve_script_text(track5_payload):
    """
    app.py lets the user EITHER type the script OR upload a PDF/DOCX file
    (script_file_path). Typed text always wins; if it's empty, this reads
    and extracts text from the uploaded file so the AI voice + subtitle
    still get the script even when nothing was typed.
    """
    script_text = (track5_payload.get("script_text") or "").strip()
    if script_text:
        return script_text

    file_path = track5_payload.get("script_file_path")
    if not file_path or not os.path.exists(file_path):
        return ""

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        extracted = _extract_text_from_pdf(file_path)
    elif ext == ".docx":
        extracted = _extract_text_from_docx(file_path)
    else:
        _log(f"WARNING: script_file_path ka extension pehchana nahi gaya: {ext}")
        extracted = ""

    extracted = (extracted or "").strip()
    if extracted:
        _log(f"Script file ({ext}) se text extract hua - {len(extracted)} characters.")
    else:
        _log(f"WARNING: script file se koi text extract nahi hua: {file_path}")
    return extracted


# ==========================================================================
# TRACK 5 - VOICE (AI via Edge-TTS, or uploaded voiceover)
# ==========================================================================
async def _edge_tts_save(text, voice_short, out_path):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice_short)
    await communicate.save(out_path)


def generate_ai_voice_clip(script_text, ai_voice_label):
    """Returns an AudioFileClip or None if generation fails/unavailable."""
    if not script_text or not script_text.strip():
        return None
    try:
        voice_short = ai_voice_label.split(" ")[0]  # e.g. "hi-IN-MadhurNeural"
        out_path = os.path.join(tempfile.gettempdir(), f"ai_voice_{uuid.uuid4().hex}.mp3")
        asyncio.run(_edge_tts_save(script_text, voice_short, out_path))
        if os.path.exists(out_path):
            return AudioFileClip(out_path)
    except Exception as e:
        _log(f"WARNING: AI voice generation fail hui: {e}")
    return None


def build_voice_clip(track5_payload):
    script_text = resolve_script_text(track5_payload)
    voice_source = track5_payload.get("voice_source")
    if voice_source == "AI Voice (Edge-TTS)":
        return generate_ai_voice_clip(
            script_text,
            track5_payload.get("ai_voice") or "hi-IN-MadhurNeural (पुरुष आवाज़)",
        )
    else:
        manual_path = track5_payload.get("manual_voice_path")
        if manual_path and os.path.exists(manual_path):
            try:
                return AudioFileClip(manual_path)
            except Exception as e:
                _log(f"WARNING: manual voiceover load fail hui: {e}")
        return None


# ==========================================================================
# (2) MANTRA LOOP LAYER - 10-15 sec clip looped across the whole video
# ==========================================================================
def build_mantra_loop_layer(loop_audio_path, total_duration,
                            volume=MANTRA_LOOP_VOLUME):
    """
    Takes the short mantra/voice clip and loops it until it covers the
    full video duration, then trims it to an exact match.

    Returns an AudioClip starting at t=0, or None if the file can't be
    loaded (never raises - a broken mantra file must not kill the render).
    """
    if not loop_audio_path or not os.path.exists(loop_audio_path):
        _log(f"WARNING: mantra audio file nahi mili, mantra layer skip: {loop_audio_path}")
        return None

    try:
        mantra_clip = AudioFileClip(loop_audio_path)
        src_duration = mantra_clip.duration
        if not src_duration or src_duration <= 0:
            _log("WARNING: mantra audio ki duration 0 hai, skip kiya ja raha hai.")
            return None

        if src_duration < total_duration:
            loop_count = int(total_duration // src_duration) + 1
            _log(f"Mantra loop: {src_duration:.1f}s ko {loop_count}x repeat karke "
                 f"{total_duration:.1f}s tak bhara ja raha hai.")
            mantra_clip = mantra_clip.fx(audio_loop, duration=total_duration)
        else:
            _log(f"Mantra audio ({src_duration:.1f}s) video se lambi hai - trim kiya ja raha hai.")
            mantra_clip = mantra_clip.subclip(0, total_duration)

        mantra_clip = mantra_clip.fx(volumex, volume).set_start(0)
        return mantra_clip
    except Exception as e:
        _log(f"WARNING: mantra loop layer banane mein fail: {e}")
        _log(traceback.format_exc())
        return None


# ==========================================================================
# TRACK 3 + TRACK 4 - MUSIC LAYERS
# ==========================================================================
def _load_music_clip(entry, total_duration):
    path = entry.get("path")
    if not path or not os.path.exists(path):
        return None
    try:
        clip = AudioFileClip(path)
        start = float(entry.get("start_sec", 0.0))
        end = float(entry.get("end_sec", 0.0))
        if end > start:
            clip = clip.subclip(start, min(end, clip.duration))
        mode = entry.get("mode", "🍃 Background Music")
        vol = MUSIC_MODE_VOLUME.get(mode, 0.7)
        clip = clip.fx(volumex, vol)
        return clip
    except Exception as e:
        _log(f"WARNING: music clip load fail hui ({path}): {e}")
        return None


def build_track3_bg_music(track3_payload, total_duration):
    entries = track3_payload.get("audio", [])
    if not entries:
        return None
    clips = []
    for e in sorted(entries, key=lambda x: x["order"]):
        c = _load_music_clip(e, total_duration)
        if c is not None:
            clips.append(c)
    if not clips:
        return None
    combined = concatenate_audioclips(clips)
    if combined.duration < total_duration:
        combined = combined.fx(audio_loop, duration=total_duration)
    else:
        combined = combined.subclip(0, total_duration)
    return combined


def build_track4_music_clips(track4_payload, total_duration):
    entries = track4_payload.get("clips", [])
    if not entries:
        return []
    master_vol = float(track4_payload.get("master_volume", 0.8))
    layers = []
    for e in sorted(entries, key=lambda x: x["order"]):
        c = _load_music_clip(e, total_duration)
        if c is None:
            continue
        start = float(e.get("start_sec", 0.0))
        c = c.fx(volumex, master_vol).set_start(min(start, max(0, total_duration - 0.1)))
        layers.append(c)
    return layers


# ==========================================================================
# TRACK 6 - SFX
# ==========================================================================
def _load_sfx_clip(entry):
    if entry.get("source_type") == "builtin":
        rel_path = BUILTIN_SFX_ASSETS.get(entry.get("builtin_name"))
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), rel_path) if rel_path else None
    else:
        path = entry.get("path")

    if not path or not os.path.exists(path):
        _log(f"WARNING: SFX file nahi mili, skip: {entry.get('builtin_name') or entry.get('path')}")
        return None
    try:
        clip = AudioFileClip(path)
        start = float(entry.get("start_sec", 0.0))
        end = float(entry.get("end_sec", 0.0))
        if end > start:
            clip = clip.subclip(0, min(end - start, clip.duration))
        vol = max(0.0, float(entry.get("volume", 100)) / 100.0)
        clip = clip.fx(volumex, vol).set_start(start)
        return clip
    except Exception as e:
        _log(f"WARNING: SFX load fail hui: {e}")
        return None


def build_track6_sfx_layers(track6_payload):
    entries = track6_payload.get("sfx", [])
    layers = []
    for e in entries:
        c = _load_sfx_clip(e)
        if c is not None:
            layers.append(c)
    return layers


# ==========================================================================
# (2) AUDIO MIX - with mantra loop + volume balancing
# ==========================================================================
def build_final_audio(payload, total_duration, options):
    """
    Layer order and levels:
      1. Track 3 background music  - ducked to BG_DUCK_VOLUME_WITH_MANTRA
                                     when mantra mode is ON, full level otherwise
      2. Track 4 timed music clips - same ducking rule
      3. Track 5 narration voice   - slightly ducked only if mantra ALSO plays
      4. Mantra loop               - MANTRA_LOOP_VOLUME, sits on top
      5. Track 6 SFX               - untouched, they are short accents

    Ducking the music (rather than boosting the mantra) keeps the mix from
    clipping, which is what you'd get by pushing the voice above 1.0.

    NOTE: this is purely about the mantra AUDIO. The mantra on-screen TEXT
    (see build_mantra_text_overlay) has no effect on this mix at all.
    """
    layers = []
    is_mantra_mode = options["is_mantra_mode"]

    # --- 1. Track 3 background music (ducked under the mantra) ---
    bg_music = build_track3_bg_music(payload.get("track3", {}), total_duration)
    if bg_music is not None:
        if is_mantra_mode:
            bg_music = bg_music.fx(volumex, BG_DUCK_VOLUME_WITH_MANTRA)
            _log(f"Mantra mode ON - background music {BG_DUCK_VOLUME_WITH_MANTRA}x par duck kiya gaya.")
        layers.append(bg_music.set_start(0))

    # --- 2. Track 4 timed music clips (same ducking rule) ---
    for t4_clip in build_track4_music_clips(payload.get("track4", {}), total_duration):
        if is_mantra_mode:
            t4_clip = t4_clip.fx(volumex, BG_DUCK_VOLUME_WITH_MANTRA)
        layers.append(t4_clip)

    # --- 3. Track 5 narration voice ---
    voice_clip = build_voice_clip(payload.get("track5", {}))
    if voice_clip is not None:
        if voice_clip.duration > total_duration:
            voice_clip = voice_clip.subclip(0, total_duration)
        if is_mantra_mode:
            # Both narration AND mantra are playing - pull the narration
            # down a touch so the two voices don't fight each other.
            voice_clip = voice_clip.fx(volumex, VOICE_DUCK_VOLUME_WITH_MANTRA)
            _log("NOTE: narration aur mantra dono active hain - narration halka duck kiya gaya.")
        layers.append(voice_clip.set_start(0))

    # --- 4. Mantra loop layer (on top) ---
    if is_mantra_mode:
        mantra_layer = build_mantra_loop_layer(
            options["loop_audio_path"], total_duration, MANTRA_LOOP_VOLUME
        )
        if mantra_layer is not None:
            layers.append(mantra_layer)

    # --- 5. Track 6 SFX ---
    layers.extend(build_track6_sfx_layers(payload.get("track6", {})))

    if not layers:
        return None

    final_audio = CompositeAudioClip(layers).set_duration(total_duration)
    _log(f"Final audio mix: {len(layers)} layers, {total_duration:.1f}s.")
    return final_audio


# ==========================================================================
# (4) CLIMAX INTEGRATION - forward cta_type + custom_cta_text
# ==========================================================================
def build_climax_clip(payload, target_size, options):
    """
    Calls climax.generate_climax() with the CTA type and text so climax.py
    can pick the right 3D/shimmer style and the right TTS voice.

    Returns the climax VideoClip, or None if it could not be generated
    (the main video must still render in that case).

    A TypeError fallback keeps older climax.py signatures working: if
    generate_climax() doesn't accept cta_type/custom_cta_text yet, we
    retry with just the original arguments.
    """
    nested_climax = payload.get("climax", {}) or {}
    climax_duration = payload.get("climax_duration") or nested_climax.get("duration") or 10
    watermark_path = payload.get("climax_watermark_path") or nested_climax.get("watermark_path")
    cta_text = options["resolved_cta_text"]

    _log(f"Climax call: type={options['cta_type']} duration={climax_duration}s text='{cta_text}'")

    try:
        return climax.generate_climax(
            duration=climax_duration,
            cta_text=cta_text,
            cta_type=options["cta_type"],
            custom_cta_text=options["custom_cta_text"],
            watermark_path=watermark_path,
            target_size=target_size,
            is_draft=bool(payload.get("is_draft", False)),
        )
    except TypeError as te:
        _log(f"NOTE: climax.generate_climax() naye arguments accept nahi karta ({te}) - "
             f"purane signature se retry kiya ja raha hai.")
        try:
            return climax.generate_climax(
                duration=climax_duration,
                cta_text=cta_text,
                watermark_path=watermark_path,
                target_size=target_size,
                is_draft=bool(payload.get("is_draft", False)),
            )
        except Exception as e:
            _log(f"WARNING: Climax segment generate nahi hui, skip: {e}")
            _log(traceback.format_exc())
            return None
    except Exception as e:
        _log(f"WARNING: Climax segment generate nahi hui, skip: {e}")
        _log(traceback.format_exc())
        return None


# ==========================================================================
# (1) MASTER PIPELINE
# ==========================================================================
def master_render_pipeline(
    payload: dict,
    loop_audio_path=None,
    is_mantra_mode=None,
    ticker_enabled=None,
    cta_type=None,
    custom_cta_text=None,
    **kwargs,
) -> str:
    """
    Entry point called by app.py:

        output_file = engine.master_render_pipeline(payload)

    or with explicit overrides:

        output_file = engine.master_render_pipeline(
            payload,
            is_mantra_mode=True,
            loop_audio_path="/tmp/mantra.mp3",
            ticker_enabled=False,
            cta_type="Custom CTA",
            custom_cta_text="बेल आइकन दबाएं",
        )

    Any argument left as None is read from the payload instead.
    **kwargs absorbs anything app.py sends that this version doesn't
    know about yet (e.g. is_loop_mode / audio_file_path aliases), so a
    newer app.py never crashes an older engine.py.

    Returns a filesystem path to the rendered .mp4.
    """
    # app.py may send these alias names - accept them too.
    if loop_audio_path is None:
        loop_audio_path = kwargs.get("audio_file_path")
    if is_mantra_mode is None:
        is_mantra_mode = kwargs.get("is_loop_mode")
    if kwargs:
        unknown = [k for k in kwargs if k not in ("audio_file_path", "is_loop_mode")]
        if unknown:
            _log(f"NOTE: unknown extra arguments ignore kiye gaye: {unknown}")

    ratio = payload.get("ratio", "Shorts (9:16)")
    # app.py now only ever sends "720p" (draft) or the user's chosen
    # "720p"/"1080p" (final, default 1080p). Fall back to 720p target
    # size if an unrecognised (ratio, quality) combo ever shows up.
    quality = payload.get("output_quality", "1080p")
    target_size = TARGET_SIZES.get((ratio, quality), TARGET_SIZES[("Shorts (9:16)", "720p")])
    font_config = payload.get("font_config", {})

    # ---- (1) Resolve every runtime option in one place ----
    options = _resolve_runtime_options(
        payload, loop_audio_path, is_mantra_mode,
        ticker_enabled, cta_type, custom_cta_text,
    )

    _log(f"Render start | ratio={ratio} quality={quality} size={target_size} "
         f"draft={payload.get('is_draft')}")

    # ---- Track 1: mandatory visual base ----
    main_video = build_track1_timeline(payload.get("track1", {}), target_size)

    # ---- Track 2: overlay/insert clips on top of the base timeline ----
    main_video = overlay_track2_clips(main_video, payload.get("track2", {}), target_size)

    base_duration = main_video.duration

    # ---- (3) Track 5 ticker overlay - only when ticker_enabled ----
    overlay_layers = [main_video]

    ticker_clip = build_ticker_overlay(
        payload.get("track5", {}), target_size, base_duration, font_config,
        ticker_enabled=options["ticker_enabled"],
    )
    if ticker_clip is not None:
        overlay_layers.append(ticker_clip)

    # ---- (7) Track 5 subtitle overlay - the Script text (typed or
    # extracted from PDF/DOCX), drawn on screen. This was previously
    # collected by app.py (subtitle_font_color/size) but never rendered.
    subtitle_clip = build_subtitle_overlay(
        payload.get("track5", {}), target_size, base_duration, font_config,
        ticker_enabled=options["ticker_enabled"],
    )
    if subtitle_clip is not None:
        overlay_layers.append(subtitle_clip)

    # ---- (5) Track 5 mantra on-screen text - independent of mantra audio ----
    mantra_text_clip = build_mantra_text_overlay(
        payload.get("track5", {}), target_size, base_duration, font_config,
        options=options,
    )
    if mantra_text_clip is not None:
        overlay_layers.append(mantra_text_clip)

    if len(overlay_layers) > 1:
        main_video = CompositeVideoClip(overlay_layers, size=target_size).set_duration(base_duration)

    # ---- (2) Audio mix (Track 3, 4, 5 voice, mantra loop, 6) ----
    final_audio = build_final_audio(payload, base_duration, options)
    if final_audio is not None:
        main_video = main_video.set_audio(final_audio)

    # ---- (4) Climax handoff ----
    full_clip = main_video
    if payload.get("enable_climax"):
        climax_clip = build_climax_clip(payload, target_size, options)
        if climax_clip is not None:
            full_clip = concatenate_videoclips([main_video, climax_clip], method="compose")

    # ---- Export ----
    out_fps = 15 if payload.get("is_draft") else 30
    out_path = os.path.join(OUTPUT_DIR, f"baba_web_studio_{uuid.uuid4().hex}.mp4")

    _log(f"Writing output -> {out_path} (fps={out_fps})")
    full_clip.write_videofile(
        out_path,
        fps=out_fps,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="ultrafast" if payload.get("is_draft") else "medium",
        logger=None,
    )

    # cleanup moviepy resources
    try:
        full_clip.close()
    except Exception:
        pass

    _log("Render complete.")
    return out_path
