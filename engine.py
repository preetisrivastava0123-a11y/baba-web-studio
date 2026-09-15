# ==============================================================================
# 📖 BABA WEB STUDIO: PRODUCTION-READY MASTER ENGINE (engine.py)
# ==============================================================================
import os
import re
import math
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from moviepy import (
    VideoClip,
    VideoFileClip,
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    CompositeAudioClip,
    concatenate_videoclips,
    concatenate_audioclips
)

# ------------------------------------------------------------------------------
# 0) PATH SAFETY HELPER
# ------------------------------------------------------------------------------
def is_valid_path(p):
    """None, empty strings, or non-existent file paths are safely caught."""
    if p is None:
        return False
    if isinstance(p, (str, bytes, os.PathLike)):
        s_path = str(p).strip()
        return len(s_path) > 0 and os.path.exists(s_path)
    return False

# ------------------------------------------------------------------------------
# 1) KEN BURNS MOTION EFFECT (Track 1 Helper)
# ------------------------------------------------------------------------------
def apply_ken_burns_effect(image_path, duration=4.0, fps=24, target_size=(1080, 1920)):
    if not is_valid_path(image_path):
        return ColorClip(size=target_size, color=(0, 0, 0), duration=duration).with_fps(fps)

    img = Image.open(image_path).convert("RGB")
    img = img.resize(target_size)
    img_np = np.array(img)
    
    def make_frame(t):
        scale = 1.0 + 0.08 * (t / max(duration, 0.1))
        h, w, _ = img_np.shape
        new_h, new_w = int(h * scale), int(w * scale)
        resized = cv2.resize(img_np, (new_w, new_h))
        
        start_y = (new_h - h) // 2
        start_x = (new_w - w) // 2
        return resized[start_y:start_y+h, start_x:start_x+w]

    return VideoClip(make_frame, duration=duration).with_fps(fps)

# ------------------------------------------------------------------------------
# 2) CLIMAX OUTRO UTILITIES & ENGINE
# ------------------------------------------------------------------------------
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF"
    "\U00002B00-\U00002BFF"
    "]+",
    flags=re.UNICODE,
)

def _find_first_existing(paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None

def _load_font(size, prefer_emoji=False):
    devanagari_candidates = [
        "C:/Windows/Fonts/Nirmala.ttf",
        "C:/Windows/Fonts/NirmalaB.ttf",
        "C:/Windows/Fonts/mangal.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.otf",
        "/System/Library/Fonts/Supplemental/Devanagari MT.ttf",
        "/System/Library/Fonts/Supplemental/Kohinoor Devanagari.ttc",
        "NotoSansDevanagari-Regular.ttf",
    ]
    emoji_candidates = [
        "C:/Windows/Fonts/seguiemj.ttf",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/noto/NotoColorEmoji.ttf",
        "/System/Library/Fonts/Apple Color Emoji.ttc",
    ]
    generic_candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]

    ordered = (emoji_candidates + devanagari_candidates) if prefer_emoji else \
              (devanagari_candidates + generic_candidates)

    path = _find_first_existing(ordered)
    if path is None:
        return ImageFont.load_default()

    try:
        return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

def _draw_mixed_text(draw, xy, text, text_font, emoji_font, fill):
    x, y = xy
    total_w = 0
    pos = 0
    for m in _EMOJI_PATTERN.finditer(text):
        if m.start() > pos:
            chunk = text[pos:m.start()]
            draw.text((x + total_w, y), chunk, font=text_font, fill=fill)
            bbox = draw.textbbox((0, 0), chunk, font=text_font)
            total_w += bbox[2] - bbox[0]
        emoji_chunk = m.group()
        draw.text((x + total_w, y), emoji_chunk, font=emoji_font, fill=fill)
        bbox = draw.textbbox((0, 0), emoji_chunk, font=emoji_font)
        total_w += bbox[2] - bbox[0]
        pos = m.end()
    if pos < len(text):
        chunk = text[pos:]
        draw.text((x + total_w, y), chunk, font=text_font, fill=fill)
        bbox = draw.textbbox((0, 0), chunk, font=text_font)
        total_w += bbox[2] - bbox[0]
    return total_w

