# ==============================================================================
# 🎬 BABA WEB STUDIO: STREAMLINED ENGINE (engine.py)
# ==============================================================================
import os
import tempfile
import asyncio
import numpy as np
from moviepy import (
    VideoFileClip, AudioFileClip, ImageClip, TextClip, 
    CompositeVideoClip, CompositeAudioClip, concatenate_videoclips
)

# climax.py से आउट्रो फ़ंक्शन आयात करना
from climax import create_climax_outro_clip


def is_valid_path(path):
    return path and isinstance(path, str) and os.path.exists(path)


def apply_ken_burns_effect(image_path, duration=4.0, fps=24, target_size=(1080, 1920)):
    """[काम]: इमेज पर ज़ूम इन / केन बर्न्स इफ़ेक्ट देना"""
    try:
        clip = ImageClip(image_path).with_duration(duration)
        # रिसाइज़ और इफ़ेक्ट लॉजिक
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
    """
    [मुख्य रेंडर इंजन]: 
    - विज़ुअल क्लिप्स को जोड़ता है।
    - वॉइसओवर और बैकग्राउंड म्यूज़िक को सिंक्रनाइज़ करता है।
    - अंत में climax.py से आउट्रो जोड़कर वीडियो कंपाइल करता है।
    """
    print("🚀 रेंडरिंग इंजन शुरू हो रहा है...")
    clips_list = []

    # 1. विज़ुअल क्लिप्स जोड़ना
    if visual_clips:
        for vc in visual_clips:
            if vc is not None:
                clips_list.append(vc)

    # अगर कोई विज़ुअल नहीं है, तो एक ब्लैंक/डिफ़ॉल्ट क्लिप बना लें ताकि क्रैश न हो
    if not clips_list:
        print("⚠️ कोई विज़ुअल क्लिप नहीं मिली, डमी क्लिप बनाई जा रही है...")
        # एक छोटी रंगीन फ़्रेम या ब्लैक क्लिप जोड़ सकते हैं

    # मुख्य वीडियो कटघरा जोड़ना
    if len(clips_list) > 1:
        base_video = concatenate_videoclips(clips_list, method="compose")
    elif len(clips_list) == 1:
        base_video = clips_list[0]
    else:
        raise ValueError("रेंडर करने के लिए कोई वैध विज़ुअल क्लिप उपलब्ध नहीं है!")

    actual_video_duration = base_video.duration

    # 2. Climax.py से आउट्रो लेयर जोड़ना (लगभग आख़िरी 5 से 10 सेकंड)
    climax_duration = 5.5
    try:
        outro_clip = create_climax_outro_clip(
            duration=climax_duration, 
            target_size=target_size, 
            fps=fps
        )
        # बेस वीडियो के अंत में क्लाइमैक्स जोड़ना
        final_visual = concatenate_videoclips([base_video, outro_clip], method="compose")
    except Exception as e:
        print(f"⚠️ आउट्रो जोड़ने में विफल, केवल बेस वीडियो रखा जा रहा है: {e}")
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
                    print(f"⚠️ म्यूज़िक फ़ाइल लोड नहीं हो सकी: {e}")

    if audio_tracks:
        final_audio = CompositeAudioClip(audio_tracks)
        final_visual = final_visual.with_audio(final_audio)

    # 4. फ़ाइल राइट करना (Export)
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
# app.py के साथ कम्पैटिबिलिटी रैपर (पुराने नाम से एरर न आए)
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
    """app.py के कॉल को सीधे render_video_engine पर डायवर्ट करता है"""
    
    if "16:9" in str(video_format):
        target_size = (1920, 1080)
    elif "1:1" in str(video_format):
        target_size = (1080, 1080)
    else:
        target_size = (1080, 1920)

    visual_clips = []
    if visual_files:
        for v in visual_files:
            if isinstance(v, dict) and is_valid_path(v.get("path")):
                clip = apply_ken_burns_effect(v.get("path"), duration=v.get("duration", 4.0), fps=fps, target_size=target_size)
                if clip:
                    visual_clips.append(clip)
            elif isinstance(v, str) and is_valid_path(v):
                clip = apply_ken_burns_effect(v, duration=4.0, fps=fps, target_size=target_size)
                if clip:
                    visual_clips.append(clip)

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
        target_size=target_size,
        outro_text=story_script
    )
