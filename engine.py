# ==============================================================================
# 📖 बाबा वेब स्टूडियो: A to Z मास्टर ब्लूप्रिंट इंजन (engine.py)
# ==============================================================================
import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2

# MoviePy 2.x Advanced Imports
from moviepy import (
    VideoFileClip,
    AudioFileClip,
    ImageClip,
    ColorClip,
    CompositeVideoClip,
    CompositeAudioClip,
    concatenate_videoclips,
    concatenate_audioclips
)

# ------------------------------------------------------------------------------
# 1) KEN BURNS MOTION & IMAGE PROCESSING (Track 1 Helper)
# ------------------------------------------------------------------------------
def apply_ken_burns_effect(image_path, duration=5.0, fps=24, target_size=(1280, 720)):
    """फोटो पर Smooth Zoom/Ken Burns इफ़ेक्ट लागू करता है।"""
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
        cropped = resized[start_y:start_y+h, start_x:start_x+w]
        return cropped

    return ImageClip(make_frame, duration=duration).with_fps(fps)

# ------------------------------------------------------------------------------
# 2) TEXT & CLIMAX OVERLAY BUILDER (Climax Engine Helper)
# ------------------------------------------------------------------------------
def create_text_overlay(text, width=1280, height=720, font_size=65, color="yellow", bg_bar=True):
    """सबटाइटल और आउट्रो संदेश के लिए पारदर्शी PNG फ्रेम तैयार करता है।"""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
        
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    
    x = (width - tw) // 2
    y = height - th - 80
    
    if bg_bar:
        padding = 15
        draw.rectangle([x - padding, y - padding, x + tw + padding, y + th + padding], fill=(0, 0, 0, 160))
        
    draw.text((x+2, y+2), text, font=font, fill="black")
    draw.text((x, y), text, font=font, fill=color)
    return np.array(img)

