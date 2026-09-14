"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो — engine.py (MoviePy 2.x+ वेल्डेड वर्ज़न)
==============================================================
यह ब्लॉक "कोर वीडियो कंपाइलर इंजन" (Core Video Compiler Engine) है।
इसका काम है बाकी स्वतंत्र ब्लॉक्स — voice.py, subtitle.py, climax.py —
और app.py के ४-ट्रैक + लाइव-लूप UI से आए डेटा को एक ही धागे में
पिरोकर अंतिम वीडियो बनाना।

इस वर्ज़न में नया क्या है (app.py के साथ "वेल्डिंग"):
  १. compile_cinematic_video() अब सीधे app.py के _build_common_kwargs() से
     आने वाले असली kwargs स्वीकार करता है — mode, visual_clips (ट्रैक 1),
     video_clips_timeline (ट्रैक 2), music_files_pool (ट्रैक 3),
     music_clips_timeline (ट्रैक 4), master_music_volume, sfx_events,
     sub_color, sub_size, voiceover_mode, custom_audio_path आदि।
  २. दो पूरी तरह अलग मोड्स हैंडल होते हैं:
       - mode="standard"  → सामान्य स्टूडियो मोड (पुराने ३/४-ट्रैक नियम:
         ट्रैक 1 सीक्वेंशियल-लूप्ड बैकग्राउंड, ट्रैक 2 टाइम-सिंक्ड वीडियो-ओवरले,
         ट्रैक 3/4 का म्यूज़िक, SFX-इवेंट्स, हमेशा आख़िरी 5.5 सेकंड में
         मयूर-पंख क्लाइमेक्स ब्लास्ट)
       - mode="live_loop" → 🔄 एआई लाइव लूप स्टूडियो: ट्रैक 1 + ट्रैक 2 के
         मीडिया को एक साझा पूल बनाकर 'while loop' में चक्र-दर-चक्र, हर बार
         अलग सिनेमैटिक स्टाइल (ज़ूम-इन/ज़ूम-आउट Ken Burns, क्रॉसफेड/हार्ड-कट)
         के साथ तब तक दोहराया जाता है जब तक चुना हुआ पूरा duration_seconds
         भर न जाए। आउट्रो/न्यूज़-पट्टी टेक्स्ट पूरी वीडियो में लगातार
         दाएँ-से-बाएँ स्क्रॉलिंग-लूप में दिखती रहती है।
  ३. पूरी फ़ाइल अब MoviePy 2.x+ के नए सिंटैक्स पर चलती है — कहीं भी पुराना
     .set_duration() / .set_position() / .set_audio() / .resize() / .crop() /
     .subclip() / .crossfadein() / .volumex() इस्तेमाल नहीं हुआ। इसकी जगह:
       .with_duration()   .with_position()   .with_audio()   .with_start()
       .resized()         .cropped()         .subclipped()
       .with_effects([vfx.CrossFadeIn(d)])   .with_volume_scaled(factor)
     इस्तेमाल होते हैं, ताकि पुराना "ImageClip object has no attribute
     set_duration" वाला एरर हमेशा के लिए ख़त्म हो जाए।

⚠️ मान्यताएँ (Assumptions) — असली फाइलें उपलब्ध न होने के कारण:
   - voice.py:      create_baba_audio(script_text, output_path) -> str
   - subtitle.py:   render_subtitle_html_to_png(text_string, output_image_path,
                     canvas_width, text_color=None, font_size=None) -> str
                     (⚠️ असली पैरामीटर नाम "font_size" है, "font_size_px" नहीं —
                     यह पहले ग़लती से font_size_px लिख दिया गया था, जिससे
                     "got an unexpected keyword argument 'font_size_px'" एरर
                     आ रहा था। engine.py के अंदर अपना इंटरनल वेरिएबल-नाम अब
                     भी font_size_px है — बस render_subtitle_html_to_png()
                     को कॉल करते वक़्त सही नाम font_size से भेजा जाता है)
   - climax.py:     create_climax_layer(video_duration, outro_text, aspect_ratio)
                     -> list (यह फंक्शन ख़ुद तय करता है कि आख़िरी 5.5 सेकंड में
                     मयूर-पंख/आउट्रो कब दिखाना है, इसलिए यहाँ सिर्फ़ सही
                     total_video_duration पास करना काफ़ी है)
   - प्रोजेक्ट की रूट डायरेक्टरी में "sitar_vadand_sfx.mp3" नाम की एक
     बैकग्राउंड-संगीत फाइल मौजूद है (डिफ़ॉल्ट/फॉलबैक बैकग्राउंड संगीत के लिए)।
   - MoviePy 2.x में vfx इफ़ेक्ट-क्लासेज़ `from moviepy import vfx` से मिलती
     हैं और `clip.with_effects([vfx.CrossFadeIn(duration)])` से लगाई जाती हैं;
     वॉल्यूम स्केल करने के लिए `clip.with_volume_scaled(factor)` मिलता है।
     अगर आपके इंस्टॉल्ड MoviePy वर्ज़न में एक्ज़ैक्ट नाम थोड़े अलग हों, तो
     सिर्फ़ यहाँ इम्पोर्ट/कॉल बदल दीजिए — बाकी पूरा ढाँचा वैसा ही रहेगा।

