"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो — engine.py
==============================================================
यह ब्लॉक "कोर वीडियो कंपाइलर इंजन" (Core Video Compiler Engine) है।
इसका काम है बाकी चारों स्वतंत्र ब्लॉक्स —
  voice.py, subtitle.py, climax.py, और यूज़र के मंदिर विजुअल्स —
को एक ही धागे में पिरोकर एक अंतिम 9:16 शॉर्ट्स वीडियो बनाना।

मुख्य फंक्शन: compile_cinematic_video(...)

⚠️ मान्यताएँ (Assumptions) — असली फाइलें उपलब्ध न होने के कारण:
   - voice.py में एक फंक्शन है, मान लीजिए:
       generate_voice_track(script_text, music_duck_percent=15) -> str
     जो अंतिम मिक्स्ड ऑडियो (कहानी + डक किया सितार संगीत) की
     फाइल-पाथ लौटाता है, साथ ही ऑडियो की कुल लंबाई (सेकंड) भी।
   - subtitle.py में यूज़र-बताया गया फंक्शन:
       render_subtitle_html_to_png(text, output_path, ...) -> str
     मौजूद है, जो Playwright से पारदर्शी PNG सबटाइटल बनाता है।
   - climax.py में पहले से बना फंक्शन:
       create_climax_layer(video_duration, outro_text) -> list
     मौजूद है, जो मयूर-पंख + सब्सक्राइब + आउट्रो की सारी लेयर्स
     लौटाता है (और यह भी TextClip का उपयोग नहीं करता, इसलिए
     यहाँ भी कहीं ImageMagick/TextClip नहीं आ रहा)।

