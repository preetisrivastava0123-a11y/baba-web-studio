# engine.py के सबसे ऊपर पुराने imports हटाकर यह लिखें:
try:
    from moviepy.editor import (
        ImageClip, VideoFileClip, AudioFileClip, CompositeVideoClip, 
        CompositeAudioClip, concatenate_videoclips, afx, vfx, TextClip
    )
except ImportError:
    from moviepy.video.io.VideoFileClip import VideoFileClip
    from moviepy.video.VideoClip import ImageClip, TextClip, CompositeVideoClip
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    from moviepy.audio.AudioClip import CompositeAudioClip
    from moviepy.video.compositing.concatenate import concatenate_videoclips
    import moviepy.audio.fx.all as afx
    import moviepy.video.fx.all as vfx

# ==========================================
# 1. VISUAL ENGINE (TRACK 1 & TRACK 2)
# ==========================================
import os
import tempfile
from moviepy.editor import ImageClip, VideoFileClip, ColorClip, concatenate_videoclips

def process_visuals(t1_files=None, default_duration=5, is_shorts=True, ken_burns=True):
    processed_clips = []
    # Target Size: Shorts = (1080, 1920), Long = (1920, 1080)
    target_size = (1080, 1920) if is_shorts else (1920, 1080)
    
    # 1. Safe Check: अगर t1_files खाली, None या गैर-लिस्ट (Non-list) हो
    if not isinstance(t1_files, (list, tuple)) or not t1_files:
        blank_clip = ColorClip(size=target_size, color=(30, 30, 30), duration=default_duration)
        return concatenate_videoclips([blank_clip], method="compose")

    # 2. UploadedFiles को सही तरह से टेम्परेरी डिस्क फाइल में लिखना
    for file in t1_files:
        temp_path = None
        
        if hasattr(file, 'read'):
            ext = os.path.splitext(file.name)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                content = file.getvalue() if hasattr(file, 'getvalue') else file.read()
                tmp.write(content)
                temp_path = tmp.name
        elif isinstance(file, str):
            temp_path = file

        if temp_path and os.path.exists(temp_path):
            try:
                ext_lower = temp_path.lower()
                
                # Image Files Handling (MoviePy resize position fix)
                if ext_lower.endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    clip = ImageClip(temp_path).set_duration(default_duration)
                    # MoviePy kompatibility fix: resize(target_size) passing tuple directly
                    clip = clip.resize(target_size)
                    processed_clips.append(clip)
                    
                # MP4 / Video Files Handling
                elif ext_lower.endswith(('.mp4', '.mov', '.avi')):
                    clip = VideoFileClip(temp_path)
                    clip = clip.resize(target_size)
                    processed_clips.append(clip)
            except Exception as e:
                print(f"Error loading clip {temp_path}: {e}")

    # 3. Fallback Check: अगर कोई क्लिप लोड नहीं हो पाई
    if not processed_clips:
        blank_clip = ColorClip(size=target_size, color=(30, 30, 30), duration=default_duration)
        processed_clips.append(blank_clip)

    return concatenate_videoclips(processed_clips, method="compose")

# ==========================================
# 2. AUDIO ENGINE & AUTO-LOOPING (TRACK 3 & TRACK 4)
# ==========================================
def process_audio_layers(main_audio_path, music_mode, visual_duration, master_vol=0.8, loop_audio=True):
    """
    Track 3 & Track 4: म्यूज़िक मोड (Song, Instrumental, BGM) वॉल्यूम सेट करता है 
    और विजुअल की कुल लंबाई तक लूप करता है।
    """
    if not main_audio_path or not os.path.exists(main_audio_path):
        return None

    audio = AudioFileClip(main_audio_path)
    
    # Mode-based Volume Levels
    mode_volumes = {
        "🎵 Song (Default)": 1.0,
        "🎻 Instrumental": 0.7,
        "🍃 Background Music": 0.3
    }
    adjusted_vol = master_vol * mode_volumes.get(music_mode, 0.8)
    audio = audio.volumex(adjusted_vol)
    
    # Auto-Looping Logic
    if loop_audio and audio.duration < visual_duration:
        loops_needed = math.ceil(visual_duration / audio.duration)
        audio = afx.audio_loop(audio, nloops=loops_needed)
    
    return audio.subclip(0, visual_duration)