अगर आपके असली फंक्शन-नाम/फाइल-नाम अलग हैं, तो सिर्फ़ नीचे दिए
IMPORT/CONSTANT बदल दीजिए — बाकी पूरा ढाँचा वैसा ही रहेगा।
==============================================================
"""

import os

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_audioclips,
    concatenate_videoclips,
    vfx,
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
SUBTITLE_TEMP_PNG = "temp_subtitle_overlay.png"       # सबटाइटल PNG का अस्थायी नाम
TICKER_TEMP_PNG = "temp_ticker_overlay.png"            # लाइव-लूप न्यूज़-पट्टी PNG का अस्थायी नाम
SITAR_BACKGROUND_MUSIC_PATH = "sitar_vadand_sfx.mp3"  # डिफ़ॉल्ट/फॉलबैक बैकग्राउंड संगीत

RENDER_FPS = 24
RENDER_THREADS = 8            # स्पीड लॉक: 8 थ्रेड्स
RENDER_PRESET = "ultrafast"   # स्पीड लॉक: सबसे तेज़ प्रीसेट

# --- "देखने लायक" (viral) बनाने वाली सेटिंग्स ---
KEN_BURNS_ZOOM_RATE = 0.06          # फोटो पर कुल कितना % ज़ूम-इन/आउट होगा (स्लॉट के अंत तक)
CROSSFADE_DURATION_SECONDS = 0.6    # हर कट के बीच स्मूद घुलने का समय
SHORTS_SLOT_SECONDS = 4             # Shorts में हर विज़ुअल कितनी देर दिखेगा (सिर्फ़ फॉलबैक के लिए)
LONG_VIDEO_SLOT_SECONDS = 10        # (लेगेसी संदर्भ — अब ट्रैक 1 के हर आइटम की अपनी स्लॉट-लंबाई होती है)
LIVE_LOOP_IMAGE_SLOT_SECONDS = 5.0  # लाइव लूप मोड में हर फोटो कितनी देर दिखेगी

# --- न्यूज़-पट्टी / आउट्रो-लूपर (सिर्फ़ लाइव लूप मोड) ---
TICKER_SCROLL_SPEED_PX_PER_SEC = 220   # पट्टी कितनी तेज़ी से दाएँ-से-बाएँ खिसकेगी
TICKER_BANNER_WIDTH_MULTIPLIER = 2.2   # बैनर की चौड़ाई (कैनवस-चौड़ाई के मुकाबले कितनी बड़ी)
TICKER_BOTTOM_MARGIN_PX = 40           # पट्टी स्क्रीन के नीचे से कितने पिक्सेल ऊपर रहेगी


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
        return audio_clip.subclipped(0, target_duration)

    loops_needed = int(target_duration // audio_clip.duration) + 1
    looped_audio_clip = concatenate_audioclips([audio_clip] * loops_needed)
    return looped_audio_clip.subclipped(0, target_duration)


# --------------------------------------------------------------
# 3) आवाज़ (वॉइसओवर) तैयार करना — AI TTS या कस्टम अपलोडेड ऑडियो
# --------------------------------------------------------------
def _build_voice_or_silence_audio(script_text: str, voiceover_mode: str, custom_audio_path):
    """
    voiceover_mode=="custom" और custom_audio_path दिया गया हो तो वही ऑडियो
    इस्तेमाल होता है। वरना, script_text खाली न हो तो voice.py से बाबा की
    AI आवाज़ बनवाई जाती है। दोनों न हों (जैसे लाइव लूप मोड में) तो कोई आवाज़
    नहीं होगी — (None, 0.0) लौटता है।

    रिटर्न:
        (voice_audio_clip या None, voice_duration_seconds)
    """
    if voiceover_mode == "custom" and custom_audio_path:
        voice_audio_clip = AudioFileClip(custom_audio_path)
        return voice_audio_clip, voice_audio_clip.duration

    if script_text and script_text.strip():
        final_audio_path = create_baba_audio(script_text, "temp_baba_voice.mp3")
        voice_audio_clip = AudioFileClip(final_audio_path)
        return voice_audio_clip, voice_audio_clip.duration

    return None, 0.0


# --------------------------------------------------------------
# 4) एक क्लिप को टारगेट साइज़ में क्रॉप-टू-फिल करना (शेयर्ड हेल्पर)
# --------------------------------------------------------------
def _fit_clip_to_canvas(raw_clip, target_width: int, target_height: int):
    """
    पहले बड़ा-किनारा स्केल करता है, फिर बीच से टारगेट-साइज़ काटता है —
    ताकि क्लिप का ओरिजिनल अनुपात (aspect ratio) बिगड़े बिना पूरा फ्रेम भरे।
    """
    original_width, original_height = raw_clip.size
    target_aspect_ratio = target_width / target_height
    original_aspect_ratio = original_width / original_height

    if original_aspect_ratio > target_aspect_ratio:
        resized_clip = raw_clip.resized(height=target_height)
    else:
        resized_clip = raw_clip.resized(width=target_width)

    cropped_clip = resized_clip.cropped(
        x_center=resized_clip.w / 2,
        y_center=resized_clip.h / 2,
        width=target_width,
        height=target_height,
    )
    return cropped_clip


# --------------------------------------------------------------
# 5अ) ट्रैक 1 (गोदाम) से मुख्य पृष्ठभूमि विज़ुअल-ट्रैक — हर आइटम की अपनी स्लॉट-लंबाई
# --------------------------------------------------------------
def _load_single_visual_clip_track1(item: dict, target_width: int, target_height: int, remaining_duration: float):
    """
    गोदाम का एक आइटम लेकर उसे उसकी फिक्स ५ सेकंड की स्लॉट-लंबाई के लिए तैयार करता है।
    तस्वीरों पर Ken Burns ज़ूम इफ़ेक्ट लागू करता है और वीडियो को सही से ट्रिम करता है।
    """
    # गोदाम में हमने टाइमर हटा दिया था, इसलिए हर फोटो फिक्स 5 सेकंड चलेगी
    slot_duration = min(5.0, remaining_duration)
    
    if item["is_image"]:
        raw_clip = ImageClip(item["path"]).with_duration(slot_duration)
    else:
        raw_clip = VideoFileClip(item["path"])
        # वीडियो क्लिप की अपनी लंबाई या बची हुई ड्यूरेशन में से जो छोटा हो
        clip_dur = raw_clip.duration if raw_clip.duration > 0 else 5.0
        slot_duration = min(clip_dur, remaining_duration)
        raw_clip = raw_clip.subclipped(0, slot_duration)
        
    prepared_clip = _fit_clip_to_canvas(raw_clip, target_width, target_height)
    
    if item["is_image"]:
        prepared_clip = prepared_clip.resized(
            lambda t: 1 + KEN_BURNS_ZOOM_RATE * (t / max(slot_duration, 0.001))
        )
    return prepared_clip, slot_duration

def _build_track1_looped_visual_track(visual_clips: list, total_duration: float, target_width: int, target_height: int):
    """
    गोदाम के सभी विज़ुअल्स को क्रम से (बारी-बारी से) एक-एक करके उठाता है।
    पूरी लिस्ट खत्म होने पर ही वापस पहली फाइल से चक्र (loop) शुरू करता है,
    जिससे गोदाम की हर एक इमेज वीडियो में साफ़ दिखाई दे।
    """
    if not visual_clips:
        raise ValueError("कम-से-कम एक विज़ुअल (ट्रैक 1) ज़रूरी है।")
        
    visual_clips_sequence = []
    elapsed_duration = 0.0
    cycle_index = 0
    total_items = len(visual_clips)
    
    # जब तक पूरे वीडियो का टाइम (जैसे 35 सेकंड) पूरा नहीं होता, चक्र चलाते रहो
    while elapsed_duration < total_duration - 0.01:
        # यह लाइन बारी-बारी से 0, 1, 2, 3 इंडेक्स की फाइलें उठाएगी
        item = visual_clips[cycle_index % total_items]
        remaining_duration = total_duration - elapsed_duration
        
        prepared_clip, slot_duration = _load_single_visual_clip_track1(
            item, target_width, target_height, remaining_duration
        )
        
        if slot_duration <= 0:
            break
            
        # हर क्लिप को उसकी सही टाइमलाइन पोजीशन पर सेट करना ताकि वे ओवरलैप न हों
        prepared_clip = prepared_clip.with_start(elapsed_duration)
        
        if visual_clips_sequence:
            prepared_clip = prepared_clip.with_effects([vfx.CrossFadeIn(CROSSFADE_DURATION_SECONDS)])
            
        visual_clips_sequence.append(prepared_clip)
        elapsed_duration += slot_duration
        cycle_index += 1 # इंडेक्स को आगे बढ़ाओ ताकि अगली इमेज लोड हो सके
        
    combined_visual_track = concatenate_videoclips(
        visual_clips_sequence, method="compose", padding=-CROSSFADE_DURATION_SECONDS
    )
    
    combined_visual_track = combined_visual_track.cropped(
        x_center=combined_visual_track.w / 2,
        y_center=combined_visual_track.h / 2,
        width=target_width,
        height=target_height,
    ).with_duration(total_duration)
    
    return combined_visual_track





# --------------------------------------------------------------
# 5ब) ट्रैक 2 — वीडियो क्लिप्स टाइमलाइन: हर क्लिप अपने तय Start/End सेकंड पर ओवरले होती है
# --------------------------------------------------------------
def _build_track2_overlay_clips(video_clips_timeline: list, target_width: int, target_height: int):
    """
    ट्रैक 2 के हर आइटम {"path","start","end"} को उसके अपने Start Second पर
    "प्रकट" होने वाली और End Second पर "हटने" वाली एक स्वतंत्र ओवरले-क्लिप
    बनाकर लौटाता है — ये मुख्य पृष्ठभूमि (ट्रैक 1) के ऊपर कंपोज़िट होती हैं।
    """
    overlay_clips = []
    for item in video_clips_timeline:
        raw_clip = VideoFileClip(item["path"])
        start_time = max(item["start"], 0.0)
        window_duration = item["end"] - start_time if item["end"] > start_time else raw_clip.duration
        window_duration = min(window_duration, raw_clip.duration)
        if window_duration <= 0:
            continue

        trimmed_clip = raw_clip.subclipped(0, window_duration)
        prepared_clip = _fit_clip_to_canvas(trimmed_clip, target_width, target_height)
        prepared_clip = prepared_clip.with_start(start_time)
        overlay_clips.append(prepared_clip)

    return overlay_clips


# --------------------------------------------------------------
# 5स) म्यूज़िक लेयर — ट्रैक 4 (टाइम-सिंक्ड क्लिप्स) प्राथमिकता, वरना ट्रैक 3 (गोदाम),
#     वरना डिफ़ॉल्ट सितार बैकग्राउंड-संगीत
# --------------------------------------------------------------
def _build_music_layer_for_standard_mode(music_clips_timeline: list, music_files_pool: list, master_music_volume: float, total_video_duration: float):
    layered_music_clips = []

    if music_clips_timeline:
        # ट्रैक 4: हर क्लिप अपने तय Start Second पर बजना शुरू होती है। "order" सिर्फ़
        # यूज़र की समझ/क्रम के लिए है — ऑडियो-मिक्सिंग में सभी लेयर्स वैसे भी एक-साथ बजती हैं।
        for music_item in sorted(music_clips_timeline, key=lambda m: m["order"]):
            raw_clip = AudioFileClip(music_item["path"])
            segment_start = max(music_item["start"], 0.0)
            segment_duration = music_item["end"] - segment_start if music_item["end"] > segment_start else raw_clip.duration
            segment_duration = min(segment_duration, raw_clip.duration)
            if segment_duration <= 0:
                continue
            trimmed_clip = raw_clip.subclipped(0, segment_duration).with_start(segment_start)
            layered_music_clips.append(trimmed_clip)

    elif music_files_pool:
        # कोई टाइम-सिंक्ड म्यूज़िक-क्लिप नहीं दी गई — ट्रैक 3 (गोदाम) के भजनों को
        # क्रम से जोड़कर पूरी वीडियो-लंबाई तक लूप कर देना (निरंतर बैकग्राउंड भजन)
        pool_clips = [AudioFileClip(path) for path in music_files_pool]
        concatenated_pool_clip = concatenate_audioclips(pool_clips)
        looped_pool_clip = _loop_audio_clip_to_duration(concatenated_pool_clip, total_video_duration)
        layered_music_clips.append(looped_pool_clip)

    else:
        # कुछ भी अपलोड नहीं हुआ — डिफ़ॉल्ट सितार बैकग्राउंड-संगीत
        sitar_bg_clip = AudioFileClip(SITAR_BACKGROUND_MUSIC_PATH)
        looped_sitar_clip = _loop_audio_clip_to_duration(sitar_bg_clip, total_video_duration)
        layered_music_clips.append(looped_sitar_clip)

    if not layered_music_clips:
        return None

    combined_music_layer = CompositeAudioClip(layered_music_clips).with_duration(total_video_duration)
    return combined_music_layer.with_volume_scaled(master_music_volume)


# --------------------------------------------------------------
# 5द) SFX लेयर — शंखनाद/डमरू आदि इवेंट्स, हर एक अपने तय Start/End सेकंड पर
# --------------------------------------------------------------
def _build_sfx_layer(sfx_events: list, total_video_duration: float):
    sfx_audio_clips = []
    for sfx_item in sfx_events:
        if not sfx_item.get("path"):
            # बिल्ट-इन प्रीसेट ध्वनि (जैसे "शंखनाद 🐚") अभी असली फाइल के तौर पर उपलब्ध
            # नहीं है — TODO: प्रीसेट-साउंड लाइब्रेरी जोड़कर sfx_name से मैप करना
            continue
        raw_sfx_clip = AudioFileClip(sfx_item["path"])
        sfx_start = max(sfx_item["start"], 0.0)
        sfx_duration = sfx_item["end"] - sfx_start if sfx_item["end"] > sfx_start else raw_sfx_clip.duration
        sfx_duration = min(sfx_duration, raw_sfx_clip.duration)
        if sfx_duration <= 0:
            continue
        trimmed_sfx_clip = (
            raw_sfx_clip.subclipped(0, sfx_duration)
            .with_start(sfx_start)
            .with_volume_scaled(sfx_item["volume"])
        )
        sfx_audio_clips.append(trimmed_sfx_clip)

    if not sfx_audio_clips:
        return None
    return CompositeAudioClip(sfx_audio_clips).with_duration(total_video_duration)


def _combine_all_audio_layers(voice_clip, music_layer, sfx_layer, total_video_duration: float):
    active_layers = [layer for layer in (voice_clip, music_layer, sfx_layer) if layer is not None]
    if not active_layers:
        return None
    return CompositeAudioClip(active_layers).with_duration(total_video_duration)


# --------------------------------------------------------------
# 5य) हिंदी सबटाइटल ओवरले लेयर बनाना (subtitle.py के ज़रिए)
# --------------------------------------------------------------
def _build_subtitle_overlay_clip(script_text: str, video_duration: float, canvas_width: int, text_color: str, font_size_px: int):
    """
    subtitle.py से Playwright के ज़रिए एक पारदर्शी PNG बनवाकर उसे स्क्रीन के
    नीचे वाले हिस्से में ओवरले करता है। script_text खाली हो (जैसे लाइव लूप
    मोड में) तो कोई सबटाइटल नहीं दिखाया जाता — None लौटता है।
    """
    if not script_text or not script_text.strip():
        return None

    rendered_subtitle_png_path = render_subtitle_html_to_png(
        text_string=script_text,
        output_image_path=SUBTITLE_TEMP_PNG,
        canvas_width=canvas_width,
        text_color=text_color,
        # ⚠️ फिक्स: असली subtitle.py का पैरामीटर नाम "font_size" है, "font_size_px"
        # नहीं — इसलिए यहाँ फंक्शन के अपने इंटरनल पैरामीटर (font_size_px) की वैल्यू
        # को render_subtitle_html_to_png() को सही नाम "font_size" से भेजा जा रहा है।
        font_size=font_size_px,
    )

    subtitle_clip = (
        ImageClip(rendered_subtitle_png_path)
        .with_duration(video_duration)
        # ⚠️ फिक्स: MoviePy 2.x+ में .with_position() को टुपल (x, y) नहीं,
        # बल्कि लिस्ट [x, y] चाहिए — वरना "int() argument must be... not
        # 'tuple'" वाला एरर आता है। इसलिए यहाँ गोल-कोष्ठक की जगह स्क्वायर-ब्रैकेट।
        .with_position(["center", "bottom"])
    )
    return subtitle_clip


# --------------------------------------------------------------
# 5र) सामान्य मोड का पूरा कंपाइलर — ऊपर के सभी हेल्पर्स को जोड़ता है
# --------------------------------------------------------------
def _compile_standard_mode(
    visual_clips, video_clips_timeline, music_files_pool, music_clips_timeline,
    master_music_volume, sfx_events, script_text, outro_text, aspect_ratio,
    duration_seconds, target_width, target_height, sub_color, sub_size,
    voiceover_mode, custom_audio_path, outro_voice_active,
):
    is_long_format = aspect_ratio == "16:9"

    # चरण १: आवाज़ (वॉइसओवर) तैयार करना
    voice_clip, voice_duration = _build_voice_or_silence_audio(script_text, voiceover_mode, custom_audio_path)

    # चरण २: कुल वीडियो-लंबाई तय करना
    if is_long_format:
        if not duration_seconds:
            raise ValueError("Long Video के लिए duration_seconds ज़रूर दिया जाना चाहिए।")
        total_video_duration = duration_seconds
    else:
        total_video_duration = voice_duration if voice_duration > 0 else SHORTS_SLOT_SECONDS

    # चरण ३: ट्रैक 1 (गोदाम) से मुख्य पृष्ठभूमि विज़ुअल-ट्रैक बनाना
    background_visual_track = _build_track1_looped_visual_track(
        visual_clips=visual_clips, total_duration=total_video_duration,
        target_width=target_width, target_height=target_height,
    )

    # चरण ४: ट्रैक 2 के वीडियो-क्लिप्स को उनके तय Start/End सेकंड पर ओवरले करना
    track2_overlay_clips = _build_track2_overlay_clips(video_clips_timeline, target_width, target_height)

    # चरण ५: ऑडियो — म्यूज़िक (ट्रैक 3/4) + SFX (शंखनाद इवेंट्स) + आवाज़, सबको मिलाना
    music_layer = _build_music_layer_for_standard_mode(
        music_clips_timeline, music_files_pool, master_music_volume, total_video_duration,
    )
    sfx_layer = _build_sfx_layer(sfx_events, total_video_duration)
    combined_audio = _combine_all_audio_layers(voice_clip, music_layer, sfx_layer, total_video_duration)
    if combined_audio is not None:
        background_visual_track = background_visual_track.with_audio(combined_audio)

    # चरण ६: हिंदी सबटाइटल ओवरले
    subtitle_overlay_clip = _build_subtitle_overlay_clip(
        script_text=script_text, video_duration=total_video_duration,
        canvas_width=target_width, text_color=sub_color, font_size_px=sub_size,
    )

    # चरण ७: क्लाइमेक्स लेयर्स (मयूर पंख + आउट्रो) — हमेशा आख़िरी 5.5 सेकंड में
   climax_layers, combined_audio, total_video_duration = _build_climax_with_cta_voice(total_video_duration, outro_text, aspect_ratio, outro_voice_active, combined_audio)


    # चरण ८: सभी लेयर्स को एक साथ कंपोज़िट करना
    all_layers = [background_visual_track, *track2_overlay_clips]
    if subtitle_overlay_clip is not None:
        all_layers.append(subtitle_overlay_clip)
    all_layers.extend(climax_layers)

    final_composed_video = CompositeVideoClip(
        all_layers, size=(target_width, target_height),
    ).with_duration(total_video_duration)

    return final_composed_video, total_video_duration


# ================================================================
# 🔄 एआई लाइव लूप स्टूडियो मोड (mode == "live_loop") के हेल्पर्स
# ================================================================

def _load_single_visual_clip_live_loop(media_item: dict, target_width: int, target_height: int, remaining_duration: float, style_variant_index: int):
    """
    लाइव लूप मोड में हर स्लॉट को बारी-बारी अलग सिनेमैटिक स्टाइल देता है ताकि
    लंबा रिपीट-वीडियो भी बोरिंग न लगे:
      0 → ज़ूम-इन (Ken Burns) + अगली क्लिप से क्रॉसफेड
      1 → हल्का ज़ूम-आउट, हार्ड-कट (बिना क्रॉसफेड)
      2 → ज़ूम-इन (भारी क्रॉसफेड)
      3 → स्थिर फ्रेम (कोई ज़ूम नहीं), हार्ड-कट
    """
    if media_item["is_image"]:
        slot_duration = min(LIVE_LOOP_IMAGE_SLOT_SECONDS, remaining_duration)
        raw_clip = ImageClip(media_item["path"]).with_duration(slot_duration)
    else:
        raw_clip = VideoFileClip(media_item["path"])
        slot_duration = min(raw_clip.duration, remaining_duration)
        raw_clip = raw_clip.subclipped(0, slot_duration)

    prepared_clip = _fit_clip_to_canvas(raw_clip, target_width, target_height)

    if media_item["is_image"] and style_variant_index == 1:
        # हल्का ज़ूम-आउट: थोड़ा बड़ा होकर वापस सामान्य साइज़ पर आना
        prepared_clip = prepared_clip.resized(
            lambda t: (1 + KEN_BURNS_ZOOM_RATE) - KEN_BURNS_ZOOM_RATE * (t / max(slot_duration, 0.001))
        )
    elif media_item["is_image"] and style_variant_index in (0, 2):
        # ज़ूम-इन — स्टाइल 2 पर नीचे क्रॉसफेड भी अतिरिक्त जुड़ता है
        prepared_clip = prepared_clip.resized(
            lambda t: 1 + KEN_BURNS_ZOOM_RATE * (t / max(slot_duration, 0.001))
        )
    # style_variant_index == 3 (या वीडियो-आइटम): कोई ज़ूम नहीं, स्थिर/नैचुरल फ्रेम

    return prepared_clip, slot_duration


def _build_live_loop_visual_track(visual_clips: list, video_clips_timeline: list, total_duration: float, target_width: int, target_height: int):
    """
    ट्रैक 1 (गोदाम) + ट्रैक 2 (टाइमलाइन स्लॉट्स — यहाँ सिर्फ़ मीडिया-सोर्स के तौर
    पर लिए जाते हैं, उनके अपने Start/End इस मोड में इस्तेमाल नहीं होते) — दोनों
    को मिलाकर एक साझा पूल बनाया जाता है, फिर एक 'while loop' उसे तब तक चक्र में
    घुमाता रहता है — हर बार अलग स्टाइल के साथ — जब तक total_duration भर न जाए।
    """
    combined_media_pool = [
        {"path": item["path"], "is_image": item["is_image"]} for item in visual_clips
    ] + [
        {"path": item["path"], "is_image": False} for item in video_clips_timeline
    ]

    if not combined_media_pool:
        raise ValueError("लाइव लूप मोड के लिए कम-से-कम एक विज़ुअल (ट्रैक 1) या वीडियो-क्लिप (ट्रैक 2) ज़रूरी है।")

    visual_clips_sequence = []
    elapsed_duration = 0.0
    cycle_index = 0
    total_items = len(combined_media_pool)

    # ---- 🔄 महा-लूपिंग व्हाइल-लूप: जब तक पूरा चुना हुआ ड्यूरेशन भर न जाए ----
    while elapsed_duration < total_duration - 0.01:
        media_item = combined_media_pool[cycle_index % total_items]
        remaining_duration = total_duration - elapsed_duration
        style_variant_index = cycle_index % 4   # हर चक्र में स्टाइल बदलती रहे — विविधता के लिए

        prepared_clip, slot_duration = _load_single_visual_clip_live_loop(
            media_item, target_width, target_height, remaining_duration, style_variant_index,
        )
        if slot_duration <= 0:
            break

        use_crossfade = style_variant_index in (0, 2)   # आधे कट क्रॉसफेड, आधे हार्ड-कट — विविधता
        if visual_clips_sequence and use_crossfade:
            prepared_clip = prepared_clip.with_effects([vfx.CrossFadeIn(CROSSFADE_DURATION_SECONDS)])

        visual_clips_sequence.append(prepared_clip)
        elapsed_duration += slot_duration
        cycle_index += 1

    combined_visual_track = concatenate_videoclips(
        visual_clips_sequence, method="compose", padding=-CROSSFADE_DURATION_SECONDS,
    )
    combined_visual_track = combined_visual_track.cropped(
        x_center=combined_visual_track.w / 2,
        y_center=combined_visual_track.h / 2,
        width=target_width,
        height=target_height,
    ).with_duration(total_duration)

    return combined_visual_track


def _build_scrolling_ticker_overlay_clip(outro_text: str, video_duration: float, canvas_width: int, canvas_height: int):
    """
    न्यूज़-पट्टी/आउट्रो टेक्स्ट को एक चौड़े पारदर्शी बैनर-PNG में रेंडर करके,
    उसे पूरी वीडियो-लंबाई तक लगातार दाएँ किनारे से अंदर आकर बाएँ किनारे से
    बाहर निकलते हुए (और फिर से लूप होकर वापस दाएँ से आते हुए) दिखाता है —
    यानी एक सतत "Scrolling Timeline Loop"।
    """
    if not outro_text or not outro_text.strip():
        return None

    banner_width = int(canvas_width * TICKER_BANNER_WIDTH_MULTIPLIER)
    ticker_png_path = render_subtitle_html_to_png(
        text_string=outro_text,
        output_image_path=TICKER_TEMP_PNG,
        canvas_width=banner_width,
    )

    ticker_image_clip = ImageClip(ticker_png_path).with_duration(video_duration)
    banner_height = ticker_image_clip.h
    ticker_y_position = canvas_height - banner_height - TICKER_BOTTOM_MARGIN_PX
    cycle_distance = banner_width + canvas_width   # दाएँ किनारे से पूरी तरह बाहर निकलने तक की दूरी

    def _ticker_x_position(t):
        traveled_distance = (t * TICKER_SCROLL_SPEED_PX_PER_SEC) % cycle_distance
        return canvas_width - traveled_distance

    # ⚠️ फिक्स: MoviePy 2.x+ में .with_position() को टुपल (x, y) की जगह
    # लिस्ट [x, y] चाहिए — वरना "int() argument must be... not 'tuple'"
    # एरर आता है। इसलिए यहाँ lambda भी गोल-कोष्ठक (...) नहीं, स्क्वायर-ब्रैकेट [...] लौटाता है।
    return ticker_image_clip.with_position(lambda t: [_ticker_x_position(t), ticker_y_position])


def _compile_live_loop_mode(
    visual_clips, video_clips_timeline, outro_text, duration_seconds,
    target_width, target_height, master_music_volume, outro_voice_active, aspect_ratio,
):
    if not duration_seconds:
        raise ValueError("लाइव लूप मोड के लिए duration_seconds ज़रूर दिया जाना चाहिए।")
    total_video_duration = duration_seconds

    # चरण १: ट्रैक 1 + ट्रैक 2 को मिलाकर 'while loop' में चक्र-दर-चक्र भरना (अलग-अलग स्टाइल्स)
    background_visual_track = _build_live_loop_visual_track(
        visual_clips=visual_clips, video_clips_timeline=video_clips_timeline,
        total_duration=total_video_duration, target_width=target_width, target_height=target_height,
    )

    # चरण २: बैकग्राउंड ऑडियो — इस मोड में कोई अलग म्यूज़िक/SFX ट्रैक नहीं आता,
    # इसलिए डिफ़ॉल्ट सितार-संगीत को पूरी ड्यूरेशन तक लूप करके बजाया जाता है
    sitar_bg_clip = AudioFileClip(SITAR_BACKGROUND_MUSIC_PATH)
    looped_bg_audio = _loop_audio_clip_to_duration(sitar_bg_clip, total_video_duration)
    looped_bg_audio = looped_bg_audio.with_volume_scaled(master_music_volume)
    background_visual_track = background_visual_track.with_audio(looped_bg_audio)

    # चरण ३: न्यूज़-पट्टी/आउट्रो — पूरी वीडियो में लगातार स्क्रॉलिंग-लूप में दिखेगी
    scrolling_ticker_clip = _build_scrolling_ticker_overlay_clip(
        outro_text=outro_text, video_duration=total_video_duration,
        canvas_width=target_width, canvas_height=target_height,
    )

    # चरण ४: क्लाइमेक्स लेयर्स — मयूर-पंख हमेशा आख़िरी 5.5 सेकंड में (लंबे लूप वीडियो में भी)
    climax_layers = (
        create_climax_layer(video_duration=total_video_duration, outro_text=outro_text, aspect_ratio=aspect_ratio)
        if outro_voice_active else []
    )

    all_layers = [background_visual_track]
    if scrolling_ticker_clip is not None:
        all_layers.append(scrolling_ticker_clip)
    all_layers.extend(climax_layers)

    final_composed_video = CompositeVideoClip(
        all_layers, size=(target_width, target_height),
    ).with_duration(total_video_duration)

    return final_composed_video


# --------------------------------------------------------------
# 6) मुख्य फंक्शन — यही बाहर से (app.py से) बुलाया जाएगा
# --------------------------------------------------------------
def compile_cinematic_video(
    mode: str = "standard",
    visual_clips: list = None,
    video_clips_timeline: list = None,
    music_files_pool: list = None,
    music_clips_timeline: list = None,
    master_music_volume: float = 0.8,
    sfx_events: list = None,
    script_text: str = "",
    outro_text: str = "",
    output_video_path: str = "final_output.mp4",
    aspect_ratio: str = "9:16",
    duration_seconds=None,
    quality: str = "720p",
    sub_color: str = "#FFD700",
    sub_size: int = 65,
    voiceover_mode: str = "ai_tts",
    custom_audio_path=None,
    outro_voice_active: bool = True,
) -> str:
    """
    पूरी सिनेमैटिक वीडियो-निर्माण प्रक्रिया को एक जगह जोड़ता है, और
    mode के अनुसार दो बिल्कुल अलग रास्तों में बँट जाता है:

      mode="standard"  → ट्रैक 1 (सीक्वेंशियल-लूप्ड बैकग्राउंड) + ट्रैक 2
                          (टाइम-सिंक्ड वीडियो-ओवरले) + ट्रैक 3/4 का म्यूज़िक +
                          SFX-इवेंट्स + हिंदी सबटाइटल + आवाज़ + क्लाइमेक्स
      mode="live_loop" → ट्रैक 1 + ट्रैक 2 का साझा मीडिया-पूल एक व्हाइल-लूप
                          में चक्र-दर-चक्र दोहराया जाता है (अलग-अलग स्टाइल्स
                          के साथ) + लगातार स्क्रॉलिंग न्यूज़-पट्टी + क्लाइमेक्स

    दोनों मोड्स में आख़िरी 5.5 सेकंड में मयूर-पंख क्लाइमेक्स ब्लास्ट (climax.py
    के ज़रिए) हमेशा लागू होता है (जब तक outro_voice_active=True हो)।

    रिटर्न:
        str -> फाइनल वीडियो की फाइल-पाथ (output_video_path)
    """
    visual_clips = visual_clips or []
    video_clips_timeline = video_clips_timeline or []
    music_files_pool = music_files_pool or []
    music_clips_timeline = music_clips_timeline or []
    sfx_events = sfx_events or []

    target_width, target_height, export_bitrate = _resolve_export_settings(aspect_ratio, quality)

    if mode == "live_loop":
        final_composed_video = _compile_live_loop_mode(
            visual_clips=visual_clips,
            video_clips_timeline=video_clips_timeline,
            outro_text=outro_text,
            duration_seconds=duration_seconds,
            target_width=target_width,
            target_height=target_height,
            master_music_volume=master_music_volume,
            outro_voice_active=outro_voice_active,
            aspect_ratio=aspect_ratio,
        )
    else:
        final_composed_video, _ = _compile_standard_mode(
            visual_clips=visual_clips,
            video_clips_timeline=video_clips_timeline,
            music_files_pool=music_files_pool,
            music_clips_timeline=music_clips_timeline,
            master_music_volume=master_music_volume,
            sfx_events=sfx_events,
            script_text=script_text,
            outro_text=outro_text,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            target_width=target_width,
            target_height=target_height,
            sub_color=sub_color,
            sub_size=sub_size,
            voiceover_mode=voiceover_mode,
            custom_audio_path=custom_audio_path,
            outro_voice_active=outro_voice_active,
        )

    # ---------------------------------------------------------
    # स्पीड-लॉक्ड फाइनल रेंडर, क्वालिटी के हिसाब से बिटरेट के साथ
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
    # सफाई (Cleanup): अस्थायी सबटाइटल/टिकर PNG हटाना
    # ---------------------------------------------------------
    for temp_png_path in (SUBTITLE_TEMP_PNG, TICKER_TEMP_PNG):
        if os.path.exists(temp_png_path):
            os.remove(temp_png_path)

    return output_video_path


# --------------------------------------------------------------
# इस फाइल को सीधे चलाकर टेस्ट करने के लिए (Optional)
# --------------------------------------------------------------
if __name__ == "__main__":
    # --- उदाहरण १: सामान्य स्टूडियो मोड ---
    standard_result_path = compile_cinematic_video(
        mode="standard",
        visual_clips=[
            {"path": "mandir_photo_1.jpg", "is_image": True, "start": 0.0, "end": 5.0},
            {"path": "mandir_visual.mp4", "is_image": False, "start": 0.0, "end": 0.0},
        ],
        video_clips_timeline=[],
        music_files_pool=[],
        music_clips_timeline=[],
        master_music_volume=0.8,
        sfx_events=[],
        script_text="यह मंदिर सैकड़ों वर्षों पुराना है और इसकी अपनी एक अनोखी कहानी है...",
        outro_text="जय बाबा की! अगला वीडियो जल्द आएगा 🙏",
        output_video_path="final_output_standard.mp4",
        aspect_ratio="9:16",
        duration_seconds=None,
        quality="720p",
        sub_color="#FFD700",
        sub_size=65,
        voiceover_mode="ai_tts",
        custom_audio_path=None,
    )
    print(f"फाइनल (सामान्य मोड) वीडियो यहाँ सेव हुई: {standard_result_path}")

    # --- उदाहरण २: 🔄 लाइव लूप मोड ---
    live_loop_result_path = compile_cinematic_video(
        mode="live_loop",
        visual_clips=[
            {"path": "mandir_photo_1.jpg", "is_image": True, "start": 0.0, "end": 5.0},
            {"path": "mandir_photo_2.jpg", "is_image": True, "start": 0.0, "end": 5.0},
        ],
        video_clips_timeline=[
            {"path": "mandir_visual.mp4", "start": 0.0, "end": 0.0},
        ],
        outro_text="जय बाबा की! 🙏 अगला दर्शन जल्द",
        output_video_path="final_output_live_loop.mp4",
        aspect_ratio="16:9",
        duration_seconds=300,   # 5 मिनट
        quality="720p",
        master_music_volume=0.8,
    )
    print(f"फाइनल (लाइव लूप मोड) वीडियो यहाँ सेव हुई: {live_loop_result_path}")


"""
==============================================================
engine.py में जोड़ने के लिए नया हिस्सा — CTA वॉइस + हार्ड-कट डकिंग
==============================================================
🆕 यह cloud_media_director_studio.py के इन दो फंक्शन्स से सीखा गया तरीका है:
   - build_cta_tail()       -> असली बोली गई "Like/Subscribe" आवाज़ बनाना,
                                उसकी असली लंबाई नापना, CTA-विंडो उसी हिसाब से तय करना
   - duck_audio_for_cta()   -> बैकग्राउंड-म्यूज़िक को hard-cut (कोई fade नहीं)
                                तरीके से CTA के दौरान धीमा करना

