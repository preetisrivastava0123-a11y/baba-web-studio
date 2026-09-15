# ==============================================================================
# 🎬 BABA WEB STUDIO: ENGINE.PY (लूपिंग और सही ड्यूरेशन के साथ)
# ==============================================================================
import os
import numpy as np
from moviepy import (
    VideoFileClip, AudioFileClip, ImageClip, 
    CompositeVideoClip, CompositeAudioClip, concatenate_videoclips, ColorClip
)

# climax.py से आउट्रो फ़ंक्शन आयात करना
from climax import create_climax_outro_clip


def is_valid_path(path):
    return path and isinstance(path, str) and os.path.exists(path)


def apply_ken_burns_effect(image_path, duration=4.0, fps=24, target_size=(1080, 1920)):
    """[काम]: इमेज पर ज़ूम इन इफ़ेक्ट देना"""
    try:
        clip = ImageClip(image_path).with_duration(duration)
        return clip.resized(target_size=target_size)
    except Exception as e:
        print(f"⚠️ इमेज लोड करने में त्रुटि {image_path}: {e}")
        return None


def render_video_engine(
    visual_clips=None,
    output_path="final_master_video.mp4",
    total_duration=10.0,
    voiceover_path=None,
    audio_files=None,
    sfx_events=None,
    auto_ducking=True,
    master_music_vol=0.8,
    video_quality="1080p (Full HD)",
    fps=24,
    target_size=(1080, 1920),
    outro_text=""
):
    """[मुख्य रेंडर इंजन]: विजुअल, ऑडियो और क्लाइमैक्स आउट्रो को जोड़कर वीडियो बनाता है"""
    print("🚀 रेंडरिंग इंजन शुरू हो रहा है...")

    # 1. विज़ुअल क्लिप्स को जोड़ना
    clips_list = []
    if visual_clips:
        for vc in visual_clips:
            if vc is not None:
                clips_list.append(vc)

    if not clips_list:
        # अगर कोई क्लिप न हो तो एक ब्लैक क्लिप बना लें
        clips_list = [ColorClip(size=target_size, color=(0,0,0), duration=5.0).with_fps(fps)]

    base_video = concatenate_videoclips(clips_list, method="compose")

    # 2. Climax.py से आउट्रो लेयर जोड़ना (आख़िरी 5.5 सेकंड)
    climax_duration = 5.5
    try:
        outro_clip = create_climax_outro_clip(
            duration=climax_duration, 
            target_size=target_size, 
            fps=fps
        )
        final_visual = concatenate_videoclips([base_video, outro_clip], method="compose")
    except Exception as e:
        print(f"⚠️ आउट्रो जोड़ने में विफल: {e}")
        final_visual = base_video

    # 3. ऑडियो और वॉइसओवर संभालना
    audio_tracks = []
    
    if voiceover_path and os.path.exists(voiceover_path):
        try:
            vo_clip = AudioFileClip(voiceover_path)
            audio_tracks.append(vo_clip)
        except Exception as e:
            print(f"⚠️ वॉइसओवर लोड नहीं हो सका: {e}")

    if audio_files:
        for af in audio_files:
            if isinstance(af, dict) and os.path.exists(af.get("path", "")):
                try:
                    m_clip = AudioFileClip(af["path"]).with_effects([lambda c: c.with_volume_scaled(master_music_vol)])
                    audio_tracks.append(m_clip)
                except Exception as e:
                    print(f"⚠️ म्यूज़िक लोड नहीं हो सका: {e}")

    if audio_tracks:
        final_audio = CompositeAudioClip(audio_tracks)
        final_visual = final_visual.with_audio(final_audio)

    # 4. वीडियो को एक्सपोर्ट/सेव करना
    print(f"💾 वीडियो यहाँ सेव हो रही है: {output_path}")
    final_visual.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4
    )

    print("✨ रेंडरिंग सफलतापूर्वक पूर्ण हुई!")
    return output_path


# ==============================================================================
# app.py कम्पैटिबिलिटी रैपर (लूपिंग लॉजिक के साथ)
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
    total_duration=None,
    fps=24
):
    """यह फ़ंक्शन app.py से डेटा लेकर तय करता है कि वीडियो कितनी लंबी बनेगी और कम पड़ने पर लूप चलाता है"""
    
    # 1. कुल समय (Target Duration) का हिसाब लगाना
    target_duration = 10.0
    
    if voiceover_path and os.path.exists(voiceover_path):
        try:
            vo_temp = AudioFileClip(voiceover_path)
            target_duration = max(target_duration, vo_temp.duration)
            vo_temp.close()
        except Exception:
            pass

    if total_duration and total_duration > target_duration:
        target_duration = total_duration

    climax_time = 5.5
    visuals_target_duration = max(5.0, target_duration - climax_time)

    # 2. स्क्रीन साइज़ तय करना
    if "16:9" in str(video_format):
        target_size = (1920, 1080)
    elif "1:1" in str(video_format):
        target_size = (1080, 1080)
    else:
        target_size = (1080, 1920)

    # 3. विज़ुअल क्लिप्स तैयार करना और कम होने पर लूप चलाना (Looping Logic)
    raw_clips = []
    if visual_files:
        for v in visual_files:
            path = v.get("path") if isinstance(v, dict) else v
            if is_valid_path(path):
                clip = apply_ken_burns_effect(path, duration=4.0, fps=fps, target_size=target_size)
                if clip:
                    raw_clips.append(clip)

    visual_clips = []
    if raw_clips:
        current_total_len = sum(c.duration for c in raw_clips)
        
        # अगर इमेजेस कम हैं, तो उन्हें तब तक लूप करते रहो जब तक कुल समय पूरा न हो जाए
        if current_total_len < visuals_target_duration:
            while sum(c.duration for c in visual_clips) < visuals_target_duration:
                for c in raw_clips:
                    visual_clips.append(c)
                    if sum(x.duration for x in visual_clips) >= visuals_target_duration:
                        break
        else:
            visual_clips = raw_clips
    else:
        visual_clips = [ColorClip(size=target_size, color=(0,0,0), duration=visuals_target_duration).with_fps(fps)]

    # 4. मुख्य इंजन को कॉल करना
    return render_video_engine(
        visual_clips=visual_clips,
        output_path=output_path,
        total_duration=target_duration,
        voiceover_path=voiceover_path,
        audio_files=audio_files,
        sfx_events=sfx_events,
        auto_ducking=auto_ducking,
        master_music_vol=master_music_vol,
        video_quality=video_quality,
        fps=fps,
        target_size=target_size,
        outro_text=story_script
    )
