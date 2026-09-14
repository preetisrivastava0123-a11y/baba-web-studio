"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो — climax.py  (Playwright-PNG + पार्टिकल-ब्लास्ट संस्करण)
==============================================================
यह ब्लॉक "क्लाइमेक्स/आउट्रो इंजन" (Climax / Outro Engine) है।
इसका काम है वीडियो के आख़िरी 5.5 सेकंड के लिए ओवरले (overlay)
लेयर्स तैयार करना:
  1) लहराता हुआ मयूर पंख (Peacock Feather) — केंद्र में
  2) 🎈 उसी पंख के चारों ओर से फूल/गुब्बारे/लाइक-सब्सक्राइब आइकन जैसे
     छोटे-छोटे कण (particles) अलग-अलग दिशाओं में बाहर तैरते हुए — "मैजिक ब्लास्ट"
  3) "Channel ko like, subscribe karein" — सुनहरा संदेश
  4) यूज़र का दिया हुआ outro_text (कमेंट नोट)

इस वर्ज़न में नया क्या है (बिज़नेस-ग्रेड अपग्रेड):
  १. 🔐 सर्वव्यापी ऑटो-स्किप सेफ़्टी-गार्ड: अब पूरे कोड में — चाहे मयूर-पंख की
     इमेज हो, कोई भी पार्टिकल (फूल/गुब्बारा/आइकन) PNG हो, या सबटाइटल-रेंडरर से
     बनने वाला टेक्स्ट-PNG (सब्सक्राइब-मैसेज/आउट्रो-नोट) — अगर वह फ़ाइल सर्वर पर
     मौजूद नहीं है, लोड नहीं हो पाती, या यूज़र ने outro_text खाली छोड़ दिया है,
     तो कंपाइलर कभी FileNotFoundError/TypeError/OSError देकर क्रैश नहीं होगा।
     वह सिर्फ़ उस विशिष्ट लेयर को चुपचाप बाईपास (skip) कर देगा और बाकी वीडियो
     बिना रुके आगे रेंडर होता रहेगा। यह गार्ड `_safe_load_image_clip()` और
     `_text_to_image_clip()` — दोनों केंद्रीय हेल्पर्स में लागू है।
  २. 🎈 मयूर पंख जादुई पार्टिकल-ब्लास्ट (VFX Particle FX): जैसे ही मयूर पंख
     हिलना शुरू होता है, ठीक उसी वेव-पोज़िशन (X,Y) को केंद्र मानकर, फूलों/
     गुब्बारों/लाइक-सब्सक्राइब-आइकन जैसी छोटी PNG आकृतियाँ एक गणितीय
     ट्रेसिंग-लूप (रेडियल त्रिज्या-विस्तार) में अलग-अलग कोणों पर बाहर की ओर
     तैरती (float) हुई दिखाई जाती हैं — जैसे आतिशबाज़ी का एक सिनेमाई धमाका।
     हर पार्टिकल की अपनी फ़ाइल न मिलने पर नियम-१ के तहत वह चुपचाप छूट जाता है।
  ३. 🔐 पूरी फ़ाइल अब सिर्फ़ MoviePy 2.x+ सिंटैक्स पर — .set_duration()/
     .set_position() कहीं भी नहीं बचा; हर जगह .with_duration()/.with_position()
     ही इस्तेमाल होता है।
  ४. aspect_ratio-अवेयर लेआउट (पहले जैसा बरकरार): मयूर पंख/पार्टिकल्स/टेक्स्ट
     का साइज़, लहर की चौड़ाई और अब कैनवस-ऊँचाई (canvas_height) भी सही
     फॉर्मेट (9:16/16:9) के सापेक्ष तय होती है।