इसे अपनी मौजूदा engine.py में इस तरह जोड़ें:
  1) नीचे दिए दोनों फंक्शन (_build_cta_voice_audio, _duck_audio_hard_cut)
     को engine.py में climax.py के इम्पोर्ट के नीचे कहीं भी पेस्ट करें।
  2) _compile_standard_mode() (या जो भी आपका मुख्य कंपाइलर फंक्शन है) में
     "climax_layers = create_climax_layer(...)" वाली लाइन को नीचे दिए
     "चरण ७ (अपडेटेड)" वाले ब्लॉक से replace करें।
==============================================================
"""

import os

from moviepy import AudioFileClip, concatenate_audioclips

from voice import create_baba_audio     # पहले से मौजूद — बाबा की AI आवाज़ बनाने वाला फंक्शन
from climax import create_climax_layer, SUBSCRIBE_MESSAGE   # SUBSCRIBE_MESSAGE अब climax.py से एक्सपोर्ट होता है


# --------------------------------------------------------------
# 🆕 १) असली बोली गई CTA-आवाज़ बनाना ("Channel ko like, subscribe karein" + outro_text)
# --------------------------------------------------------------
def _build_cta_voice_audio(outro_text: str) -> tuple:
    """
    voice.py के create_baba_audio() से CTA की असली बोली हुई आवाज़ बनाता है:
    "Channel ko like, subscribe karein" + यूज़र का outro_text एक साथ।

    🔐 सुरक्षा: अगर आवाज़ बनाने में कोई भी दिक्कत आए (जैसे edge-tts का
    नेटवर्क-टाइमआउट), तो यह क्रैश नहीं करता — सिर्फ़ (None, 0.0) लौटा देता
    है, ताकि पूरा वीडियो बिना CTA-आवाज़ के भी (सिर्फ़ टेक्स्ट/पंख के साथ)
    आगे रेंडर हो सके।

    रिटर्न:
        (cta_audio_clip या None, cta_audio_duration_seconds)
    """
    cta_spoken_text = SUBSCRIBE_MESSAGE
    if outro_text and outro_text.strip():
        cta_spoken_text = f"{SUBSCRIBE_MESSAGE}. {outro_text.strip()}"

    try:
        cta_audio_path = create_baba_audio(cta_spoken_text, "temp_cta_voice.mp3")
        cta_audio_clip = AudioFileClip(cta_audio_path)
        return cta_audio_clip, cta_audio_clip.duration
    except Exception as cta_voice_error:
        print(f"⚠️ [ऑटो-स्किप] CTA-आवाज़ नहीं बन सकी — क्लाइमेक्स सिर्फ़ विज़ुअल (बिना आवाज़) रहेगा: {cta_voice_error}")
        return None, 0.0


# --------------------------------------------------------------
# 🆕 २) बैकग्राउंड-ऑडियो को CTA के दौरान "हार्ड-कट" तरीके से धीमा करना
# --------------------------------------------------------------
def _duck_audio_hard_cut(background_audio_clip, duck_start_time: float, total_duration: float, duck_volume: float = 0.5):
    """
    cloud_media_director_studio.py के duck_audio_for_cta() से लिया गया
    तरीका: बैकग्राउंड-ऑडियो को दो हिस्सों में काटकर सीधे वॉल्यूम बदलना —
    कोई fade-in/fade-out इफ़ेक्ट-चेन नहीं जोड़ना।

    ⚠️ क्यों ज़रूरी है: दो अलग "smoothing" इफ़ेक्ट (fade + volume-change)
    एक साथ लगाने से ट्रांज़िशन "धीमा/लड़खड़ाता हुआ" (warped) सुनाई देता है।
    सीधा hard-cut सबसे साफ़ और प्रोफ़ेशनल तरीका है — ठीक जैसा असली न्यूज़
    चैनल/YouTube वीडियो में होता है।

    पैरामीटर:
        background_audio_clip -> मुख्य बैकग्राउंड-संगीत/मिक्स्ड ऑडियो क्लिप
        duck_start_time        -> किस सेकंड से आवाज़ धीमी होनी शुरू होगी (= climax_start_time)
        total_duration          -> पूरे वीडियो की कुल लंबाई
        duck_volume             -> CTA के दौरान कितना वॉल्यूम रहेगा (0.5 = 50%)

    अगर background_audio_clip=None हो, या duck_start_time अमान्य हो, तो
    यह फंक्शन क्रैश नहीं करता — जो भी मिला वही सुरक्षित रूप से लौटा देता है।
    """
    if background_audio_clip is None:
        return None
    if duck_start_time <= 0 or duck_start_time >= background_audio_clip.duration:
        return background_audio_clip

    try:
        main_part = background_audio_clip.subclipped(0, duck_start_time).with_volume_scaled(1.0)
        end_part = background_audio_clip.subclipped(
            duck_start_time, min(background_audio_clip.duration, total_duration)
        ).with_volume_scaled(duck_volume)
        return concatenate_audioclips([main_part, end_part])
    except Exception as duck_error:
        print(f"⚠️ [ऑटो-स्किप] CTA-ducking नहीं हो सकी, बैकग्राउंड-संगीत सामान्य वॉल्यूम पर रहेगा: {duck_error}")
        return background_audio_clip


# --------------------------------------------------------------
# 🆕 चरण ७ (अपडेटेड) — इसे अपने _compile_standard_mode() के अंदर
# पुरानी "climax_layers = create_climax_layer(...)" लाइन की जगह डालें
# --------------------------------------------------------------
"""
पुराना कोड (हटाएँ):

    climax_layers = (
        create_climax_layer(video_duration=total_video_duration, outro_text=outro_text, aspect_ratio=aspect_ratio)
        if outro_voice_active else []
    )