# ==========================================
# 3. AUDIO DUCKING & SFX SYNC (TRACK 5 & TRACK 6)
# ==========================================
def apply_ducking_and_sfx(bg_audio, voiceover_path, sfx_events, visual_duration, auto_ducking=True):
    """
    Track 5 AI/Recorded Voiceover के आते ही BGM धीमा करता है 
    और Track 6 SFX (शंख, डमरू आदि) को टाइम-कोड पर सिंक करता है।
    """
    audio_tracks = []
    
    # Voiceover Processing
    voice_clip = None
    if voiceover_path and os.path.exists(voiceover_path):
        voice_clip = AudioFileClip(voiceover_path)
        audio_tracks.append(voice_clip)
        
        # Apply Ducking to Background Music
        if auto_ducking and bg_audio:
            bg_audio = bg_audio.volumex(0.25)
            
    if bg_audio:
        audio_tracks.append(bg_audio)
        
    # Track 6 SFX Event Syncing
    for sfx in sfx_events:
        if os.path.exists(sfx.get("path", "")):
            sfx_clip = AudioFileClip(sfx["path"]).volumex(sfx.get("volume", 0.9))
            sfx_clip = sfx_clip.set_start(sfx.get("start_sec", 0))
            audio_tracks.append(sfx_clip)

    return CompositeAudioClip(audio_tracks).set_duration(visual_duration)


# ==========================================
# 4. DYNAMIC OVERLAYS & TICKER STRIP (TRACK 5)
# ==========================================
def create_ticker_strip(ticker_text, video_w, video_h, duration, bg_color="black", txt_color="yellow"):
    """
    स्क्रीन के निचले हिस्से में लूप होने वाली रनिंग न्यूज़/कमेंट पट्टी जनरेट करता है।
    """
    if not ticker_text:
        return None
        
    txt_clip = TextClip(ticker_text, fontsize=32, color=txt_color, bg_color=bg_color, font="Arial-Bold")
    strip_h = txt_clip.h + 20
    
    # Scrolling Motion Logic (Right to Left)
    txt_clip = txt_clip.set_position(lambda t: (video_w - (t * 150) % (video_w + txt_clip.w), video_h - strip_h - 10))
    return txt_clip.set_duration(duration)


# ==========================================
# 5. TRACK 7: MASTER TIMELINE & PIPELINE HANDOFF
# ==========================================
def master_render_pipeline(payload):
    """
    UI Payload प्राप्त करके सभी लेयर्स को मर्ज करता है 
    तथा Climax Processing (`climax.py`) को फॉरवर्ड करता है।
    """
    # 1. Base Setup Variables
    v_format = payload.get("video_format", "9:16 Shorts (Default)")
    target_res = (1080, 1920) if "9:16" in v_format else (1920, 1080)
    
    base_dur = payload.get("base_duration", 30)
    has_climax = payload.get("enable_climax", True)
    total_dur = base_dur + 10 if has_climax else base_dur
    
    # 2. Build Visual Layer (Tracks 1 & 2)
    visual_clip = process_visuals(
        payload.get("t1_files", []), 
        payload.get("t2_clips", []), 
        target_res=target_res,
        default_img_dur=payload.get("t1_def_dur", 5),
        ken_burns=payload.get("t1_ken_burns", True)
    )
    
    # Force Match Visual Length to Selected Duration
    visual_clip = visual_clip.loop(duration=base_dur) if visual_clip.duration < base_dur else visual_clip.subclip(0, base_dur)
    
    # 3. Build Audio Layer (Tracks 3, 4, 5, 6)
    bg_music = process_audio_layers(
        payload.get("t3_audio"), 
        payload.get("music_mode", "🎵 Song (Default)"), 
        base_dur,
        loop_audio=payload.get("loop_audio", True)
    )
    
    final_audio = apply_ducking_and_sfx(
        bg_music, 
        payload.get("t5_voiceover"), 
        payload.get("sfx_events", []), 
        base_dur,
        auto_ducking=payload.get("auto_ducking", True)
    )
    visual_clip = visual_clip.set_audio(final_audio)

    # 4. Overlays & Ticker (Track 5)
    ticker = create_ticker_strip(payload.get("ticker_text"), target_res[0], target_res[1], base_dur)
    final_composite = CompositeVideoClip([visual_clip, ticker] if ticker else [visual_clip])

    # 5. Export Temp Main Video & Handoff to climax.py
    temp_output = "temp_main_video.mp4"
    final_output = "final_output_video.mp4"
    
    final_composite.write_videofile(temp_output, fps=30, codec="libx264", audio_codec="aac")
    
    if has_climax:
        # Pipeline Handoff to climax.py module
        import climax
        climax.attach_10s_climax(temp_output, final_output, ticker_text=payload.get("ticker_text"))
    else:
        os.rename(temp_output, final_output)

    return final_output
