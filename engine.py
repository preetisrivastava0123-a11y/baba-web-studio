# ==============================================================================
# 📖 बाबा वेब स्टूडियो: MASTER 7-TRACK ENGINE (engine.py)
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
# 1) KEN BURNS MOTION EFFECT (MoviePy v2 Compatible)
# ------------------------------------------------------------------------------
def apply_ken_burns_effect(image_path, duration=5.0, fps=24, target_size=(1280, 720)):
    """फोटो पर स्मूथ ज़ूम/Ken Burns इफ़ेक्ट लागू करता है।"""
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
# 2) CLIMAX ENGINE: 10-15 SECONDS RESERVED OUTRO & SPARKS GENERATOR
# ------------------------------------------------------------------------------
def create_climax_outro_clip(duration=10.0, target_size=(1280, 720), fps=24):
    """
    अंतिम 10-15 सेकंड के लिए आतिशबाज़ी स्पार्क्स (Fireworks) और 
    3D 'LIKE & SUBSCRIBE' एनिमेटेड बैज विथ गोल्ड ग्लो तैयार करता है।
    """
    w, h = target_size
    num_particles = 60
    np.random.seed(42)

    # पार्टिकल इनिशियल स्टेट्स
    particles = [{
        'x': w // 2,
        'y': h // 2,
        'vx': np.random.uniform(-400, 400),
        'vy': np.random.uniform(-400, 100),
        'color': (np.random.randint(220, 255), np.random.randint(180, 255), np.random.randint(0, 120))
    } for _ in range(num_particles)]

    def make_frame(t):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 1. पार्टिकल आतिशबाज़ी (Particle Sparks)
        cycle_t = t % 3.0  # हर 3 सेकंड पर आतिशबाज़ी का लूप
        for p in particles:
            px = int(p['x'] + p['vx'] * cycle_t)
            py = int(p['y'] + p['vy'] * cycle_t + 120 * (cycle_t ** 2)) # Gravity effect
            if 0 <= px < w and 0 <= py < h:
                draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=p['color'])

        # 2. 3D Animated LIKE & SUBSCRIBE Badge with Gold Glow
        scale = 1.0 + 0.06 * math.sin(t * 6)
        bw, bh = int(w * 0.7 * scale), int(110 * scale)
        bx, by = (w - bw) // 2, (h - bh) // 2

        # बैज शैडो और गोल्ड ग्लो
        draw.rounded_rectangle([bx + 4, by + 6, bx + bw + 4, by + bh + 6], radius=25, fill=(0, 0, 0, 140))
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=25, fill=(220, 38, 38, 245), outline=(255, 215, 0), width=5)

        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(38 * scale))
        except Exception:
            font = ImageFont.load_default()

        text = "🔔 LIKE & SUBSCRIBE FOR MORE!"
        tb = draw.textbbox((0, 0), text, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        draw.text(((w - tw) // 2, (h - th) // 2), text, font=font, fill="white")

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
    per_image_duration=4.0,       # प्रति फोटो समय
    climax_reserved_sec=10.0,     # क्लाइमैक्स के लिए रिज़र्व 10-15 सेकंड
    output_path="final_output.mp4"
):
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
    # TRACK 1 & 2: DYNAMIC VISUAL DURATION & CLIMAX CALCULATIONS
    # --------------------------------------------------------------------------
    bg_clips = []
    for v_item in visual_files:
        path = v_item.get("path")
        if not path or not os.path.exists(path):
            continue
            
        dur = v_item.get("end", per_image_duration) - v_item.get("start", 0.0)
        dur = max(dur, 2.0)
        is_img = v_item.get("is_image", True)
        use_ken_burns = v_item.get("ken_burns", True)
        
        if is_img:
            if use_ken_burns:
                c = apply_ken_burns_effect(path, duration=dur, fps=fps, target_size=target_size)
            else:
                img = Image.open(path).convert("RGB").resize(target_size)
                c = VideoClip(lambda t: np.array(img), duration=dur).with_fps(fps)
        else:
            c = VideoFileClip(path).without_audio()
            c = c.subclipped(0, min(dur, c.duration)).resized(new_size=target_size)
            
        bg_clips.append(c)

    if not bg_clips:
        bg_clips.append(ColorClip(size=target_size, color=(0,0,0), duration=15.0))

    main_visual_content = concatenate_videoclips(bg_clips, method="compose")
    content_duration = main_visual_content.duration

    # यूट्यूब नियम: अगर सामग्री बहुत छोटी है, तो लूप करके कम से कम 15s बनाएं
    if content_duration < 15.0:
        loops_needed = math.ceil(15.0 / content_duration)
        main_visual_content = concatenate_videoclips([main_visual_content] * loops_needed)
        content_duration = main_visual_content.duration

    # कुल लंबाई = मुख्य विजुअल्स की लंबाई + 10 से 15 सेकंड का क्लाइमैक्स आउट्रो
    total_duration = content_duration + climax_reserved_sec

    # अंतिम विजुअल ट्रैक (मुख्य विजुअल्स को अंत तक फैलाना ताकि ब्लैक स्क्रीन न दिखे)
    visual_extension_loops = math.ceil(total_duration / content_duration)
    full_visual_track = concatenate_videoclips([main_visual_content] * visual_extension_loops).subclipped(0, total_duration)

    video_layers = [full_visual_track]

    # Track 2 Layering (Timed Overlays)
    for slot in video_timeline_slots:
        path = slot.get("path")
        if path and os.path.exists(path):
            st_t = min(slot.get("start", 0.0), total_duration - 1.0)
            dur = min(slot.get("end", st_t + 5.0) - st_t, total_duration - st_t)
            
            ov_clip = VideoFileClip(path).subclipped(0, min(dur, 5.0))
            ov_clip = ov_clip.resized(new_size=(int(w*0.8), int(h*0.8))).with_position("center").with_start(st_t)
            video_layers.append(ov_clip)

    # 💥 PYTHON CLIMAX ENGINE: अंतिम 10 से 15 सेकंड के लिए ओवरले
    climax_outro = create_climax_outro_clip(duration=climax_reserved_sec, target_size=target_size, fps=fps)
    climax_outro = climax_outro.with_start(total_duration - climax_reserved_sec)
    video_layers.append(climax_outro)

    final_visual_video = CompositeVideoClip(video_layers, size=target_size)

    # --------------------------------------------------------------------------
    # TRACK 3, 4, 6, 7: GUARANTEED AUDIO & MUSIC ENGINE
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

    # Voiceover Layer (Track 6)
    has_voiceover = False
    if voiceover_path and os.path.exists(voiceover_path):
        vo_clip = AudioFileClip(voiceover_path)
        vo_clip = vo_clip.subclipped(0, min(vo_clip.duration, total_duration)).with_start(0.0)
        audio_tracks.append(vo_clip)
        has_voiceover = True

    # Main Music Layer (Track 3) - लूप होकर पूरे वीडियो समय तक चलेगा
    bg_music_vol = 0.30 if (has_voiceover and auto_ducking) else master_music_vol
    for a_item in audio_files:
        a_path = a_item.get("path")
        if a_path and os.path.exists(a_path):
            mode = a_item.get("mode", "🎵 Song (Default)")
            m_clip = AudioFileClip(a_path)
            
            if "Background" in mode: mode_vol = bg_music_vol * 0.4
            elif "Instrument" in mode: mode_vol = bg_music_vol * 0.7
            else: mode_vol = bg_music_vol
                
            # ऑटो-लूपिंग पूरी वीडियो लंबाई (total_duration) के लिए
            if m_clip.duration < total_duration:
                loops_needed = math.ceil(total_duration / m_clip.duration)
                m_clip = concatenate_audioclips([m_clip] * loops_needed)
                
            m_clip = m_clip.subclipped(0, total_duration).with_start(0.0)
            m_clip = apply_volume_scale(m_clip, mode_vol)
            audio_tracks.append(m_clip)

    # Audio Layer Integration
    if audio_tracks:
        composite_audio = CompositeAudioClip(audio_tracks).subclipped(0, total_duration)
        final_visual_video = final_visual_video.with_audio(composite_audio)

    # --------------------------------------------------------------------------
    # RENDER ENGINE EXPORT
    # --------------------------------------------------------------------------
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