नया कोड (इसकी जगह डालें):
"""


def _build_climax_with_cta_voice(
    total_video_duration: float,
    outro_text: str,
    aspect_ratio: str,
    outro_voice_active: bool,
    combined_audio,   # अब तक बना मुख्य ऑडियो-मिक्स (आवाज़ + संगीत + SFX) — इसी को duck करेंगे
):
    """
    चरण ७ का पूरा नया तरीका — विज़ुअल क्लाइमेक्स-लेयर्स भी बनाता है और
    CTA-आवाज़ भी जोड़ता है, साथ ही बैकग्राउंड-ऑडियो को hard-cut ducking भी
    करता है। सब कुछ एक ही जगह से लौटता है ताकि आगे कंपोज़िट करना आसान हो।

    रिटर्न:
        (climax_visual_layers: list, final_combined_audio, total_video_duration_updated)
        -> total_video_duration_updated वही असली लंबाई है जो CTA-आवाज़ के
           हिसाब से बढ़ी/बरकरार रही — आगे CompositeVideoClip में इसी का
           इस्तेमाल करें, ताकि लंबी CTA-आवाज़ कभी वीडियो के अंत में कटे नहीं।
    """
    if not outro_voice_active:
        return [], combined_audio, total_video_duration

    # --- चरण A: असली बोली गई CTA-आवाज़ बनाना और उसकी असली लंबाई नापना ---
    cta_audio_clip, cta_audio_duration = _build_cta_voice_audio(outro_text)

    # --- चरण B: climax_duration तय करना — डिफ़ॉल्ट 5.5s, या CTA-आवाज़ जितनी लंबी हो उतना ---
    from climax import CLIMAX_DURATION_SECONDS
    required_climax_duration = max(CLIMAX_DURATION_SECONDS, cta_audio_duration + 0.4)

    # --- चरण C: अगर CTA-आवाज़ की वजह से climax_duration बढ़ी हो, तो पूरे वीडियो
    # की लंबाई भी उतनी ही बढ़ा देना, ताकि आवाज़/विज़ुअल कभी बीच में न कटें ---
    total_video_duration_updated = max(total_video_duration, required_climax_duration + 1.0)

    # --- चरण D: विज़ुअल क्लाइमेक्स-लेयर्स (पंख + पार्टिकल-ब्लास्ट + टेक्स्ट) बनाना ---
    climax_visual_layers, climax_duration_used = create_climax_layer(
        video_duration=total_video_duration_updated,
        outro_text=outro_text,
        aspect_ratio=aspect_ratio,
        climax_duration_override=required_climax_duration,
    )
    climax_start_time = total_video_duration_updated - climax_duration_used

    # --- चरण E: बैकग्राउंड-ऑडियो को hard-cut तरीके से CTA के दौरान धीमा करना ---
    final_combined_audio = _duck_audio_hard_cut(
        combined_audio, climax_start_time, total_video_duration_updated, duck_volume=0.5,
    )

    # --- चरण F: असली CTA-आवाज़ को सही समय पर मिक्स में जोड़ना ---
    if cta_audio_clip is not None:
        cta_audio_clip = cta_audio_clip.with_start(climax_start_time)
        if final_combined_audio is not None:
            from moviepy import CompositeAudioClip
            final_combined_audio = CompositeAudioClip(
                [final_combined_audio, cta_audio_clip]
            ).with_duration(total_video_duration_updated)
        else:
            final_combined_audio = cta_audio_clip

    return climax_visual_layers, final_combined_audio, total_video_duration_updated