⚠️ मान्यताएँ (Assumptions) — असली फाइलें उपलब्ध न होने के कारण:
   - PEACOCK_FEATHER_IMAGE ("peacock_feather.png") — प्रोजेक्ट रूट में मौजूद
     मानी गई है; न मिले तो नियम-१ के तहत पूरी फेदर-लेयर (और उससे जुड़ा
     पार्टिकल-ब्लास्ट भी) अपने-आप स्किप हो जाएगा।
   - PARTICLE_IMAGE_FILENAMES — फूल/गुब्बारे/लाइक/सब्सक्राइब-आइकन की छोटी PNG
     फाइलें, जो या तो प्रोजेक्ट रूट में या "climax_assets/" सब-फ़ोल्डर में
     मानी गई हैं। ये सभी वैकल्पिक (optional) हैं — कोई भी न मिले तो सिर्फ़
     उतने कण छूट जाएँगे, बाकी सब कुछ (पंख/टेक्स्ट) सामान्य रूप से चलता रहेगा।
     फ़ाइल-नाम अपने असली एसेट्स के हिसाब से नीचे CONSTANT में बदल दीजिए।

⚠️ मास्टर डायरेक्टिव अब भी बरकरार:
   - यहाँ ImageMagick / MoviePy का TextClip बिल्कुल नहीं इस्तेमाल
     किया गया — सारा टेक्स्ट subtitle.py (Playwright) से PNG के
     रूप में बनता है, फिर सिर्फ़ ImageClip से ओवरले होता है।

