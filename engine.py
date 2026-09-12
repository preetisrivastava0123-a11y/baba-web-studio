"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो — engine.py
==============================================================
यह ब्लॉक "कोर वीडियो कंपाइलर इंजन" (Core Video Compiler Engine) है।
इसका काम है बाकी स्वतंत्र ब्लॉक्स — voice.py, subtitle.py, climax.py,
और यूज़र के क्रम में सजाए गए मंदिर विजुअल्स — को एक ही धागे में
पिरोकर अंतिम वीडियो बनाना।

इस वर्ज़न में नया क्या है:
  १. compile_cinematic_video() अब user_media_list (लिस्ट), aspect_ratio,
     duration_seconds और quality पैरामीटर स्वीकार करता है।
  २. यूज़र द्वारा दी गई क्रम-संख्या (ordering) के अनुसार सभी
     फोटो/वीडियो एक के बाद एक (Sequential) जोड़े जाते हैं।
  ३. महा-लूपिंग: लंबे वीडियो (5/30/60 मिनट) के लिए विज़ुअल्स और
     बैकग्राउंड सितार संगीत (sitar_vadand_sfx.mp3) चुनी गई ड्यूरेशन
     पूरी होने तक अपने-आप चक्र में दोहराए (loop) जाते हैं। मयूर-पंख
     क्लाइमेक्स हमेशा सिर्फ़ आख़िरी 5.5 सेकंड में ही आता है — चाहे
     वीडियो 40 सेकंड का हो या 1 घंटे का (क्योंकि climax.py को हमेशा
     सही total_video_duration ही भेजा जाता है)।
  ४. फॉर्मेट-स्विच: 9:16 Shorts (1080x1920) या 16:9 Long Video
     (1920x1080), और क्वालिटी-स्विच: 720p या 1080p — दोनों मिलकर
     फाइनल कैनवस-साइज़ और एक्सपोर्ट-बिटरेट तय करते हैं।
  ५. "देखने लायक" (viral) बनाने के लिए दो तकनीकें जोड़ी हैं:
       - केन-बर्न्स ज़ूम इफ़ेक्ट (सिर्फ़ फोटो पर) — हल्का सा धीरे-धीरे
         ज़ूम-इन, जिससे स्थिर फोटो भी सिनेमैटिक लगती है।
       - क्रॉसफेड ट्रांज़िशन — हर कट अगले क्लिप में स्मूदली घुलता है,
         अचानक जंप-कट नहीं लगता।

⚠️ मान्यताएँ (Assumptions) — असली फाइलें उपलब्ध न होने के कारण:
   - voice.py:      create_baba_audio(script_text, output_path) -> str
   - subtitle.py:   render_subtitle_html_to_png(text_string, output_image_path,
                     canvas_width) -> str
   - climax.py:     create_climax_layer(video_duration, outro_text) -> list
                     (यह फंक्शन ख़ुद तय करता है कि आख़िरी 5.5 सेकंड में
                     मयूर-पंख/आउट्रो कब दिखाना है, इसलिए यहाँ सिर्फ़ सही
                     total_video_duration पास करना काफ़ी है)
   - प्रोजेक्ट की रूट डायरेक्टरी में "sitar_vadand_sfx.mp3" नाम की एक
     बैकग्राउंड-संगीत फाइल मौजूद है (लॉन्ग-वीडियो मोड के लिए)।