def _measure_mixed_text(draw, text, text_font, emoji_font):
    w = 0
    h = 0
    pos = 0
    for m in _EMOJI_PATTERN.finditer(text):
        if m.start() > pos:
            chunk = text[pos:m.start()]
            bbox = draw.textbbox((0, 0), chunk, font=text_font)
            w += bbox[2] - bbox[0]
            h = max(h, bbox[3] - bbox[1])
        emoji_chunk = m.group()
        bbox = draw.textbbox((0, 0), emoji_chunk, font=emoji_font)
        w += bbox[2] - bbox[0]
        h = max(h, bbox[3] - bbox[1])
        pos = m.end()
    if pos < len(text):
        chunk = text[pos:]
        bbox = draw.textbbox((0, 0), chunk, font=text_font)
        w += bbox[2] - bbox[0]
        h = max(h, bbox[3] - bbox[1])
    return w, h

def create_climax_outro_clip(duration=10.0, target_size=(1080, 1920), fps=24):
    w, h = target_size
    np.random.seed(101)

    colors = [
        (255, 50, 150),
        (0, 230, 255),
        (255, 215, 0),
        (50, 255, 100),
        (255, 100, 50),
        (200, 100, 255),
        (255, 255, 255),
    ]

    n_centers = 8
    burst_configs = []
    for i in range(n_centers):
        burst_configs.append({
            "cx": int(w * np.random.uniform(0.15, 0.85)),
            "cy": int(h * np.random.uniform(0.10, 0.40)),
            "color": colors[i % len(colors)],
            "delay": (duration / n_centers) * i * 0.5,
            "period": np.random.uniform(1.6, 2.6),
        })

    sparks = []
    for cfg in burst_configs:
        for _ in range(45):
            sparks.append({
                "cx": cfg["cx"],
                "cy": cfg["cy"],
                "angle": np.random.uniform(0, 2 * math.pi),
                "speed": np.random.uniform(200, 700),
                "color": cfg["color"],
                "delay": cfg["delay"],
                "period": cfg["period"],
            })

    fountains = []
    for _ in range(70):
        fountains.append({
            "x": np.random.uniform(w * 0.08, w * 0.92),
            "speed_y": np.random.uniform(-950, -500),
            "speed_x": np.random.uniform(-100, 100),
            "color": colors[np.random.randint(0, len(colors))],
            "period": np.random.uniform(1.8, 2.4),
            "phase": np.random.uniform(0, 2.0),
        })

    floating_items = [
        {"text": "\U0001F44D LIKE", "bg": (0, 122, 255), "x": int(w * 0.15), "speed": 170, "phase": 0.0},
        {"text": "\U0001F514 BELL", "bg": (255, 149, 0), "x": int(w * 0.38), "speed": 205, "phase": 1.3},
        {"text": "\U0001F534 SUBSCRIBE", "bg": (255, 45, 85), "x": int(w * 0.62), "speed": 185, "phase": 0.7},
        {"text": "\u2197\uFE0F SHARE", "bg": (52, 199, 89), "x": int(w * 0.85), "speed": 200, "phase": 1.9},
    ]

    font_large = _load_font(38, prefer_emoji=False)
    font_large_emoji = _load_font(38, prefer_emoji=True)
    font_btn = _load_font(24, prefer_emoji=False)
    font_btn_emoji = _load_font(24, prefer_emoji=True)

    def make_frame(t):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # A) Multi-burst firework explosions
        for s in sparks:
            rel_t = t - s["delay"]
            if rel_t <= 0:
                continue
            cycle_t = rel_t % s["period"]
            dist = s["speed"] * cycle_t
            px = int(s["cx"] + dist * math.cos(s["angle"]))
            py = int(s["cy"] + dist * math.sin(s["angle"]) + 120 * (cycle_t ** 2))
            tail_x = int(px - 25 * math.cos(s["angle"]))
            tail_y = int(py - 25 * math.sin(s["angle"]))
            if 0 <= px < w and 0 <= py < h:
                alpha = max(0, int(255 * (1 - cycle_t / s["period"])))
                draw.line([(tail_x, tail_y), (px, py)], fill=s["color"] + (alpha,), width=4)
                draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(255, 255, 255, alpha))

        # B) Fountain particles
        for f in fountains:
            ft = (t + f["phase"]) % f["period"]
            fx = int(f["x"] + f["speed_x"] * ft)
            fy = int(h * 0.88 + f["speed_y"] * ft + 350 * (ft ** 2))
            if 0 <= fx < w and 0 <= fy < h:
                alpha = max(0, int(220 * (1 - ft / f["period"])))
                draw.ellipse([fx - 3, fy - 3, fx + 3, fy + 3], fill=f["color"] + (alpha,))

        # C) Falling Badges
        for item in floating_items:
            curr_y = int(((t + item["phase"]) * item["speed"]) % (h + 100)) - 50
            curr_x = int(item["x"] + 20 * math.sin(t * 3 + item["phase"]))

            bw, bh = 190, 50
            draw.rounded_rectangle(
                [curr_x - bw // 2 + 3, curr_y + 3, curr_x + bw // 2 + 3, curr_y + bh + 3],
                radius=15, fill=(0, 0, 0, 120),
            )
            draw.rounded_rectangle(
                [curr_x - bw // 2, curr_y, curr_x + bw // 2, curr_y + bh],
                radius=15, fill=item["bg"] + (240,), outline=(255, 255, 255, 255), width=2,
            )
            text_w, text_h = _measure_mixed_text(draw, item["text"], font_btn, font_btn_emoji)
            tx = curr_x - text_w // 2
            ty = curr_y + (bh - text_h) // 2
            _draw_mixed_text(draw, (tx, ty), item["text"], font_btn, font_btn_emoji, fill=(255, 255, 255, 255))

        # D) Bottom Hindi CTA Card
        pulse = 1.0 + 0.04 * math.sin(t * 8)
        bw, bh = int(w * 0.90), int(130 * pulse)
        bx = (w - bw) // 2
        by = int(h * 0.82)

        draw.rounded_rectangle(
            [bx + 4, by + 6, bx + bw + 4, by + bh + 6], radius=22, fill=(0, 0, 0, 180)
        )
        draw.rounded_rectangle(
            [bx, by, bx + bw, by + bh], radius=22, fill=(210, 20, 30, 250),
            outline=(255, 215, 0, 255), width=5,
        )

        text = "\U0001F514 लाइक और सब्सक्राइब जरूर करें!"
        text_w, text_h = _measure_mixed_text(draw, text, font_large, font_large_emoji)
        tx = bx + (bw - text_w) // 2
        ty = by + (bh - text_h) // 2
        _draw_mixed_text(draw, (tx, ty), text, font_large, font_large_emoji, fill=(255, 255, 255, 255))

        return np.array(img)

    return VideoClip(make_frame, duration=duration).with_fps(fps)

# ------------------------------------------------------------------------------
# 3) MAIN ENGINE FUNCTION
# ------------------------------------------------------------------------------
def apply_volume_scale(clip, scale):
    if hasattr(clip, "volumex"):
        return clip.volumex(scale)
    elif hasattr(clip, "with_volume_scaling"):
        return clip.with_volume_scaling(scale)
    elif hasattr(clip, "transform"):
        return clip.transform(lambda get_frame, t: get_frame(t) * scale)
    return clip

def render_video_engine(
    visual_clips,
    output_path="output.mp4",
    total_duration=10.0,
    voiceover_path=None,
    audio_files=None,
    sfx_events=None,
    auto_ducking=True,
    master_music_vol=0.8,
    video_quality="1080p",
    fps=24,
    target_size=(1080, 1920)
):
    if audio_files is None:
        audio_files = []
    if sfx_events is None:
        sfx_events = []

    # Visual track composition
    if not visual_clips:
        main_clip = ColorClip(size=target_size, color=(0, 0, 0), duration=total_duration).with_fps(fps)
    else:
        main_clip = concatenate_videoclips(visual_clips)

    outro_overlay = create_climax_outro_clip(duration=total_duration, target_size=target_size, fps=fps)
    final_visual_video = CompositeVideoClip([main_clip, outro_overlay]).with_duration(total_duration)

    # Audio Composition Engine
    audio_tracks = []
    has_voiceover = False

    # Track 6: Voiceover Layer
    if is_valid_path(voiceover_path):
        vo_clip = AudioFileClip(voiceover_path)
        vo_clip = vo_clip.subclipped(0, min(vo_clip.duration, total_duration)).with_start(0.0)
        audio_tracks.append(vo_clip)
        has_voiceover = True

    # Track 3 & 4: Main Music Layer
    bg_music_vol = 0.30 if (has_voiceover and auto_ducking) else master_music_vol
    for a_item in audio_files:
        if isinstance(a_item, dict):
            a_path = a_item.get("path", None)
            if is_valid_path(a_path):
                mode = a_item.get("mode", "🎵 Song (Default)")
                m_clip = AudioFileClip(a_path)
                
                if "Background" in mode:
                    mode_vol = bg_music_vol * 0.4
                elif "Instrument" in mode:
                    mode_vol = bg_music_vol * 0.7
                else:
                    mode_vol = bg_music_vol
                    
                if m_clip.duration < total_duration:
                    loops_needed = math.ceil(total_duration / m_clip.duration)
                    m_clip = concatenate_audioclips([m_clip] * loops_needed)
                    
                m_clip = m_clip.subclipped(0, total_duration).with_start(0.0)
                m_clip = apply_volume_scale(m_clip, mode_vol)
                audio_tracks.append(m_clip)

    # Track 7: SFX Events
    for sfx in sfx_events:
        if isinstance(sfx, dict):
            s_path = sfx.get("path", None)
            if is_valid_path(s_path):
                st_t = sfx.get("start", 0.0)
                end_t = sfx.get("end", st_t + 2.0)
                vol = sfx.get("volume", 0.8)
                
                s_clip = AudioFileClip(s_path)
                s_clip = s_clip.subclipped(0, min(end_t - st_t, s_clip.duration)).with_start(st_t)
                s_clip = apply_volume_scale(s_clip, vol)
                audio_tracks.append(s_clip)

    # Integrate Audio with Video
    if audio_tracks:
        composite_audio = CompositeAudioClip(audio_tracks).subclipped(0, total_duration)
        final_visual_video = final_visual_video.with_audio(composite_audio)

    # Export Configuration
    preset = "ultrafast" if "720p" in video_quality else "medium"
    
    final_visual_video.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        preset=preset,
        threads=4
    )

    return output_path

# ------------------------------------------------------------------------------
# 4) EXECUTION ENTRY POINT FOR PREVIEW
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    clip = create_climax_outro_clip(duration=10.0, target_size=(1080, 1920), fps=24)
    for sample_t in (0.0, 2.5, 5.0, 9.5):
        frame = clip.get_frame(sample_t)
        Image.fromarray(frame).save(f"/tmp/climax_preview_{sample_t:.1f}.png")
    print("Preview frames written to /tmp/climax_preview_*.png")

# app.py के साथ कनेक्ट करने के लिए (Alias)
compile_cinematic_video = render_video_engine


# ==============================================================================
# 5) APP.PY COMPATIBILITY WRAPPER (सभी पैरामीटर्स को सपोर्ट करने के लिए)
# ==============================================================================
def compile_cinematic_video(
    video_format="9:16 (Vertical Short/Reel)",
    video_quality="1080p (Full HD)",
    visual_files=None,
    video_timeline_slots=None,
    audio_files=None,
    music_timeline_slots=None,
    master_music_vol=0.8,
    sfx_events=None,
    story_script="",
    voiceover_path=None,
    output_path="final_master_video.mp4",
    auto_ducking=True,
    total_duration=10.0,
    fps=24
):
    """
    app.py के सभी पैरामीटर्स को सुरक्षित रूप से हैंडल करता है।
    """
    # 1. Target Size तय करना (Format के अनुसार)
    if "16:9" in str(video_format):
        target_size = (1920, 1080)
    elif "1:1" in str(video_format):
        target_size = (1080, 1080)
    else:
        target_size = (1080, 1920) # 9:16 Vertical Default

    # 2. Visual Clips की लिस्ट तैयार करना
    visual_clips = []
    if visual_files:
        for v in visual_files:
            if isinstance(v, dict) and is_valid_path(v.get("path")):
                # Ken Burns Effect लागू करना
                clip = apply_ken_burns_effect(
                    v.get("path"), 
                    duration=v.get("duration", 4.0), 
                    fps=fps, 
                    target_size=target_size
                )
                visual_clips.append(clip)
            elif isinstance(v, str) and is_valid_path(v):
                clip = apply_ken_burns_effect(v, duration=4.0, fps=fps, target_size=target_size)
                visual_clips.append(clip)

    # 3. Main Engine को कॉल करना
    return render_video_engine(
        visual_clips=visual_clips,
        output_path=output_path,
        total_duration=total_duration,
        voiceover_path=voiceover_path,
        audio_files=audio_files,
        sfx_events=sfx_events,
        auto_ducking=auto_ducking,
        master_music_vol=master_music_vol,
        video_quality=video_quality,
        fps=fps,
        target_size=target_size
    )