# ------------------------------------------------------------------------------
# 3) MASTER 7-TRACK COMPILATION ENGINE
# ------------------------------------------------------------------------------
def compile_cinematic_video(
    video_format="📱 9:16 Shorts (Default)",
    video_quality="🔘 1080p Full HD (Default) (क्रिस्प)",
    visual_files=None,            # Track 1 Data
    video_timeline_slots=None,    # Track 2 Data
    audio_files=None,             # Track 3 Data
    music_timeline_slots=None,    # Track 4 Data
    master_music_vol=0.80,        # Track 4 Master Volume
    sfx_events=None,              # Track 7 Data
    story_script="",              # Track 6 Script
    voiceover_path=None,          # Track 6 Voiceover
    auto_ducking=True,            # Track 6 Auto-Ducking
    sub_color="yellow",           # Subtitle Style
    sub_size=65,
    output_path="final_output.mp4"
):
    """
    MASTER BLUEPRINT ENGINE:
    Track 1: Visuals Layer (Mandatory)
    Track 2: Video Clips Timeline (Optional)
    Track 3: Main Audio Layer with 3 Modes (Mandatory)
    Track 4: Music Clips Timeline (Optional)
    Track 5: Timing Calculator Sync
    Track 6: Script, Voice & Subtitles
    Track 7: SFX Overlay
    Climax Engine: End Engagement Booster
    """
    if visual_files is None: visual_files = []
    if video_timeline_slots is None: video_timeline_slots = []
    if audio_files is None: audio_files = []
    if music_timeline_slots is None: music_timeline_slots = []
    if sfx_events is None: sfx_events = []

    # Aspect Ratio & Resolution Setup
    if "9:16" in video_format:
        target_size = (720, 1280) if "720p" in video_quality else (1080, 1920)
    else:
        target_size = (1280, 720) if "720p" in video_quality else (1920, 1080)
        
    fps = 24
    w, h = target_size

    # --------------------------------------------------------------------------
    # TRACK 1 & 2: VISUAL COMPOSITION ENGINE
    # --------------------------------------------------------------------------
    bg_clips = []
    for v_item in visual_files:
        path = v_item.get("path")
        if not path or not os.path.exists(path):
            continue
            
        st_t = v_item.get("start", 0.0)
        end_t = v_item.get("end", 5.0)
        dur = max(end_t - st_t, 0.5)
        
        is_img = v_item.get("is_image", True)
        use_ken_burns = v_item.get("ken_burns", True)
        
        if is_img:
            if use_ken_burns:
                c = apply_ken_burns_effect(path, duration=dur, fps=fps, target_size=target_size)
            else:
                img = Image.open(path).convert("RGB").resize(target_size)
                c = ImageClip(np.array(img), duration=dur).with_fps(fps)
        else:
            c = VideoFileClip(path).without_audio()
            if end_t > st_t and end_t <= c.duration:
                c = c.subclipped(st_t, end_t)
            c = c.resized(new_size=target_size)
            
        bg_clips.append(c)

    if not bg_clips:
        # Fallback empty black clip if missing mandatory
        bg_clips.append(ColorClip(size=target_size, color=(0,0,0), duration=10.0))

    main_visual_track = concatenate_videoclips(bg_clips, method="compose")
    total_duration = main_visual_track.duration

    # Track 2 Layering (Timed Video Overlay Clips)
    video_layers = [main_visual_track]
    for slot in video_timeline_slots:
        path = slot.get("path")
        if path and os.path.exists(path):
            st_t = slot.get("start", 0.0)
            end_t = slot.get("end", st_t + 5.0)
            dur = max(end_t - st_t, 0.5)
            
            ov_clip = VideoFileClip(path).subclipped(0, min(dur, 10.0))
            ov_clip = ov_clip.resized(new_size=(int(w*0.8), int(h*0.8))).with_position("center").with_start(st_t)
            video_layers.append(ov_clip)

    final_visual_video = CompositeVideoClip(video_layers, size=target_size)

    # --------------------------------------------------------------------------
    # TRACK 3, 4, 6, 7: AUDIO COMPOSITION & MODES ENGINE
    # --------------------------------------------------------------------------
    audio_tracks = []

    # 1. Voiceover (Track 6) with Auto-Ducking Logic
    has_voiceover = False
    if voiceover_path and os.path.exists(voiceover_path):
        vo_clip = AudioFileClip(voiceover_path)
        if vo_clip.duration > total_duration:
            vo_clip = vo_clip.subclipped(0, total_duration)
        audio_tracks.append(vo_clip.with_start(0.0))
        has_voiceover = True

    # 2. Main Music Layer (Track 3) with Modes & Auto-Looping
    bg_music_vol = 0.30 if (has_voiceover and auto_ducking) else master_music_vol
    for a_item in audio_files:
        a_path = a_item.get("path")
        if a_path and os.path.exists(a_path):
            mode = a_item.get("mode", "🎵 Song (Default)")
            m_clip = AudioFileClip(a_path)
            
            # Apply Music Mode Volume Modifiers
            if "Background" in mode:
                mode_vol = bg_music_vol * 0.4
            elif "Instrument" in mode:
                mode_vol = bg_music_vol * 0.7
            else:
                mode_vol = bg_music_vol
                
            # Looping Logic if audio is shorter than visual duration
            if m_clip.duration < total_duration:
                loops_needed = math.ceil(total_duration / m_clip.duration)
                m_clip = concatenate_audioclips([m_clip] * loops_needed)
                
            m_clip = m_clip.subclipped(0, total_duration).multiply_volume(mode_vol)
            audio_tracks.append(m_clip)

    # 3. Track 4: Music Clips Timeline
    for m_slot in music_timeline_slots:
        m_path = m_slot.get("path")
        if m_path and os.path.exists(m_path):
            st_t = m_slot.get("start", 0.0)
            end_t = m_slot.get("end", st_t + 5.0)
            dur = max(end_t - st_t, 0.5)
            
            m_clip = AudioFileClip(m_path)
            m_clip = m_clip.subclipped(0, min(dur, m_clip.duration)).with_start(st_t).multiply_volume(master_music_vol)
            audio_tracks.append(m_clip)

    # 4. Track 7: SFX Events Timeline
    for sfx in sfx_events:
        s_path = sfx.get("path")
        if s_path and os.path.exists(s_path):
            st_t = sfx.get("start", 0.0)
            end_t = sfx.get("end", st_t + 2.0)
            vol = sfx.get("volume", 0.8)
            
            s_clip = AudioFileClip(s_path)
            s_clip = s_clip.subclipped(0, min(end_t - st_t, s_clip.duration)).with_start(st_t).multiply_volume(vol)
            audio_tracks.append(s_clip)

    # Audio Layer Integration
    if audio_tracks:
        composite_audio = CompositeAudioClip(audio_tracks)
        if composite_audio.duration > total_duration:
            composite_audio = composite_audio.subclipped(0, total_duration)
        final_visual_video = final_visual_video.with_audio(composite_audio)

    # --------------------------------------------------------------------------
    # CLIMAX ENGINE & VIDEO EXPORT
    # --------------------------------------------------------------------------
    # Dynamic Render Presets
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