अगर आपके असली फंक्शन-नाम/फाइल-नाम अलग हैं, तो सिर्फ़ नीचे दिए
IMPORT/CONSTANT बदल दीजिए — बाकी पूरा ढाँचा वैसा ही रहेगा।
==============================================================
"""

import os

from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_audioclips,
    concatenate_videoclips,
)

# --------------------------------------------------------------
# बाकी स्वतंत्र ब्लॉक्स से ज़रूरी फंक्शन इम्पोर्ट करना
# --------------------------------------------------------------
from voice import create_baba_audio                # ऑडियो (कहानी + डक सितार)
from subtitle import render_subtitle_html_to_png   # हिंदी सबटाइटल PNG
from climax import create_climax_layer              # मयूर पंख + आउट्रो लेयर्स


# --------------------------------------------------------------
# सेटिंग्स (Constants)
# --------------------------------------------------------------
SUBTITLE_TEMP_PNG = "temp_subtitle_overlay.png"     # सबटाइटल PNG का अस्थायी नाम
SITAR_BACKGROUND_MUSIC_PATH = "sitar_vadand_sfx.mp3"  # लॉन्ग-वीडियो का बैकग्राउंड संगीत

RENDER_FPS = 24
RENDER_THREADS = 8            # स्पीड लॉक: 8 थ्रेड्स
RENDER_PRESET = "ultrafast"   # स्पीड लॉक: सबसे तेज़ प्रीसेट

# --- "देखने लायक" (viral) बनाने वाली सेटिंग्स ---
KEN_BURNS_ZOOM_RATE = 0.06          # फोटो पर कुल कितना % ज़ूम-इन होगा (स्लॉट के अंत तक)
CROSSFADE_DURATION_SECONDS = 0.6    # हर कट के बीच स्मूद घुलने का समय
SHORTS_SLOT_SECONDS = 4             # Shorts में हर विज़ुअल कितनी देर दिखेगा (तेज़, एनर्जेटिक कट्स)
LONG_VIDEO_SLOT_SECONDS = 10        # Long Video में हर विज़ुअल कितनी देर दिखेगा (शांत, ध्यान-सा पेस)


# --------------------------------------------------------------
# 1) फॉर्मेट + क्वालिटी के हिसाब से टारगेट साइज़ और बिटरेट तय करना
# --------------------------------------------------------------
def _resolve_export_settings(aspect_ratio: str, quality: str):
    """
    यूज़र के चुने फॉर्मेट (9:16 / 16:9) और क्वालिटी (720p / 1080p) के
    आधार पर सही कैनवस-साइज़ और एक्सपोर्ट-बिटरेट लौटाता है।

    रिटर्न:
        (target_width, target_height, export_bitrate)
    """
    if aspect_ratio == "16:9":
        target_width, target_height = (1920, 1080) if quality == "1080p" else (1280, 720)
    else:
        # डिफ़ॉल्ट: 9:16 Shorts फॉर्मेट
        target_width, target_height = (1080, 1920) if quality == "1080p" else (720, 1280)

    export_bitrate = "8000k" if quality == "1080p" else "4000k"
    return target_width, target_height, export_bitrate


# --------------------------------------------------------------
# 2) एक ऑडियो क्लिप को तब तक लूप करना जब तक टारगेट ड्यूरेशन पूरी न हो
# --------------------------------------------------------------
def _loop_audio_clip_to_duration(audio_clip, target_duration: float):
    """
    छोटी ऑडियो क्लिप (जैसे बैकग्राउंड संगीत) को बार-बार जोड़कर
    (concatenate) तब तक लंबा करता है जब तक वह target_duration तक
    न पहुँच जाए, फिर ठीक उसी लंबाई पर काट (trim) देता है।
    """
    if audio_clip.duration >= target_duration:
        return audio_clip.subclip(0, target_duration)

    loops_needed = int(target_duration // audio_clip.duration) + 1
    looped_audio_clip = concatenate_audioclips([audio_clip] * loops_needed)
    return looped_audio_clip.subclip(0, target_duration)


# --------------------------------------------------------------
# 3) ऑडियो ट्रैक तैयार करना — मोड के हिसाब से (Shorts बनाम Long Video)
# --------------------------------------------------------------
def _build_audio_track(is_long_video: bool, script_text: str, long_video_duration_seconds):
    """
    Shorts मोड में: कहानी की आवाज़ (+ डक सितार संगीत, voice.py के अंदर
    मिक्स्ड) ही चलेगी, और उसकी लंबाई ही पूरे वीडियो की लंबाई तय करेगी।

    Long Video मोड में: यूज़र की चुनी ड्यूरेशन (5/30/60 मिनट) तक
    बैकग्राउंड सितार संगीत (sitar_vadand_sfx.mp3) चक्र में लूप होता
    रहेगा — जैसे एक शांत मंदिर-दर्शन/ध्यान वीडियो।

    रिटर्न:
        (audio_clip, total_video_duration)
    """
    if not is_long_video:
        final_audio_path = create_baba_audio(script_text, "temp_baba_voice.mp3")
        voice_audio_clip = AudioFileClip(final_audio_path)
        return voice_audio_clip, voice_audio_clip.duration

    if not long_video_duration_seconds:
        raise ValueError("Long Video के लिए duration_seconds ज़रूर दिया जाना चाहिए।")

    sitar_bg_clip = AudioFileClip(SITAR_BACKGROUND_MUSIC_PATH)
    looped_bg_audio_clip = _loop_audio_clip_to_duration(sitar_bg_clip, long_video_duration_seconds)
    return looped_bg_audio_clip, long_video_duration_seconds


# --------------------------------------------------------------
# 4) एक विज़ुअल (फोटो/वीडियो) को लोड करके टारगेट साइज़ में क्रॉप-टू-फिल करना
#    + फोटो होने पर केन-बर्न्स ज़ूम इफ़ेक्ट जोड़ना
# --------------------------------------------------------------
def _load_single_visual_clip(media_path: str, slot_duration: float, target_width: int, target_height: int):
    """
    एक फाइल को उसके "स्लॉट" जितनी देर के लिए तैयार करता है:
      - फोटो हो तो: स्लॉट जितनी देर दिखेगी + धीरे-धीरे ज़ूम-इन (Ken Burns)
      - वीडियो हो तो: ज़रूरत पड़ने पर लूप करके स्लॉट तक बढ़ाया/काटा जाएगा
    फिर उसे टारगेट साइज़ (9:16 या 16:9) में क्रॉप-टू-फिल किया जाता है।
    """
    file_extension = os.path.splitext(media_path)[1].lower()
    is_image = file_extension in (".png", ".jpg", ".jpeg", ".webp")

    if is_image:
        raw_clip = ImageClip(media_path).set_duration(slot_duration)
    else:
        raw_clip = VideoFileClip(media_path)
        if raw_clip.duration < slot_duration:
            loop_count = int(slot_duration // raw_clip.duration) + 1
            raw_clip = concatenate_videoclips([raw_clip] * loop_count)
        raw_clip = raw_clip.subclip(0, slot_duration)

    # ---- क्रॉप-टू-फिल: पहले बड़ा-किनारा स्केल, फिर बीच से टारगेट-साइज़ काटना ----
    original_width, original_height = raw_clip.size
    target_aspect_ratio = target_width / target_height
    original_aspect_ratio = original_width / original_height

    if original_aspect_ratio > target_aspect_ratio:
        resized_clip = raw_clip.resize(height=target_height)
    else:
        resized_clip = raw_clip.resize(width=target_width)

    cropped_clip = resized_clip.crop(
        x_center=resized_clip.w / 2,
        y_center=resized_clip.h / 2,
        width=target_width,
        height=target_height,
    )

    # ---- सिर्फ़ फोटो पर केन-बर्न्स ज़ूम: वीडियो को "जीवंत" और सिनेमैटिक बनाता है ----
    # यह टारगेट-साइज़ में क्रॉप करने के *बाद* लगाया गया है, ताकि ज़ूम की वजह
    # से फ्रेम का अनुपात (aspect ratio) कभी न बिगड़े।
    if is_image:
        cropped_clip = cropped_clip.resize(
            lambda t: 1 + KEN_BURNS_ZOOM_RATE * (t / max(slot_duration, 0.001))
        )

    return cropped_clip


# --------------------------------------------------------------
# 5) क्रम में सजाए गए सभी विज़ुअल्स को लूप करके फुल-ड्यूरेशन ट्रैक बनाना
# --------------------------------------------------------------
def _build_looped_visual_track(
    ordered_media_paths: list,
    total_duration: float,
    target_width: int,
    target_height: int,
    is_long_video: bool,
):
    """
    यूज़र द्वारा दी गई क्रम-संख्या के अनुसार सजाई गई फाइलों को एक-एक
    "स्लॉट" (कुछ सेकंड) के लिए दिखाता है, फिर अगली फाइल पर जाता है।
    लिस्ट खत्म होने पर वापस पहली फाइल से चक्र (loop) शुरू कर देता है
    — जब तक कि total_duration पूरी न हो जाए। हर कट क्रॉसफेड से जुड़ता है।
    """
    slot_duration = LONG_VIDEO_SLOT_SECONDS if is_long_video else SHORTS_SLOT_SECONDS
    total_media_count = len(ordered_media_paths)

    visual_clips_sequence = []
    elapsed_duration = 0.0
    media_cycle_index = 0

    while elapsed_duration < total_duration:
        current_media_path = ordered_media_paths[media_cycle_index % total_media_count]
        remaining_duration = total_duration - elapsed_duration
        current_slot_duration = min(slot_duration, remaining_duration)

        visual_clip = _load_single_visual_clip(
            media_path=current_media_path,
            slot_duration=current_slot_duration,
            target_width=target_width,
            target_height=target_height,
        )

        # पहली क्लिप को छोड़कर बाकी सभी में क्रॉसफेड-इन जोड़ना (स्मूद कट)
        if visual_clips_sequence:
            visual_clip = visual_clip.crossfadein(CROSSFADE_DURATION_SECONDS)

        visual_clips_sequence.append(visual_clip)
        elapsed_duration += current_slot_duration
        media_cycle_index += 1

    combined_visual_track = concatenate_videoclips(
        visual_clips_sequence,
        method="compose",
        padding=-CROSSFADE_DURATION_SECONDS,
    )

    # ---- सुरक्षा-नेट: केन-बर्न्स ज़ूम की वजह से फ्रेम कैनवस से थोड़ा बाहर
    # निकल सकता है, इसलिए आख़िर में फिर से ठीक टारगेट-साइज़ पर सेंटर-क्रॉप
    # कर देना, ताकि आगे सबटाइटल/क्लाइमेक्स लेयर से साइज़ हमेशा मैच करे।
    combined_visual_track = combined_visual_track.crop(
        x_center=combined_visual_track.w / 2,
        y_center=combined_visual_track.h / 2,
        width=target_width,
        height=target_height,
    ).set_duration(total_duration)

    return combined_visual_track


# --------------------------------------------------------------
# 6) हिंदी सबटाइटल ओवरले लेयर बनाना (subtitle.py के ज़रिए)
# --------------------------------------------------------------
def _build_subtitle_overlay_clip(script_text: str, video_duration: float, canvas_width: int):
    """
    subtitle.py से Playwright के ज़रिए एक पारदर्शी PNG बनवाकर उसे
    स्क्रीन के नीचे वाले हिस्से में ओवरले करता है। canvas_width अब
    फ़िक्स नहीं बल्कि चुने गए फॉर्मेट (9:16/16:9) के अनुसार आता है,
    ताकि सबटाइटल कभी वीडियो से बाहर न छलके।
    """
    rendered_subtitle_png_path = render_subtitle_html_to_png(
        text_string=script_text,
        output_image_path=SUBTITLE_TEMP_PNG,
        canvas_width=canvas_width,
    )

    subtitle_clip = (
        ImageClip(rendered_subtitle_png_path)
        .set_duration(video_duration)
        .set_position(("center", "bottom"))
    )

    return subtitle_clip


# --------------------------------------------------------------
# 7) मुख्य फंक्शन — यही बाहर से (app.py से) बुलाया जाएगा
# --------------------------------------------------------------
def compile_cinematic_video(
    user_media_list: list,
    script_text: str,
    outro_text: str,
    output_video_path: str,
    aspect_ratio: str = "9:16",
    duration_seconds: int = 15,
    quality: str = "1080p Full HD",
) -> str:

    """
    पूरी सिनेमैटिक वीडियो-निर्माण प्रक्रिया को एक जगह जोड़ता है:
      १) फॉर्मेट (9:16/16:9) + क्वालिटी (720p/1080p) से टारगेट साइज़ तय करना
      २) ऑडियो ट्रैक तैयार करना (Shorts: कहानी की आवाज़, Long: लूप्ड सितार संगीत)
         — इसी से पूरे वीडियो की कुल लंबाई (total_video_duration) तय होती है
      ३) यूज़र की क्रम-संख्या के अनुसार सभी विज़ुअल्स को एक-एक करके जोड़ना,
         ज़रूरत पड़ने पर पूरी ड्यूरेशन तक चक्र में लूप करना (Ken Burns + क्रॉसफेड के साथ)
      ४) subtitle.py से हिंदी सबटाइटल PNG बनवाकर नीचे ओवरले करना
      ५) climax.py से आख़िरी 5.5 सेकंड में मयूर-पंख + आउट्रो जोड़ना
         (चाहे वीडियो 40 सेकंड का हो या 1 घंटे का)
      ६) चुनी गई क्वालिटी के बिटरेट के साथ फाइनल रेंडर करना

    पैरामीटर:
        user_media_list (list)   -> यूज़र की क्रम-संख्या अनुसार सजाई फाइलों की पाथ-लिस्ट
        script_text (str)        -> कहानी की स्क्रिप्ट (आवाज़/सबटाइटल के लिए)
        outro_text (str)         -> क्लाइमेक्स में दिखने वाला कमेंट/नोट
        output_video_path (str)  -> फाइनल वीडियो कहाँ सेव होगी
        aspect_ratio (str)       -> "9:16" (Shorts) या "16:9" (Long Video)
        duration_seconds (int)   -> सिर्फ़ Long Video के लिए ज़रूरी (सेकंड में)
        quality (str)            -> "720p" या "1080p"

    रिटर्न:
        str -> फाइनल वीडियो की फाइल-पाथ (output_video_path)
    """
    is_long_video = aspect_ratio == "16:9"
    target_width, target_height, export_bitrate = _resolve_export_settings(aspect_ratio, quality)

    # ---------------------------------------------------------
    # चरण १: ऑडियो ट्रैक + कुल वीडियो-लंबाई तय करना
    # ---------------------------------------------------------
    audio_clip, total_video_duration = _build_audio_track(
        is_long_video=is_long_video,
        script_text=script_text,
        long_video_duration_seconds=duration_seconds,
    )

    # ---------------------------------------------------------
    # चरण २: क्रम में सजाए गए विज़ुअल्स को लूप करके फुल-ड्यूरेशन ट्रैक बनाना
    # ---------------------------------------------------------
    background_visual_track = _build_looped_visual_track(
        ordered_media_paths=user_media_list,
        total_duration=total_video_duration,
        target_width=target_width,
        target_height=target_height,
        is_long_video=is_long_video,
    )
    background_visual_track = background_visual_track.set_audio(audio_clip)

    # ---------------------------------------------------------
    # चरण ३: हिंदी सबटाइटल ओवरले लेयर बनाना
    # ---------------------------------------------------------
    subtitle_overlay_clip = _build_subtitle_overlay_clip(
        script_text=script_text,
        video_duration=total_video_duration,
        canvas_width=target_width,
    )

    # ---------------------------------------------------------
    # चरण ४: क्लाइमेक्स लेयर्स (मयूर पंख + आउट्रो) — हमेशा आख़िरी 5.5 सेकंड में
    # ---------------------------------------------------------
    climax_layers = create_climax_layer(
        video_duration=total_video_duration,
        outro_text=outro_text,
        aspect_ratio=aspect_ratio,
    )

    # ---------------------------------------------------------
    # चरण ५: सभी लेयर्स को एक साथ कंपोज़िट करना
    # ---------------------------------------------------------
    all_layers = [background_visual_track, subtitle_overlay_clip, *climax_layers]

    final_composed_video = CompositeVideoClip(
        all_layers, size=(target_width, target_height)
    ).set_duration(total_video_duration)

    # ---------------------------------------------------------
    # चरण ६: स्पीड-लॉक्ड फाइनल रेंडर, क्वालिटी के हिसाब से बिटरेट के साथ
    # ---------------------------------------------------------
    final_composed_video.write_videofile(
        output_video_path,
        fps=RENDER_FPS,
        threads=RENDER_THREADS,
        preset=RENDER_PRESET,
        codec="libx264",
        audio_codec="aac",
        bitrate=export_bitrate,
    )

    # ---------------------------------------------------------
    # सफाई (Cleanup): अस्थायी सबटाइटल PNG हटाना
    # ---------------------------------------------------------
    if os.path.exists(SUBTITLE_TEMP_PNG):
        os.remove(SUBTITLE_TEMP_PNG)

    return output_video_path


# --------------------------------------------------------------
# इस फाइल को सीधे चलाकर टेस्ट करने के लिए (Optional)
# --------------------------------------------------------------
if __name__ == "__main__":
    result_path = compile_cinematic_video(
        user_media_list=["mandir_photo_1.jpg", "mandir_photo_2.jpg", "mandir_visual.mp4"],
        script_text="यह मंदिर सैकड़ों वर्षों पुराना है और इसकी अपनी एक अनोखी कहानी है...",
        outro_text="जय बाबा की! अगला वीडियो जल्द आएगा 🙏",
        output_video_path="final_output.mp4",
        aspect_ratio="9:16",
        duration_seconds=None,
        quality="720p",
    )
    print(f"फाइनल वीडियो यहाँ सेव हुई: {result_path}")
