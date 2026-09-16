# -*- coding: utf-8 -*-
"""
engine.py - Baba Web Studio
Production render pipeline. Consumes the payload dict built by app.py's
build_payload() exactly as-is and returns a path to the rendered .mp4.

Public API
----------
master_render_pipeline(payload: dict) -> str

NOTE ON PAYLOAD SHAPE
----------------------------------------------------------------------
app.py's actual build_payload() puts climax fields at the TOP LEVEL of
the payload (payload['enable_climax'], payload['climax_duration'],
payload['climax_text'], payload['climax_watermark_path']) -- there is
no nested payload['climax'] dict. This module reads them from where
app.py actually puts them, not from a hypothetical nested key.

DEVANAGARI TEXT
----------------------------------------------------------------------
Per app.py's header docstring: PIL's default text layout does not shape
Devanagari conjuncts/matras correctly. This module renders all Hindi
text (subtitles/ticker) through a Chromium/Playwright pass when
available, falling back to PIL + RAQM, then plain PIL as a last resort
-- mirroring the same strategy climax.py uses for the CTA text.
----------------------------------------------------------------------
"""

import os
import io
import math
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

# Map app.py's BUILTIN_SFX_LIBRARY labels -> local asset files.
# These files ship alongside engine.py; if missing, the SFX event is
# skipped gracefully (see _load_sfx_clip).
BUILTIN_SFX_ASSETS = {
    "शंख (Shankh)": "assets/sfx/shankh.mp3",
    "डमरू (Damru)": "assets/sfx/damru.mp3",
    "घंटी (Ghanti)": "assets/sfx/ghanti.mp3",
    "सीटी (Whistle)": "assets/sfx/whistle.mp3",
    "तालियां (Applause)": "assets/sfx/applause.mp3",
}

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
# DEVANAGARI-SAFE TEXT RENDERING (mirrors climax.py's strategy)
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
                                     bg_color_hex=None, align="center"):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    background_css = bg_color_hex if bg_color_hex else "transparent"
    html = f"""
    <html><head><style>
      html, body {{
        margin: 0; padding: 0; background: {background_css};
        width: {canvas_w}px; height: {canvas_h}px;
        display: flex; align-items: center; justify-content: {align};
      }}
      #txt {{
        font-family: 'Noto Sans Devanagari', 'Nirmala UI', 'Mangal', sans-serif;
        font-size: {font_size}px; font-weight: 600; color: {color_hex};
        white-space: nowrap; padding: 0 16px;
        text-shadow: 0 0 6px rgba(0,0,0,0.8);
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
                              bg_rgba=(0, 0, 0, 0), font_config=None):
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

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (canvas_w - tw) / 2
    y = (canvas_h - th) / 2
    stroke_w = max(1, font_size // 20)
    draw.text((x, y), text, font=font, fill=color_rgb + (255,),
               stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))
    return img


def render_hindi_text_image(text, font_size, color_rgb, canvas_w, canvas_h,
                             bg_color_rgb=None, font_config=None):
    """Chromium first (correct shaping), PIL+raqm fallback. Returns RGBA PIL Image."""
    if not text:
        return Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    hex_color = "#%02x%02x%02x" % color_rgb
    bg_hex = ("#%02x%02x%02x" % bg_color_rgb) if bg_color_rgb else None
    img = _render_text_png_via_playwright(text, font_size, hex_color, canvas_w, canvas_h, bg_hex)
    if img is None:
        bg_rgba = (bg_color_rgb + (255,)) if bg_color_rgb else (0, 0, 0, 0)
        img = _render_text_png_via_pil(text, font_size, color_rgb, canvas_w, canvas_h,
                                        bg_rgba, font_config)
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
            clip = CompositeVideoClip([ColorClip(target_size, color=(0, 0, 0)).set_duration(duration), clip],
                                       size=target_size).set_duration(duration)
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
    """Track 2 clips replace/overlay the main timeline as full-frame inserts
    during their specified [start_sec, end_sec] window (intro/meme/side clips)."""
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
# TRACK 5 - TICKER OVERLAY (bottom scrolling text, Devanagari-safe)
# ==========================================================================
def build_ticker_overlay(track5_payload, target_size, total_duration, font_config):
    ticker_text = (track5_payload.get("ticker_text") or "").strip()
    if not ticker_text:
        return None

    w, h = target_size
    band_h = max(36, int(h * 0.045))
    font_size = int(band_h * 0.62)
    bg_rgb = _hex_to_rgb(track5_payload.get("ticker_bg_color", "#000000"), (0, 0, 0))
    speed = TICKER_SPEED_PX_PER_SEC.get(track5_payload.get("ticker_speed", "Medium"), 120)

    # Render the ticker text once at natural width (repeat with spacing so
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
    return ticker_clip


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
    voice_source = track5_payload.get("voice_source")
    if voice_source == "AI Voice (Edge-TTS)":
        return generate_ai_voice_clip(
            track5_payload.get("script_text", ""),
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
# AUDIO MIX
# ==========================================================================
def build_final_audio(payload, total_duration):
    layers = []

    bg_music = build_track3_bg_music(payload.get("track3", {}), total_duration)
    if bg_music is not None:
        layers.append(bg_music.set_start(0))

    layers.extend(build_track4_music_clips(payload.get("track4", {}), total_duration))

    voice_clip = build_voice_clip(payload.get("track5", {}))
    if voice_clip is not None:
        if voice_clip.duration > total_duration:
            voice_clip = voice_clip.subclip(0, total_duration)
        layers.append(voice_clip.set_start(0))

    layers.extend(build_track6_sfx_layers(payload.get("track6", {})))

    if not layers:
        return None

    final_audio = CompositeAudioClip(layers).set_duration(total_duration)
    return final_audio


# ==========================================================================
# MASTER PIPELINE
# ==========================================================================
def master_render_pipeline(payload: dict) -> str:
    """
    Entry point called by app.py:
        output_file = engine.master_render_pipeline(payload)
    Returns a filesystem path to the rendered .mp4.
    """
    ratio = payload.get("ratio", "Shorts (9:16)")
    quality = payload.get("output_quality", "1080p")
    target_size = TARGET_SIZES.get((ratio, quality), TARGET_SIZES[("Shorts (9:16)", "720p")])
    font_config = payload.get("font_config", {})

    _log(f"Render start | ratio={ratio} quality={quality} size={target_size} draft={payload.get('is_draft')}")

    # ---- Track 1: mandatory visual base ----
    main_video = build_track1_timeline(payload.get("track1", {}), target_size)

    # ---- Track 2: overlay/insert clips on top of the base timeline ----
    main_video = overlay_track2_clips(main_video, payload.get("track2", {}), target_size)

    base_duration = main_video.duration

    # ---- Track 5 ticker overlay ----
    ticker_clip = build_ticker_overlay(payload.get("track5", {}), target_size, base_duration, font_config)
    if ticker_clip is not None:
        main_video = CompositeVideoClip([main_video, ticker_clip], size=target_size).set_duration(base_duration)

    # ---- Audio mix (Track 3, 4, 5 voice, 6) ----
    final_audio = build_final_audio(payload, base_duration)
    if final_audio is not None:
        main_video = main_video.set_audio(final_audio)

    # ---- Climax handoff ----
    full_clip = main_video
    if payload.get("enable_climax"):
        climax_duration = payload.get("climax_duration", 10)
        climax_text = payload.get("climax_text", "")
        watermark_path = payload.get("climax_watermark_path")
        try:
            climax_clip = climax.generate_climax(
                duration=climax_duration,
                cta_text=climax_text,
                watermark_path=watermark_path,
                target_size=target_size,
                is_draft=bool(payload.get("is_draft", False)),
            )
            full_clip = concatenate_videoclips([main_video, climax_clip], method="compose")
        except Exception as e:
            _log(f"WARNING: Climax segment generate nahi hui, ise skip kiya ja raha hai: {e}")
            _log(traceback.format_exc())

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
