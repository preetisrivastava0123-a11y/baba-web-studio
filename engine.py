# ==============================================================================
# 📖 BABA WEB STUDIO: PRODUCTION-READY MASTER ENGINE (engine.py)
# ==============================================================================
import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2

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
# 0) PATH SAFETY HELPER (PREVENTS NoneType CRASHES GLOBALLY)
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
def apply_ken_burns_effect(image_path, duration=4.0, fps=24, target_size=(1280, 720)):
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
# 2) ADVANCED CLIMAX ENGINE: 10-SEC MULTI-STYLE FIREWORKS & FALLING BUTTONS
# ------------------------------------------------------------------------------
def create_climax_outro_clip(duration=10.0, target_size=(1080, 1920), fps=24):
    w, h = target_size
    np.random.seed(101)

    # 🎇 1. Multi-Color & Multi-Style Fireworks Setup
    colors = [
        (255, 50, 150),   # मैजेंटा / पिंक
        (0, 230, 255),    # स्काई ब्लू
        (255, 215, 0),    # गोल्डन येलो
        (50, 255, 100),   # नियॉन ग्रीन
        (255, 100, 50),   # ऑरेंज / रेड
        (200, 100, 255),  # पर्पल
        (255, 255, 255)   # ब्राइट व्हाइट
    ]

    # अलग-अलग लोकेशन पर अलग-अलग समय पर ब्लास्ट होने वाले सेंटर्स
    burst_configs = [
        {'cx': int(w * 0.2), 'cy': int(h * 0.20), 'color': colors[0], 'delay': 0.0},
        {'cx': int(w * 0.8), 'cy': int(h * 0.20), 'color': colors[1], 'delay': 0.5},
        {'cx': int(w * 0.5), 'cy': int(h * 0.30), 'color': colors[2], 'delay': 1.0},
        {'cx': int(w * 0.35), 'cy': int(h * 0.15), 'color': colors[3], 'delay': 1.8},
        {'cx': int(w * 0.65), 'cy': int(h * 0.15), 'color': colors[4], 'delay': 2.3},
        {'cx': int(w * 0.5), 'cy': int(h * 0.18), 'color': colors[5], 'delay': 3.0},
    ]

    sparks = []
    for cfg in burst_configs:
        for _ in range(45):
            sparks.append({
                'cx': cfg['cx'],
                'cy': cfg['cy'],
                'angle': np.random.uniform(0, 2 * math.pi),
                'speed': np.random.uniform(200, 700),
                'color': cfg['color'],
                'delay': cfg['delay']
            })

    # 🎆 2. Anar / Fountain Sparks (नीचे से ऊपर छूटने वाले पटाखे)
    fountains = []
    for _ in range(60):
        fountains.append({
            'x': np.random.uniform(w * 0.1, w * 0.9),
            'speed_y': np.random.uniform(-900, -500),
            'speed_x': np.random.uniform(-100, 100),
            'color': colors[np.random.randint(0, len(colors))]
        })

    # 🎈 3. Falling Like / Subscribe / Bell Buttons Setup (गिरने वाले बटन)
    floating_items = [
        {"text": "👍 LIKE", "bg": (0, 122, 255), "x": int(w * 0.15), "speed": 180, "phase": 0},
        {"text": "🔔 BELL", "bg": (255, 149, 0), "x": int(w * 0.38), "speed": 220, "phase": 1.5},
        {"text": "🔴 SUBSCRIBE", "bg": (255, 45, 85), "x": int(w * 0.62), "speed": 190, "phase": 0.8},
        {"text": "↗️ SHARE", "bg": (52, 199, 89), "x": int(w * 0.85), "speed": 210, "phase": 2.1},
    ]

    # Fonts Loader
    font_paths = [
        "C:/Windows/Fonts/mangal.ttf",
        "C:/Windows/Fonts/nirmala.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "mangal.ttf"
    ]
    font_large, font_btn = None, None
    for fp in font_paths:
        try:
            if os.path.exists(fp):
                font_large = ImageFont.truetype(fp, 38)
                font_btn = ImageFont.truetype(fp, 24)
                break
        except Exception:
            continue

    if font_large is None:
        font_large = ImageFont.load_default()
        font_btn = ImageFont.load_default()

    def make_frame(t):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # -------------------------------------------------------------
        # A) FIREWORKS TYPE 1: MULTI-BURST EXPLOSIONS (आतिशबाजी धमाके)
        # -------------------------------------------------------------
        for s in sparks:
            rel_t = t - s['delay']
            if rel_t > 0:
                cycle_t = rel_t % 2.5  # हर 2.5 सेकंड में री-ब्लास्ट
                dist = s['speed'] * cycle_t
                px = int(s['cx'] + dist * math.cos(s['angle']))
                py = int(s['cy'] + dist * math.sin(s['angle']) + 120 * (cycle_t ** 2)) # गुरुत्वाकर्षण (Gravity)

                tail_x = int(px - 25 * math.cos(s['angle']))
                tail_y = int(py - 25 * math.sin(s['angle']))

                if 0 <= px < w and 0 <= py < h:
                    alpha = max(0, int(255 * (1 - cycle_t / 2.5)))
                    draw.line([(tail_x, tail_y), (px, py)], fill=s['color'] + (alpha,), width=4)
                    draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(255, 255, 255, alpha))

        # -------------------------------------------------------------
        # B) FIREWORKS TYPE 2: FOUNTAINS / ANAR (नीचे से ऊपर अनार)
        # -------------------------------------------------------------
        for f in fountains:
            ft = t % 2.0
            fx = int(f['x'] + f['speed_x'] * ft)
            fy = int(h * 0.85 + f['speed_y'] * ft + 350 * (ft ** 2))
            if 0 <= fx < w and 0 <= fy < h:
                draw.ellipse([fx - 3, fy - 3, fx + 3, fy + 3], fill=f['color'] + (220,))

        # -------------------------------------------------------------
        # C) FALLING BUTTONS (ऊपर से नीचे गिरते हुए बटन)
        # -------------------------------------------------------------
        for item in floating_items:
            # Y पोजीशन की गणना
            curr_y = int(((t + item['phase']) * item['speed']) % (h + 100)) - 50
            curr_x = int(item['x'] + 20 * math.sin(t * 3 + item['phase'])) # हल्का झूलना (Swaying)

            bw, bh = 180, 50
            # बटन कार्ड
            draw.rounded_rectangle([curr_x - bw//2 + 3, curr_y + 3, curr_x + bw//2 + 3, curr_y + bh + 3], radius=15, fill=(0, 0, 0, 120))
            draw.rounded_rectangle([curr_x - bw//2, curr_y, curr_x + bw//2, curr_y + bh], radius=15, fill=item['bg'] + (240,), outline=(255, 255, 255), width=2)
            
            # बटन टेक्स्ट
            draw.text((curr_x - bw//3, curr_y + 12), item['text'], font=font_btn, fill=(255, 255, 255, 255))

        # -------------------------------------------------------------
        # D) MAIN HINDI CTA CARD (मुख्य हिंदी टेक्स्ट कार्ड)
        # -------------------------------------------------------------
        pulse = 1.0 + 0.04 * math.sin(t * 8)
        bw, bh = int(w * 0.90), int(130 * pulse)
        bx = (w - bw) // 2
        by = int(h * 0.82)

        # 3D शैडो और रेड-गोल्डन कार्ड
        draw.rounded_rectangle([bx + 4, by + 6, bx + bw + 4, by + bh + 6], radius=22, fill=(0, 0, 0, 180))
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=22, fill=(210, 20, 30, 250), outline=(255, 215, 0), width=5)

        # शुद्ध हिंदी मैसेज
        text = "🔔 लाइक और सब्सक्राइब जरूर करें!"
        
        try:
            tb = draw.textbbox((0, 0), text, font=font_large)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
        except Exception:
            tw, th = int(bw * 0.8), 40

        tx = bx + (bw - tw) // 2
        ty = by + (bh - th) // 2

        draw.text((tx, ty), text, font=font_large, fill=(255, 255, 255, 255))

        return np.array(img)

    return VideoClip(make_frame, duration=duration).with_fps(fps)

# ------------------------------------------------------------------------------
# 3) MASTER 7-TRACK COMPILATION ENGINE
# ------------------------------------------------------------------------------
def compile_cinematic_video(
    video_format="📱 9:16 Shorts (Default)",
    video_quality="🔘 1080p Full HD (Default) (क्रिस्प)",
    visual_files=None,
    video_timeline_slots=None,
    audio_files=None,
    music_timeline_slots=None,
    master_music_vol=0.80,
    sfx_events=None,
    story_script="",
    voiceover_path=None,
    auto_ducking=True,
    output_path="final_output.mp4"
):
    if visual_files is None: visual_files = []
    if video_timeline_slots is None: video_timeline_slots = []
    if audio_files is None: audio_files = []
    if music_timeline_slots is None: music_timeline_slots = []
    if sfx_events is None: sfx_events = []

    # Resolution Setup
    if "9:16" in video_format:
        target_size = (720, 1280) if "720p" in video_quality else (1080, 1920)
    else:
        target_size = (1280, 720) if "720p" in video_quality else (1920, 1080)
        
    fps = 24
    w, h = target_size

    # --------------------------------------------------------------------------
    # TRACK 1: VISUAL COMPOSITION ENGINE
    # --------------------------------------------------------------------------
    bg_clips = []
    default_clip_dur = 10.0

    for v_item in visual_files:
        if not isinstance(v_item, dict):
            continue
        path = v_item.get("path", None)
        if not is_valid_path(path):
            continue
            
        is_img = v_item.get("is_image", True)
        use_ken_burns = v_item.get("ken_burns", True)
        
        if is_img:
            if use_ken_burns:
                c = apply_ken_burns_effect(path, duration=default_clip_dur, fps=fps, target_size=target_size)
            else:
                img = Image.open(path).convert("RGB").resize(target_size)
                c = VideoClip(lambda t: np.array(img), duration=default_clip_dur).with_fps(fps)
        else:
            c = VideoFileClip(path).without_audio()
            c = c.subclipped(0, min(default_clip_dur, c.duration)).resized(new_size=target_size)
            
        bg_clips.append(c)

    if not bg_clips:
        bg_clips.append(ColorClip(size=target_size, color=(0, 0, 0), duration=10.0).with_fps(fps))

    main_visual_track = concatenate_videoclips(bg_clips, method="compose")
    total_duration = main_visual_track.duration

    # Track 2 Layering (Overlay Videos)
    video_layers = [main_visual_track]
    for slot in video_timeline_slots:
        if isinstance(slot, dict):
            path = slot.get("path", None)
            if is_valid_path(path):
                st_t = min(slot.get("start", 0.0), total_duration - 1.0)
                dur = min(slot.get("end", st_t + 4.0) - st_t, total_duration - st_t)
                
                ov_clip = VideoFileClip(path).subclipped(0, min(dur, 4.0))
                ov_clip = ov_clip.resized(new_size=(int(w*0.8), int(h*0.8))).with_position("center").with_start(st_t)
                video_layers.append(ov_clip)

    # CLIMAX ENGINE OVERLAY
    outro_dur = 4.0
    if total_duration >= outro_dur:
        climax_outro = create_climax_outro_clip(duration=outro_dur, target_size=target_size, fps=fps)
        climax_outro = climax_outro.with_start(total_duration - outro_dur)
        video_layers.append(climax_outro)

    final_visual_video = CompositeVideoClip(video_layers, size=target_size)

    # --------------------------------------------------------------------------
    # TRACK 3, 4, 6, 7: AUDIO COMPOSITION ENGINE
    # --------------------------------------------------------------------------
    audio_tracks = []

    def apply_volume_scale(clip, scale):
        if hasattr(clip, "volumex"):
            return clip.volumex(scale)
        elif hasattr(clip, "with_volume_scaling"):
            return clip.with_volume_scaling(scale)
        elif hasattr(clip, "transform"):
            return clip.transform(lambda get_frame, t: get_frame(t) * scale)
        return clip

    # Track 6: Voiceover Layer
    has_voiceover = False
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
                
                if "Background" in mode: mode_vol = bg_music_vol * 0.4
                elif "Instrument" in mode: mode_vol = bg_music_vol * 0.7
                else: mode_vol = bg_music_vol
                    
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

    # Integrate Audio
    if audio_tracks:
        composite_audio = CompositeAudioClip(audio_tracks).subclipped(0, total_duration)
        final_visual_video = final_visual_video.with_audio(composite_audio)

    # Export
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