अगर आपके असली फंक्शन-नाम/पैरामीटर अलग हैं, तो सिर्फ़ नीचे दिए
IMPORT और उनके CALL बदल दीजिए — बाकी पूरा ढाँचा वैसा ही रहेगा।
==============================================================
"""

import os


from moviepy import AudioFileClip, CompositeVideoClip, ImageClip, VideoFileClip, concatenate_videoclips


# --------------------------------------------------------------
# बाकी तीन स्वतंत्र ब्लॉक्स से ज़रूरी फंक्शन इम्पोर्ट करना
# --------------------------------------------------------------
from voice import create_baba_audio            # ऑडियो (कहानी + डक सितार)
from subtitle import render_subtitle_html_to_png   # हिंदी सबटाइटल PNG
from climax import create_climax_layer             # मयूर पंख + आउट्रो लेयर्स


# --------------------------------------------------------------
# सेटिंग्स (Constants)
# --------------------------------------------------------------
SHORTS_WIDTH = 1080     # 9:16 शॉर्ट्स फॉर्मेट की चौड़ाई
SHORTS_HEIGHT = 1920    # 9:16 शॉर्ट्स फॉर्मेट की ऊँचाई

MUSIC_DUCK_PERCENT = 15   # सितार संगीत को कहानी के नीचे कितना डक करना है

SUBTITLE_TEMP_PNG = "temp_subtitle_overlay.png"   # सबटाइटल PNG का अस्थायी नाम

RENDER_FPS = 24
RENDER_THREADS = 8          # स्पीड लॉक: 8 थ्रेड्स
RENDER_PRESET = "ultrafast"  # स्पीड लॉक: सबसे तेज़ प्रीसेट


# --------------------------------------------------------------
# 1) यूज़र के मंदिर विजुअल्स को लोड करके 9:16 में परफेक्ट फिट करना
# --------------------------------------------------------------
def _load_and_resize_visual(media_path: str, target_duration: float):
    """
    यूज़र द्वारा अपलोड की गई फोटो या वीडियो को लोड करता है और उसे
    1080x1920 (9:16) फॉर्मेट में "क्रॉप-टू-फिल" (crop-to-fill) तरीके
    से रीसाइज़ करता है — यानी पूरी स्क्रीन भरेगी, कहीं काली पट्टी
    (black bar) नहीं बचेगी।

    पैरामीटर:
        media_path (str)       -> फोटो/वीडियो की फाइल-पाथ
        target_duration (float)-> ऑडियो की कुल लंबाई के बराबर
                                   (वीडियो को उतना ही लंबा/लूप करना है)

    रिटर्न:
        VideoFileClip/ImageClip -> 1080x1920 में तैयार क्लिप
    """
    file_extension = os.path.splitext(media_path)[1].lower()
    is_image = file_extension in (".png", ".jpg", ".jpeg", ".webp")

    if is_image:
        # ---- स्थिति 1: यूज़र ने फोटो अपलोड की है ----
        raw_clip = ImageClip(media_path).set_duration(target_duration)
    else:
        # ---- स्थिति 2: यूज़र ने वीडियो अपलोड की है ----
        raw_clip = VideoFileClip(media_path)

        # अगर वीडियो ऑडियो-लंबाई से छोटा है, तो उसे लूप करके बढ़ाना
        if raw_clip.duration < target_duration:
            loop_count = int(target_duration // raw_clip.duration) + 1
            raw_clip = concatenate_videoclips([raw_clip] * loop_count)

        # अंत में ऑडियो की लंबाई तक ही काट देना (trim)
        raw_clip = raw_clip.subclip(0, target_duration)

    # ---- क्रॉप-टू-फिल लॉजिक: पहले बड़ा-किनारा स्केल, फिर बीच से क्रॉप ----
    original_width, original_height = raw_clip.size
    target_aspect_ratio = SHORTS_WIDTH / SHORTS_HEIGHT
    original_aspect_ratio = original_width / original_height

    if original_aspect_ratio > target_aspect_ratio:
        # मूल विजुअल ज़्यादा "चौड़ा" है -> ऊँचाई के अनुसार स्केल करना
        resized_clip = raw_clip.resize(height=SHORTS_HEIGHT)
    else:
        # मूल विजुअल ज़्यादा "लंबा/संकरा" है -> चौड़ाई के अनुसार स्केल करना
        resized_clip = raw_clip.resize(width=SHORTS_WIDTH)

    # स्केल करने के बाद बीच से ठीक 1080x1920 काट लेना (center-crop)
    final_visual_clip = resized_clip.crop(
        x_center=resized_clip.w / 2,
        y_center=resized_clip.h / 2,
        width=SHORTS_WIDTH,
        height=SHORTS_HEIGHT,
    )

    return final_visual_clip


# --------------------------------------------------------------
# 2) हिंदी सबटाइटल ओवरले लेयर बनाना (subtitle.py के ज़रिए)
# --------------------------------------------------------------
def _build_subtitle_overlay_clip(script_text: str, video_duration: float):
    """
    subtitle.py के render_subtitle_html_to_png() को बुलाकर
    Playwright से एक पारदर्शी PNG बनवाता है (जिसमें हिंदी टेक्स्ट
    सही मात्राओं के साथ रेंडर हुआ होता है), फिर उसे स्क्रीन के
    नीचे वाले हिस्से में ImageClip की तरह सेट करता है।

    ⚠️ ध्यान दें: यहाँ भी कहीं TextClip/ImageMagick इस्तेमाल नहीं
    किया गया — पूरा टेक्स्ट पहले से रेंडर की गई PNG इमेज है।
    """
    # Playwright से सबटाइटल PNG बनवाना (पूरा टेक्स्ट पूरे वीडियो पर दिखेगा,
    # अगर टाइम-सिंक्ड सबटाइटल चाहिए तो subtitle.py को टाइमिंग-लिस्ट देनी होगी)
    # ⚠️ फिक्स: पहले यहाँ text=/output_path= नाम से कॉल हो रहा था, जबकि
    # असली subtitle.py फंक्शन text_string/output_image_path लेता है
    # (TypeError आता)। साथ ही canvas_width को SHORTS_WIDTH (1080px) पर
    # सेट किया है ताकि सबटाइटल 1080px चौड़े वीडियो से बाहर न छलके
    # (डिफ़ॉल्ट कैनवस 1600px चौड़ा है)।
    rendered_subtitle_png_path = render_subtitle_html_to_png(
        text_string=script_text,
        output_image_path=SUBTITLE_TEMP_PNG,
        canvas_width=SHORTS_WIDTH,
    )

    subtitle_clip = (
        ImageClip(rendered_subtitle_png_path)
        .set_duration(video_duration)
        .set_position(("center", "bottom"))
    )

    return subtitle_clip


# --------------------------------------------------------------
# 3) मुख्य फंक्शन — यही बाहर से (app.py से) बुलाया जाएगा
# --------------------------------------------------------------
def compile_cinematic_video(
    user_media: str,
    script_text: str,
    outro_text: str,
    output_video_path: str,
) -> str:
    """
    पूरी सिनेमैटिक वीडियो-निर्माण प्रक्रिया को एक जगह जोड़ता है:
      १) voice.py से ऑडियो (कहानी + 15% डक सितार संगीत) जनरेट करवाना
      २) यूज़र के मंदिर विजुअल को 9:16 (1080x1920) में परफेक्ट फिट करना
      ३) subtitle.py से हिंदी सबटाइटल PNG बनवाकर नीचे ओवरले करना
      ४) climax.py से आख़िरी 5.5 सेकंड में मयूर-पंख + आउट्रो जोड़ना
      ५) 'ultrafast' प्रीसेट और 8 थ्रेड्स के साथ तेज़ रेंडर करना

    पैरामीटर:
        user_media (str)         -> यूज़र के मंदिर की फोटो/वीडियो पाथ
        script_text (str)        -> कहानी की स्क्रिप्ट (आवाज़ + सबटाइटल के लिए)
        outro_text (str)         -> क्लाइमेक्स में दिखने वाला कमेंट/नोट
        output_video_path (str)  -> फाइनल वीडियो कहाँ सेव होगी

    रिटर्न:
        str -> फाइनल वीडियो की फाइल-पाथ (output_video_path)
    """

    # ---------------------------------------------------------
    # चरण १: ऑडियो ट्रैक तैयार करना (कहानी + 15% डक सितार संगीत)
    # ---------------------------------------------------------
    final_audio_path = create_baba_audio(script_text, "temp_baba_voice.mp3")
    audio_clip = AudioFileClip(final_audio_path)
    total_video_duration = audio_clip.duration   # वीडियो की कुल लंबाई = ऑडियो जितनी

    # ---------------------------------------------------------
    # चरण २: मंदिर विजुअल को लोड करके 9:16 में रीसाइज़ करना
    # ---------------------------------------------------------
    background_visual_clip = _load_and_resize_visual(
        media_path=user_media,
        target_duration=total_video_duration,
    )
    # ऑडियो को बैकग्राउंड विजुअल पर जोड़ना
    background_visual_clip = background_visual_clip.set_audio(audio_clip)

    # ---------------------------------------------------------
    # चरण ३: हिंदी सबटाइटल ओवरले लेयर बनाना
    # ---------------------------------------------------------
    subtitle_overlay_clip = _build_subtitle_overlay_clip(
        script_text=script_text,
        video_duration=total_video_duration,
    )

    # ---------------------------------------------------------
    # चरण ४: क्लाइमेक्स लेयर्स (मयूर पंख + आउट्रो) लाना
    # ---------------------------------------------------------
    climax_layers = create_climax_layer(
        video_duration=total_video_duration,
        outro_text=outro_text,
    )

    # ---------------------------------------------------------
    # चरण ५: सभी लेयर्स को एक साथ कंपोज़िट करना
    # ---------------------------------------------------------
    # क्रम (order) ज़रूरी है: सबसे नीचे बैकग्राउंड, फिर सबटाइटल,
    # फिर सबसे ऊपर क्लाइमेक्स लेयर्स (ताकि पंख/आउट्रो सबसे ऊपर दिखे)
    all_layers = [background_visual_clip, subtitle_overlay_clip, *climax_layers]

    final_composed_video = CompositeVideoClip(
        all_layers, size=(SHORTS_WIDTH, SHORTS_HEIGHT)
    ).set_duration(total_video_duration)

    # ---------------------------------------------------------
    # चरण ६: स्पीड-लॉक्ड फाइनल रेंडर (40 सेकंड के लक्ष्य के लिए)
    # ---------------------------------------------------------
    # ⚠️ ध्यान दें: 'ultrafast' प्रीसेट फाइल-साइज़ बड़ा कर सकता है,
    # लेकिन रेंडर-स्पीड को अधिकतम करता है, जो कि यहाँ लक्ष्य है।
    final_composed_video.write_videofile(
        output_video_path,
        fps=RENDER_FPS,
        threads=RENDER_THREADS,
        preset=RENDER_PRESET,
        codec="libx264",
        audio_codec="aac",
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
        user_media="mandir_visual.mp4",
        script_text="यह मंदिर सैकड़ों वर्षों पुराना है और इसकी अपनी एक अनोखी कहानी है...",
        outro_text="जय बाबा की! अगला वीडियो जल्द आएगा 🙏",
        output_video_path="final_shorts_output.mp4",
    )
    print(f"फाइनल वीडियो यहाँ सेव हुई: {result_path}")
