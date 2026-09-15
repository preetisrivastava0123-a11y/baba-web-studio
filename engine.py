# ==============================================================
# बाबा जनरेटिव वेब स्टूडियो — वीडियो कंपाइलेशन इंजन (Engine Core)
# ==============================================================
import os
import math
import tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2

from moviepy import AudioFileClip, CompositeAudioClip, CompositeVideoClip, ImageClip, VideoFileClip, concatenate_audioclips, concatenate_videoclips, vfx

# --------------------------------------------------------------
# 1) इमेज प्रोसेसिंग और टेक्स्ट overlays
# --------------------------------------------------------------
def create_text_image(text, width=1280, height=720, font_size=50, color="yellow", bg_color=(0, 0, 0, 0)):
    image = Image.new("RGBA", (width, height), bg_color)
    draw = ImageDraw.Draw(image)
    
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
        
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    x = (width - text_width) // 2
    y = height - text_height - 60
    
    # टेक्स्ट बैकग्राउंड शैडो
    draw.text((x+2, y+2), text, font=font, fill="black")
    draw.text((x, y), text, font=font, fill=color)
    
    return np.array(image)

def apply_ken_burns_effect(image_path, duration=5.0, fps=24, target_size=(1280, 720)):
    img = Image.open(image_path).convert("RGB")
    img = img.resize(target_size)
    img_np = np.array(img)
    
    def make_frame(t):
        scale = 1.0 + 0.08 * (t / duration)
        h, w, c = img_np.shape
        new_h, new_w = int(h * scale), int(w * scale)
        resized = cv2.resize(img_np, (new_w, new_h))
        
        start_y = (new_h - h) // 2
        start_x = (new_w - w) // 2
        cropped = resized[start_y:start_y+h, start_x:start_x+w]
        return cropped

    return ImageClip(make_frame, duration=duration).with_fps(fps)

# --------------------------------------------------------------
# 2) मुख्य वीडियो कंपाइलेशन फंक्शन
# --------------------------------------------------------------
def compile_cinematic_video(
    mode="standard",
    visual_clips=None,
    video_clips_timeline=None,
    music_files_pool=None,
    music_clips_timeline=None,
    master_music_volume=0.8,
    sfx_events=None,
    script_text="",
    outro_text="",
    output_video_path="output.mp4",
    aspect_ratio="16:9",
    duration_seconds=None,
    quality="720p",
    sub_color="#FFD700",
    sub_size=65,
    voiceover_mode="ai_tts",
    custom_audio_path=None,
    outro_voice_active=True
):
    if visual_clips is None:
        visual_clips = []
    if video_clips_timeline is None:
        video_clips_timeline = []
    if music_files_pool is None:
        music_files_pool = []
    if music_clips_timeline is None:
        music_clips_timeline = []
    if sfx_events is None:
        sfx_events = []

    target_size = (1280, 720) if aspect_ratio == "16:9" else (720, 1280)
    width, height = target_size
    fps = 24

    processed_video_clips = []
    
    # 1. विज़ुअल क्लिप्स प्रोसेस करें
    for item in visual_clips:
        path = item.get("path")
        if not path or not os.path.exists(path):
            continue
            
        if item.get("is_image", True):
            duration = item.get("end", 5.0) - item.get("start", 0.0)
            if duration <= 0:
                duration = 5.0
            clip = apply_ken_burns_effect(path, duration=duration, fps=fps, target_size=target_size)
        else:
            clip = VideoFileClip(path).without_audio()
            clip = clip.resized(new_size=target_size)
            
        processed_video_clips.append(clip)

    # 2. लाइव लूप मोड चेक (अगर विज़ुअल्स कम हों तो लूप करें)
    if processed_video_clips:
        if mode == "live_loop" and duration_seconds:
            total_current_dur = sum(c.duration for c in processed_video_clips)
            if total_current_dur < duration_seconds:
                repeat_times = math.ceil(duration_seconds / total_current_dur)
                processed_video_clips = (processed_video_clips * repeat_times)
        
        final_background_video = concatenate_videoclips(processed_video_clips, method="compose")
        if duration_seconds and final_background_video.duration > duration_seconds:
            final_background_video = final_background_video.subclipped(0, duration_seconds)
    else:
        # अगर कोई मीडिया न हो तो ब्लैक स्क्रीन क्लिप बनाएं
        dur = duration_seconds if duration_seconds else 10.0
        final_background_video = ColorClip(size=target_size, color=(0, 0, 0), duration=dur)

    final_duration = final_background_video.duration

    # 3. ऑडियो प्रोसेसिंग (म्यूज़िक और SFX)
    audio_tracks = []
    
    # कस्टम/वॉइसओवर ऑडियो
    if custom_audio_path and os.path.exists(custom_audio_path):
        voice_clip = AudioFileClip(custom_audio_path)
        if voice_clip.duration > final_duration:
            voice_clip = voice_clip.subclipped(0, final_duration)
        audio_tracks.append(voice_clip)

    # म्यूज़िक क्लिप्स टाइमलाइन
    for m_item in music_clips_timeline:
        m_path = m_item.get("path")
        if m_path and os.path.exists(m_path):
            m_clip = AudioFileClip(m_path)
            st_time = m_item.get("start", 0.0)
            end_time = m_item.get("end", m_clip.duration)
            if end_time > st_time:
                m_clip = m_clip.subclipped(0, min(end_time - st_time, m_clip.duration))
            m_clip = m_clip.with_start(st_time).multiply_volume(master_music_volume)
            audio_tracks.append(m_clip)

    # SFX इवेंट्स
    for sfx in sfx_events:
        s_path = sfx.get("path")
        if s_path and os.path.exists(s_path):
            s_clip = AudioFileClip(s_path)
            st_time = sfx.get("start", 0.0)
            s_vol = sfx.get("volume", 0.7)
            s_clip = s_clip.with_start(st_time).multiply_volume(s_vol)
            audio_tracks.append(s_clip)

    # ऑडियो मिलाएँ
    if audio_tracks:
        final_audio = CompositeAudioClip(audio_tracks)
        if final_audio.duration > final_duration:
            final_audio = final_audio.subclipped(0, final_duration)
        final_background_video = final_background_video.with_audio(final_audio)

    # 4. वीडियो राइट (रेंडरिंग)
    preset_val = "ultrafast" if quality == "720p" else "medium"
    final_background_video.write_videofile(
        output_video_path,
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        preset=preset_val,
        threads=4
    )

    return output_video_path