यह फाइल पूरी तरह स्वतंत्र (independent) है। यह सिर्फ MoviePy
क्लिप्स की एक लिस्ट लौटाती है — असली मुख्य वीडियो के साथ जोड़ना
(CompositeVideoClip) engine.py में होता है।
==============================================================
"""

import math
import os
import tempfile

from moviepy import ImageClip

# --------------------------------------------------------------
# subtitle.py से Playwright-आधारित PNG रेंडरर इम्पोर्ट करना
# --------------------------------------------------------------
from subtitle import render_subtitle_html_to_png


# --------------------------------------------------------------
# सेटिंग्स (Constants) — ज़रूरत पड़ने पर आसानी से बदले जा सकते हैं
# --------------------------------------------------------------
PEACOCK_FEATHER_IMAGE = "peacock_feather.png"   # मयूर पंख की तस्वीर
CLIMAX_DURATION_SECONDS = 5.5                    # आख़िरी कितने सेकंड में यह लेयर दिखेगी

WAVE_FREQUENCY = 4.5     # पंख कितनी तेज़ी से लहराए (sin के अंदर)
WAVE_AMPLITUDE_PX = 15   # पंख कितने पिक्सेल बाएँ-दाएँ हिले

SUBSCRIBE_MESSAGE = "Channel ko like, subscribe karein"
GOLD_COLOR = "#FFD700"   # सुनहरा रंग (subscribe संदेश के लिए)
WHITE_COLOR = "#FFFFFF"  # सफ़ेद रंग (outro नोट के लिए)

# --- 🎈 मयूर पंख जादुई पार्टिकल-ब्लास्ट सेटिंग्स ---
# ⚠️ ये फ़ाइल-नाम अपने असली एसेट्स (फूल/गुब्बारे/लाइक/सब्सक्राइब-आइकन PNG) के
# हिसाब से बदल दीजिए। हर एक वैकल्पिक है — नियम-१ के ऑटो-स्किप गार्ड की वजह से
# कोई भी फ़ाइल न मिलने पर सिर्फ़ वही कण छूटेगा, बाकी सब सामान्य चलेगा।
PARTICLE_IMAGE_FILENAMES = [
    "particle_flower_1.png",
    "particle_flower_2.png",
    "particle_balloon_1.png",
    "particle_balloon_2.png",
    "particle_like_icon.png",
    "particle_subscribe_icon.png",
]
PARTICLE_ASSET_SEARCH_DIRS = ["", "climax_assets"]   # पहले रूट, फिर "climax_assets/" सब-फ़ोल्डर में ढूँढा जाएगा
PARTICLE_BURST_RADIUS_PX = 260        # कण केंद्र से कितनी दूर तक बाहर उड़ेंगे
PARTICLE_LAUNCH_STAGGER_SECONDS = 0.08  # हर अगला कण थोड़ी देर बाद (स्टैगर्ड) उड़ना शुरू करे — फुलझड़ी जैसा असर

# --- फॉर्मेट (aspect_ratio) के अनुसार कैनवस-साइज़ और फॉन्ट-स्केल ---
# ⚠️ फिक्स: पहले VIDEO_WIDTH_ASSUMED हमेशा 1920 मान लिया जाता था, जो
# 9:16 Shorts (जिसकी असली चौड़ाई सिर्फ़ 1080/720px होती है) के लिए
# बिल्कुल ग़लत था — इससे पंख की लहर बहुत हल्की/अगोचर (barely visible)
# दिखती और टेक्स्ट-PNG गलत चौड़ाई में बनता। अब हर फॉर्मेट की अपनी सही
# चौड़ाई/ऊँचाई और फॉन्ट-स्केल तय की गई है।
FORMAT_LAYOUT_SETTINGS = {
    "9:16": {
        "canvas_width": 1080,       # पोर्ट्रेट (Shorts) की मानक चौड़ाई
        "canvas_height": 1920,      # पोर्ट्रेट (Shorts) की मानक ऊँचाई
        "font_scale": 1.0,          # बेस फॉन्ट-साइज़ (कोई बदलाव नहीं)
    },
    "16:9": {
        "canvas_width": 1920,       # लैंडस्केप (Long Video) की मानक चौड़ाई
        "canvas_height": 1080,      # लैंडस्केप (Long Video) की मानक ऊँचाई
        "font_scale": 1.35,         # स्क्रीन ज़्यादा चौड़ी है, इसलिए टेक्स्ट थोड़ा बड़ा
    },
}
DEFAULT_ASPECT_RATIO = "9:16"   # अगर कोई अनजान वैल्यू आ जाए तो यही डिफ़ॉल्ट रहेगा

# PNG रेंडर करते समय इस्तेमाल होने वाला temporary फोल्डर
TEMP_PNG_DIR = os.path.join(tempfile.gettempdir(), "baba_climax_pngs")


# --------------------------------------------------------------
# 0.1) दिए गए aspect_ratio के लिए सही लेआउट-सेटिंग निकालना
# --------------------------------------------------------------
def _resolve_layout_settings(aspect_ratio: str):
    """
    यूज़र के चुने फॉर्मेट ("9:16" या "16:9") के अनुसार सही
    canvas_width, canvas_height और font_scale लौटाता है। अगर कोई
    अनजान वैल्यू आ जाए, तो सुरक्षित तरीके से डिफ़ॉल्ट (9:16) इस्तेमाल होता है।
    """
    return FORMAT_LAYOUT_SETTINGS.get(
        aspect_ratio, FORMAT_LAYOUT_SETTINGS[DEFAULT_ASPECT_RATIO]
    )


# --------------------------------------------------------------
# 0.2) 🔐 सर्वव्यापी ऑटो-स्किप गार्ड #1 — कोई भी इमेज-फ़ाइल (पंख/पार्टिकल) सुरक्षित ढंग से लोड करना
# --------------------------------------------------------------
def _safe_load_image_clip(filename_or_path: str, climax_start_time: float, climax_duration: float):
    """
    किसी भी PNG/इमेज फ़ाइल को MoviePy ImageClip के रूप में लोड करने की कोशिश
    करता है — पहले उसके बताए path से, न मिले तो PARTICLE_ASSET_SEARCH_DIRS की
    हर डायरेक्टरी में ढूँढकर। अगर फ़ाइल कहीं नहीं मिलती, करप्ट है, या लोड
    करते वक़्त किसी भी तरह की एरर (FileNotFoundError/OSError/TypeError/कुछ भी)
    आती है, तो यह फंक्शन क्रैश होने की बजाय चुपचाप None लौटा देता है — कॉलर
    इसे उस लेयर को स्किप करने के संकेत की तरह इस्तेमाल करता है।
    """
    if not filename_or_path:
        return None

    try:
        if os.path.isabs(filename_or_path):
            candidate_paths = [filename_or_path]
        else:
            candidate_paths = [
                os.path.join(search_dir, filename_or_path) if search_dir else filename_or_path
                for search_dir in PARTICLE_ASSET_SEARCH_DIRS
            ]

        resolved_path = next((path for path in candidate_paths if os.path.exists(path)), None)
        if resolved_path is None:
            # 🔐 नियम-१: फ़ाइल कहीं नहीं मिली — चुपचाप स्किप, कोई क्रैश नहीं
            print(f"⚠️ [ऑटो-स्किप] '{filename_or_path}' सर्वर पर नहीं मिली — यह लेयर छोड़ी जा रही है।")
            return None

        loaded_image_clip = (
            ImageClip(resolved_path)
            .with_start(climax_start_time)
            .with_duration(climax_duration)
        )
        return loaded_image_clip

    except Exception as image_load_error:
        # 🔐 नियम-१: FileNotFoundError/OSError/TypeError — कुछ भी हो, क्रैश नहीं
        print(f"⚠️ [ऑटो-स्किप] '{filename_or_path}' लोड नहीं हो सकी — यह लेयर छोड़ी जा रही है: {image_load_error}")
        return None


# --------------------------------------------------------------
# 0.3) 🔐 सर्वव्यापी ऑटो-स्किप गार्ड #2 — टेक्स्ट को PNG में बदलकर सुरक्षित ढंग से ImageClip बनाना
# --------------------------------------------------------------
def _text_to_image_clip(
    text: str,
    output_filename: str,
    font_size: int,
    color: str,
    climax_start_time: float,
    climax_duration: float,
    canvas_width: int,
):
    """
    TextClip का विकल्प (replacement):
      1) subtitle.py के render_subtitle_html_to_png() से पारदर्शी PNG
         बनवाना (हिंदी मात्राएँ सही रेंडर हों, ImageMagick की ज़रूरत न पड़े)
      2) उस PNG को MoviePy ImageClip से लोड करके ओवरले-लायक बनाना

    🔐 नियम-१ (ऑटो-स्किप): अगर text खाली/None हो, या PNG-रेंडरिंग/लोडिंग के
    दौरान कोई भी एरर आ जाए (Playwright क्रैश, डिस्क-राइट फेल, आदि), तो यह
    फंक्शन कभी एरर नहीं फेंकता — बस None लौटा देता है, ताकि पूरा वीडियो
    इस एक टेक्स्ट-लेयर के बिना भी बिना रुके आगे बन सके।

    canvas_width फॉर्मेट (9:16/16:9) के अनुसार आता है, ताकि टेक्स्ट
    कभी वीडियो-फ्रेम से बाहर न कटे और लैंडस्केप में सही चौड़ा दिखे।
    """
    if not text or not text.strip():
        # 🔐 नियम-१: खाली outro_text/मैसेज — चुपचाप स्किप, कोई एरर नहीं
        return None

    try:
        os.makedirs(TEMP_PNG_DIR, exist_ok=True)
        output_path = os.path.join(TEMP_PNG_DIR, output_filename)

        rendered_png_path = render_subtitle_html_to_png(
            text_string=text,
            output_image_path=output_path,
            font_size=font_size,
            text_color=color,
            canvas_width=canvas_width,
        )

        image_clip = (
            ImageClip(rendered_png_path)
            .with_start(climax_start_time)
            .with_duration(climax_duration)
        )
        return image_clip

    except Exception as text_render_error:
        # 🔐 नियम-१: टेक्स्ट-PNG बनाते/लोड करते वक़्त कुछ भी गड़बड़ हो — क्रैश नहीं
        print(f"⚠️ [ऑटो-स्किप] टेक्स्ट-लेयर '{output_filename}' नहीं बन सकी — यह लेयर छोड़ी जा रही है: {text_render_error}")
        return None


# --------------------------------------------------------------
# 1) लहराता हुआ मयूर पंख बनाने वाला फंक्शन
# --------------------------------------------------------------
def _build_feather_clip(climax_start_time: float, climax_duration: float, canvas_width: int):
    """
    peacock_feather.png को लोड करता है (सुरक्षित ढंग से — नियम-१) और उसे
    स्क्रीन के केंद्र में math.sin() के ज़रिए बाएँ-से-दाएँ धीरे-धीरे
    लहराता (wave) हुआ दिखाता है।

    ⚠️ लहर की चौड़ाई असली canvas_width (जो aspect_ratio से आता है) के
    सापेक्ष गणना होती है, ताकि 9:16 में भी लहर उतनी ही सटीक/दृश्यमान
    (visible) दिखे जितनी 16:9 में।

    रिटर्न:
        (feather_clip या None, feather_height) -> पंख की क्लिप + उसकी ऊँचाई
        (फ़ाइल न मिले तो feather_clip=None और feather_height=0 लौटता है — नियम-१)
    """
    feather_clip = _safe_load_image_clip(PEACOCK_FEATHER_IMAGE, climax_start_time, climax_duration)
    if feather_clip is None:
        # 🔐 नियम-१: पंख की फ़ाइल न मिले तो पूरी फेदर-लेयर (और उससे जुड़ा
        # पार्टिकल-ब्लास्ट) बिना क्रैश हुए स्किप — बाकी क्लाइमेक्स (टेक्स्ट) फिर भी चलेगा
        return None, 0

    feather_width, feather_height = feather_clip.size

    def wave_position(t):
        """
        t = इस क्लिप के अपने समय के अनुसार (0 से climax_duration तक)।
        सापेक्ष (0 से 1 के बीच) पोज़िशन लौटाई जाती है, ताकि यह
        किसी भी कैनवस-साइज़ (9:16 या 16:9) पर सही ढंग से स्केल हो।
        """
        horizontal_wave_offset = math.sin(t * WAVE_FREQUENCY) * WAVE_AMPLITUDE_PX

        # केंद्र (0.5) में लहर का ऑफसेट, अब सही canvas_width के सापेक्ष
        x_fraction = 0.5 + (horizontal_wave_offset / canvas_width)
        y_fraction = 0.5   # ऊँचाई हमेशा केंद्र में स्थिर रहेगी

        # ⚠️ फिक्स: MoviePy 2.x+ में .with_position() को टुपल (x, y) नहीं,
        # बल्कि लिस्ट [x, y] चाहिए — वरना "int() argument must be...
        # not 'tuple'" वाला एरर आता है। इसलिए यहाँ स्क्वायर-ब्रैकेट।
        return [x_fraction, y_fraction]

    feather_clip = feather_clip.with_position(wave_position, relative=True)

    return feather_clip, feather_height


# --------------------------------------------------------------
# 1.1) 🎈 मयूर पंख जादुई पार्टिकल-ब्लास्ट — फूल/गुब्बारे/लाइक-सब्सक्राइब आइकन
# --------------------------------------------------------------
def _build_particle_burst_clips(climax_start_time: float, climax_duration: float, canvas_width: int, canvas_height: int):
    """
    मयूर पंख के हिलने के साथ ही, उसी के केंद्र-बिंदु (X,Y) से फूल/गुब्बारे/
    लाइक/सब्सक्राइब जैसे छोटे-छोटे कण (particles) एक गणितीय ट्रेसिंग-लूप
    (रेडियल त्रिज्या-विस्तार) में अलग-अलग कोणों पर बाहर की ओर तैरते हुए
    दिखाए जाते हैं — जैसे एक सिनेमाई "मैजिक ब्लास्ट"।

    हर कण को 360° के गोल-घेरे में बराबर-बराबर कोण पर बाँटा जाता है (जितने
    ज़्यादा कण, उतनी ही घनी फुलझड़ी), और हर अगला कण थोड़ी देर बाद (स्टैगर्ड)
    उड़ना शुरू करता है ताकि एक जीवंत, क्रमिक धमाके जैसा एहसास बने।

    🔐 नियम-१: कोई भी पार्टिकल-फ़ाइल न मिले तो सिर्फ़ वह कण छूटता है, बाकी
    कण/पंख/टेक्स्ट सामान्य रूप से बनते रहते हैं।
    """
    particle_clips = []
    total_particles = len(PARTICLE_IMAGE_FILENAMES)
    if total_particles == 0:
        return particle_clips

    for particle_index, particle_filename in enumerate(PARTICLE_IMAGE_FILENAMES):
        particle_image_clip = _safe_load_image_clip(particle_filename, climax_start_time, climax_duration)
        if particle_image_clip is None:
            continue   # 🔐 नियम-१: यह कण न मिला — चुपचाप छोड़कर अगले कण पर बढ़ना

        # गोल-घेरे में बराबर-बराबर कोण पर हर कण की अपनी उड़ान-दिशा तय करना
        launch_angle_radians = (2 * math.pi / total_particles) * particle_index
        launch_delay_seconds = particle_index * PARTICLE_LAUNCH_STAGGER_SECONDS

        def _particle_position(t, angle=launch_angle_radians, delay=launch_delay_seconds):
            """
            t=0 पर कण ठीक पंख के केंद्र में (कोई ऑफसेट नहीं) शुरू होता है,
            फिर launch_delay के बाद धीरे-धीरे बाहर की ओर त्रिज्या बढ़ाते
            हुए तैरता है, जब तक PARTICLE_BURST_RADIUS_PX तक न पहुँच जाए।
            """
            travel_time = max(t - delay, 0.0)
            travel_window = max(climax_duration - delay, 0.001)
            travel_progress = min(travel_time / travel_window, 1.0)
            current_radius_px = PARTICLE_BURST_RADIUS_PX * travel_progress

            offset_x_px = math.cos(angle) * current_radius_px
            offset_y_px = math.sin(angle) * current_radius_px

            x_fraction = 0.5 + (offset_x_px / canvas_width)
            y_fraction = 0.5 + (offset_y_px / canvas_height)
            # ⚠️ फिक्स: MoviePy 2.x+ के .with_position() को टुपल नहीं, लिस्ट [x, y] चाहिए
            return [x_fraction, y_fraction]

        particle_image_clip = particle_image_clip.with_position(_particle_position, relative=True)
        particle_clips.append(particle_image_clip)

    return particle_clips


# --------------------------------------------------------------
# 2) सुनहरा "Subscribe" संदेश बनाने वाला फंक्शन (PNG के ज़रिए)
# --------------------------------------------------------------
def _build_subscribe_image_clip(
    climax_start_time: float,
    climax_duration: float,
    feather_height: int,
    canvas_width: int,
    canvas_height: int,
    font_scale: float,
):
    """
    मयूर पंख के ठीक नीचे एक सुनहरे रंग का स्थिर संदेश दिखाता है:
    "Channel ko like, subscribe karein"

    font_scale के ज़रिए 16:9 (Long Video) में टेक्स्ट थोड़ा बड़ा
    और 9:16 (Shorts) में सामान्य साइज़ में रेंडर होता है।
    """
    subscribe_clip = _text_to_image_clip(
        text=SUBSCRIBE_MESSAGE,
        output_filename="subscribe_message.png",
        font_size=int(45 * font_scale),
        color=GOLD_COLOR,
        climax_start_time=climax_start_time,
        climax_duration=climax_duration,
        canvas_width=canvas_width,
    )

    if subscribe_clip is None:
        return None

    vertical_gap_below_feather = (feather_height / 2) + 20
    y_fraction = 0.5 + (vertical_gap_below_feather / canvas_height)
    subscribe_clip = subscribe_clip.with_position(lambda t: [0.5, y_fraction], relative=True)

    return subscribe_clip


# --------------------------------------------------------------
# 3) यूज़र का outro_text बनाने वाला फंक्शन (PNG के ज़रिए)
# --------------------------------------------------------------
def _build_outro_note_image_clip(
    climax_start_time: float,
    climax_duration: float,
    feather_height: int,
    outro_text: str,
    canvas_width: int,
    canvas_height: int,
    font_scale: float,
):
    """
    सब्सक्राइब मैसेज के नीचे यूज़र का दिया हुआ कमेंट/नोट (outro_text)
    दिखाता है — PNG-आधारित ImageClip, TextClip नहीं। canvas_width और
    font_scale से यह भी फॉर्मेट के अनुसार सही ढंग से फिट होता है।
    outro_text खाली हो तो नियम-१ के तहत यह लेयर अपने-आप छूट जाती है।
    """
    outro_note_clip = _text_to_image_clip(
        text=outro_text,
        output_filename="outro_note.png",
        font_size=int(35 * font_scale),
        color=WHITE_COLOR,
        climax_start_time=climax_start_time,
        climax_duration=climax_duration,
        canvas_width=canvas_width,
    )

    if outro_note_clip is None:
        return None

    vertical_gap_below_subscribe = (feather_height / 2) + 90
    y_fraction = 0.5 + (vertical_gap_below_subscribe / canvas_height)
    outro_note_clip = outro_note_clip.with_position(lambda t: [0.5, y_fraction], relative=True)

    return outro_note_clip


# --------------------------------------------------------------
# 4) मुख्य फंक्शन — यही बाहर से (engine.py से) बुलाया जाएगा
# --------------------------------------------------------------
def create_climax_layer(
    video_duration: float,
    outro_text: str,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
) -> list:
    """
    वीडियो के आख़िरी 5.5 सेकंड के लिए सभी ओवरले लेयर्स तैयार करता है:
    लहराता मयूर पंख, उससे फूटता पार्टिकल-ब्लास्ट (फूल/गुब्बारे/आइकन),
    सुनहरा सब्सक्राइब-मैसेज, और यूज़र का आउट्रो-नोट।

    डायनामिक टाइमस्टैम्प (हमेशा लागू, चाहे वीडियो कितना भी लंबा हो):
        climax_start_time = video_duration - CLIMAX_DURATION_SECONDS
    यानी 40-सेकंड की Shorts हो या 1-घंटे की Long Video — मयूर पंख,
    पार्टिकल-ब्लास्ट और आउट्रो-टेक्स्ट सिर्फ़ आख़िरी 5.5 सेकंड में ही दिखेंगे।

    🔐 नियम-१ (सर्वव्यापी ऑटो-स्किप): इस पूरे फंक्शन में कोई भी लेयर — पंख,
    कोई भी पार्टिकल, सब्सक्राइब-मैसेज, या आउट्रो-नोट — बिना फ़ाइल/खाली-टेक्स्ट
    की वजह से मौजूद न हो तो कभी क्रैश नहीं होता, बस उसकी जगह उस लेयर को
    छोड़कर बाकी की लिस्ट लौटा दी जाती है (worst-case: सभी लेयर्स छूट जाएँ
    तो भी यह फंक्शन खाली लिस्ट [] लौटाएगा, एरर नहीं फेंकेगा)।

    पैरामीटर:
        video_duration (float) -> पूरे वीडियो की कुल लंबाई (सेकंड में)
        outro_text (str)       -> यूज़र का दिया हुआ कमेंट/नोट (खाली भी हो सकता है)
        aspect_ratio (str)     -> "9:16" (Shorts) या "16:9" (Long Video);
                                   इसी से पंख/पार्टिकल्स/टेक्स्ट का साइज़ व
                                   पोज़िशन सही कैनवस के अनुसार एडजस्ट होता है

    रिटर्न:
        list -> [feather_clip, *particle_clips, subscribe_image_clip, outro_note_image_clip]
                (जो भी लेयर उपलब्ध/मौजूद नहीं, वह लिस्ट में शामिल नहीं होगी)
    """

    if video_duration <= CLIMAX_DURATION_SECONDS:
        raise ValueError(
            f"वीडियो ({video_duration} सेकंड) क्लाइमेक्स लेयर "
            f"({CLIMAX_DURATION_SECONDS} सेकंड) से छोटा है। पहले वीडियो लंबा करें।"
        )

    # --- फॉर्मेट (9:16/16:9) के अनुसार सही कैनवस-साइज़ व फॉन्ट-स्केल निकालना ---
    layout_settings = _resolve_layout_settings(aspect_ratio)
    canvas_width = layout_settings["canvas_width"]
    canvas_height = layout_settings["canvas_height"]
    font_scale = layout_settings["font_scale"]

    # --- क्लाइमेक्स लेयर कब से शुरू होगी: कुल लंबाई घटा आख़िरी 5.5 सेकंड ---
    climax_start_time = video_duration - CLIMAX_DURATION_SECONDS

    # --- 1) लहराता हुआ मयूर पंख (फ़ाइल न मिले तो नियम-१ के तहत None) ---
    feather_clip, feather_height = _build_feather_clip(
        climax_start_time, CLIMAX_DURATION_SECONDS, canvas_width
    )

    # --- 1.1) 🎈 मयूर पंख से फूटता पार्टिकल-ब्लास्ट — सिर्फ़ तभी जब पंख खुद मौजूद हो
    # (क्योंकि कणों की उड़ान पंख के केंद्र-बिंदु से ही नापी जाती है) ---
    particle_burst_clips = (
        _build_particle_burst_clips(climax_start_time, CLIMAX_DURATION_SECONDS, canvas_width, canvas_height)
        if feather_clip is not None else []
    )

    # --- 2) सुनहरा "Subscribe" संदेश ---
    subscribe_image_clip = _build_subscribe_image_clip(
        climax_start_time,
        CLIMAX_DURATION_SECONDS,
        feather_height,
        canvas_width,
        canvas_height,
        font_scale,
    )

    # --- 3) यूज़र का outro_text ---
    outro_note_image_clip = _build_outro_note_image_clip(
        climax_start_time,
        CLIMAX_DURATION_SECONDS,
        feather_height,
        outro_text,
        canvas_width,
        canvas_height,
        font_scale,
    )

    # --- सभी लेयर्स की लिस्ट बनाना (खाली/None क्लिप्स को छोड़कर) ---
    # क्रम ज़रूरी है: पंख सबसे नीचे, उसके ऊपर पार्टिकल-ब्लास्ट, फिर टेक्स्ट सबसे ऊपर
    climax_layers = [feather_clip, *particle_burst_clips, subscribe_image_clip, outro_note_image_clip]
    climax_layers = [clip for clip in climax_layers if clip is not None]

    return climax_layers


# --------------------------------------------------------------
# इस फाइल को सीधे चलाकर टेस्ट करने के लिए (Optional)
# --------------------------------------------------------------
if __name__ == "__main__":
    from moviepy import ColorClip, CompositeVideoClip

    test_duration = 15

    # --- टेस्ट 1: 9:16 Shorts फॉर्मेट ---
    background_shorts = ColorClip(
        size=(1080, 1920), color=(10, 10, 10)
    ).with_duration(test_duration)
    shorts_layers = create_climax_layer(
        video_duration=test_duration,
        outro_text="जय बाबा की! अगला वीडियो जल्द आएगा 🙏",
        aspect_ratio="9:16",
    )
    CompositeVideoClip([background_shorts, *shorts_layers]).write_videofile(
        "climax_test_shorts.mp4", fps=24
    )

    # --- टेस्ट 2: 16:9 Long Video फॉर्मेट ---
    background_long = ColorClip(
        size=(1920, 1080), color=(10, 10, 10)
    ).with_duration(test_duration)
    long_layers = create_climax_layer(
        video_duration=test_duration,
        outro_text="जय बाबा की! अगला वीडियो जल्द आएगा 🙏",
        aspect_ratio="16:9",
    )
    CompositeVideoClip([background_long, *long_layers]).write_videofile(
        "climax_test_long.mp4", fps=24
    )

    # --- टेस्ट 3: 🔐 ऑटो-स्किप गार्ड की पुष्टि — कोई फ़ाइल/टेक्स्ट उपलब्ध न होने पर भी क्रैश नहीं होना चाहिए ---
    empty_outro_layers = create_climax_layer(
        video_duration=test_duration,
        outro_text="",   # जानबूझकर खाली — नियम-१ के तहत आउट्रो-नोट लेयर छूट जानी चाहिए
        aspect_ratio="9:16",
    )
    print(f"✅ ऑटो-स्किप टेस्ट पास — {len(empty_outro_layers)} लेयर्स बनीं (क्रैश नहीं हुआ)।")
