# ==========================================
# CLIMAX ENGINE: SPECIAL ENGAGEMENT BOOSTER
# ==========================================
import os
import numpy as np
import cv2
from moviepy.editor import (
    VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, 
    CompositeAudioClip, concatenate_videoclips, ColorClip
)


# ==========================================
# 1. PROCEDURAL VISUAL EFFECTS (PARTICLES & CONFETTI)
# ==========================================
def generate_fireworks_confetti_frame(width, height, t, total_dur):
    """
    आतिशबाज़ी (Fireworks), कन्फेटी (Confetti Shower) और बैलून्स का 
    डायनामिक OpenCV फ़्रेम जनरेट करता है।
    """
    # Create dark/translucent base canvas for climax
    img = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Seed based on frame time for smooth animation
    np.random.seed(int(t * 30))
    
    # 💥 1. Confetti Shower Layer (Falling Colored Rectangles)
    num_confetti = 80
    for _ in range(num_confetti):
        cx = np.random.randint(0, width)
        cy = int((np.random.rand() * height + t * 400)) % height
        color = tuple(map(int, np.random.randint(100, 255, size=3)))
        cv2.rectangle(img, (cx, cy), (cx + 12, cy + 20), color, -1)
        
    # 💥 2. Fireworks Particle Sparks Layer
    num_sparks = 60
    center_x, center_y = width // 2, height // 3
    for _ in range(num_sparks):
        angle = np.random.uniform(0, 2 * np.pi)
        speed = np.random.uniform(50, 350)
        radius = int((t * speed) % 250)
        sx = int(center_x + radius * np.cos(angle))
        sy = int(center_y + radius * np.sin(angle))
        if 0 <= sx < width and 0 <= sy < height:
            color = (0, 255, 255) if np.random.rand() > 0.5 else (255, 105, 180)
            cv2.circle(img, (sx, sy), np.random.randint(3, 7), color, -1)
            
    # 🎈 3. Floating Balloons (Bottom to Top Motion)
    num_balloons = 6
    for i in range(num_balloons):
        bx = int((i + 1) * (width / (num_balloons + 1)))
        by = int(height - ((t * 120 + i * 150) % (height + 200)))
        cv2.circle(img, (bx, by), 35, (0, 140, 255), -1)  # Red/Orange Balloon
        cv2.line(img, (bx, by + 35), (bx, by + 80), (200, 200, 200), 2)  # String

    return img


# ==========================================
# 2. CALL-TO-ACTION (CTA) & BADGE OVERLAYS
# ==========================================
def create_cta_overlay(width, height, duration, channel_name="बाबा वेब स्टूडियो"):
    """
    👍 LIKE & 🔔 SUBSCRIBE का 3D Pop-up animated badge और न्यूज़ टिक्कर बनाता है।
    """
    # Animated Pop-up Badge Text
    cta_text = f"👍 LIKE & 🔔 SUBSCRIBE\n{channel_name}"
    
    badge_clip = TextClip(
        cta_text,
        fontsize=55 if width < height else 70,
        color="yellow",
        font="Arial-Bold",
        stroke_color="black",
        stroke_width=3,
        method="caption",
        size=(int(width * 0.85), None),
        align="center"
    )
    
    # Center positioning with scaling effect
    badge_clip = badge_clip.set_position(('center', int(height * 0.4))).set_duration(duration)
    
    # Bottom Bar / News Ticker Note Overlay
    ticker_note = TextClip(
        "🔔 ऐसी ही और दिव्य वीडियो के लिए अभी सब्सक्राइब करें!",
        fontsize=35,
        color="white",
        bg_color="red",
        font="Arial-Bold",
        method="caption",
        size=(width, 60),
        align="center"
    ).set_position(('center', height - 80)).set_duration(duration)

    return badge_clip, ticker_note


# ==========================================
# 3. MAIN CLIMAX ATTACHMENT FUNCTION
# ==========================================
def attach_10s_climax(main_video_path, output_path, is_shorts=True, channel_name="बाबा वेब स्टूडियो", ticker_text=None):
    """
    engine.py द्वारा पास किए गए मेन वीडियो के अंत में 
    Shorts (10s) या Long (15s) का Climax जोड़ता है।
    """
    if not os.path.exists(main_video_path):
        raise FileNotFoundError(f"Main video file not found at: {main_video_path}")
        
    main_clip = VideoFileClip(main_video_path)
    width, height = main_clip.w, main_clip.h
    
    # ⏱️ Climax Timing Reservation: Shorts = 10 Sec, Long = 15 Sec
    climax_duration = 10.0 if is_shorts else 15.0
    
    # 1. Create Particle FX Video Clip
    particle_clip = VideoFileClip.fl_make_frame(
        lambda t: generate_fireworks_confetti_frame(width, height, t, climax_duration),
        duration=climax_duration
    )
    
    # 2. Generate CTA Overlay Elements
    badge_clip, ticker_note = create_cta_overlay(width, height, climax_duration, channel_name)
    
    # Composite Climax Visual Scene
    climax_visual = CompositeVideoClip(
        [particle_clip, badge_clip, ticker_note], 
        size=(width, height)
    ).set_duration(climax_duration)
    
    # 3. Audio & Voiceover Integration (SFX & AI Voice)
    climax_audio_tracks = []
    
    # SFX: Applause / Crowds Cheering (Generated or Loaded)
    sfx_applause_path = "assets/sfx/applause.mp3"
    if os.path.exists(sfx_applause_path):
        applause_sfx = AudioFileClip(sfx_applause_path).volumex(0.8).set_duration(climax_duration)
        climax_audio_tracks.append(applause_sfx)

    # Voiceover: AI Climax Announcement
    voiceover_path = "assets/voiceover/climax_vo.mp3"
    if os.path.exists(voiceover_path):
        voice_clip = AudioFileClip(voiceover_path).volumex(1.0)
        climax_audio_tracks.append(voice_clip)
        
    # Combine Audio Layers if available
    if climax_audio_tracks:
        climax_audio = CompositeAudioClip(climax_audio_tracks).set_duration(climax_duration)
        climax_visual = climax_visual.set_audio(climax_audio)
        
    # 4. Final Stitching: Main Video + Climax Video
    final_master_video = concatenate_videoclips([main_clip, climax_visual], method="compose")
    
    # Render Master Video Output
    final_master_video.write_videofile(
        output_path, 
        fps=30, 
        codec="libx264", 
        audio_codec="aac",
        threads=4
    )
    
    # Close resources
    main_clip.close()
    final_master_video.close()
    
    return output_path
