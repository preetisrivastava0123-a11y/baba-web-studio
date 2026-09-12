"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो — climax.py  (Playwright-PNG संस्करण)
==============================================================
यह ब्लॉक "क्लाइमेक्स/आउट्रो इंजन" (Climax / Outro Engine) है।
इसका काम है वीडियो के आख़िरी 5.5 सेकंड के लिए तीन ओवरले
(overlay) लेयर्स तैयार करना:
  1) लहराता हुआ मयूर पंख (Peacock Feather) — केंद्र में
  2) "Channel ko like, subscribe karein" — सुनहरा संदेश
  3) यूज़र का दिया हुआ outro_text (कमेंट नोट)

इस वर्ज़न में नया क्या है:
  १. डायनामिक टाइमस्टैम्प: क्लाइमेक्स हमेशा ठीक video_duration - 5.5
     पर शुरू होता है — चाहे वीडियो 40 सेकंड का हो या 1 घंटे का।
     (यह लॉजिक पहले से सही था, अब सिर्फ़ और पक्का/डॉक्यूमेंटेड किया गया है)
  २. aspect_ratio-अवेयर लेआउट: अब create_climax_layer() एक नया
     पैरामीटर aspect_ratio ("9:16" या "16:9") लेता है, जिससे:
       - मयूर पंख का साइज़ और लहर (wave) की चौड़ाई सही कैनवस-चौड़ाई
         के सापेक्ष तय होती है (पहले हमेशा 1920px मान लिया जाता था,
         जो 9:16 पर ग़लत था)।
       - सब्सक्राइब-मैसेज और आउट्रो-टेक्स्ट PNG की चौड़ाई (canvas_width)
         फॉर्मेट के अनुसार सेट होती है, ताकि 16:9 लैंडस्केप में टेक्स्ट
         बड़ा/चौड़ा रहे और 9:16 पोर्ट्रेट में स्क्रीन से बाहर न छलके।
       - फॉन्ट-साइज़ भी हल्का-सा फॉर्मेट के अनुसार स्केल होता है
         (16:9 में स्क्रीन ज़्यादा चौड़ी लेकिन कम ऊँची होती है, इसलिए
         टेक्स्ट को हल्का बड़ा रखा गया है ताकि दूर से भी पढ़ा जा सके)।

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

# --- फॉर्मेट (aspect_ratio) के अनुसार कैनवस-चौड़ाई और फॉन्ट-स्केल ---
# ⚠️ फिक्स: पहले VIDEO_WIDTH_ASSUMED हमेशा 1920 मान लिया जाता था, जो
# 9:16 Shorts (जिसकी असली चौड़ाई सिर्फ़ 1080/720px होती है) के लिए
# बिल्कुल ग़लत था — इससे पंख की लहर बहुत हल्की/अगोचर (barely visible)
# दिखती और टेक्स्ट-PNG गलत चौड़ाई में बनता। अब हर फॉर्मेट की अपनी सही
# चौड़ाई और फॉन्ट-स्केल तय की गई है।
FORMAT_LAYOUT_SETTINGS = {
    "9:16": {
        "canvas_width": 1080,       # पोर्ट्रेट (Shorts) की मानक चौड़ाई
        "font_scale": 1.0,          # बेस फॉन्ट-साइज़ (कोई बदलाव नहीं)
    },
    "16:9": {
        "canvas_width": 1920,       # लैंडस्केप (Long Video) की मानक चौड़ाई
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
    canvas_width और font_scale लौटाता है। अगर कोई अनजान वैल्यू
    आ जाए, तो सुरक्षित तरीके से डिफ़ॉल्ट (9:16) इस्तेमाल होता है।
    """
    return FORMAT_LAYOUT_SETTINGS.get(
        aspect_ratio, FORMAT_LAYOUT_SETTINGS[DEFAULT_ASPECT_RATIO]
    )


# --------------------------------------------------------------
# 0.2) एक छोटा सहायक (helper) फंक्शन — टेक्स्ट को PNG में बदलकर
#      सीधे MoviePy ImageClip के रूप में लौटाता है
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

    canvas_width अब फॉर्मेट (9:16/16:9) के अनुसार आता है, ताकि टेक्स्ट
    कभी वीडियो-फ्रेम से बाहर न कटे और लैंडस्केप में सही चौड़ा दिखे।
    """
    if not text or not text.strip():
        return None

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
        .set_start(climax_start_time)
        .set_duration(climax_duration)
    )

    return image_clip


# --------------------------------------------------------------
# 1) लहराता हुआ मयूर पंख बनाने वाला फंक्शन
# --------------------------------------------------------------
def _build_feather_clip(climax_start_time: float, climax_duration: float, canvas_width: int):
    """
    peacock_feather.png को लोड करता है और उसे स्क्रीन के केंद्र में
    math.sin() के ज़रिए बाएँ-से-दाएँ धीरे-धीरे लहराता (wave) हुआ दिखाता है।

    ⚠️ फिक्स: लहर की चौड़ाई अब हार्डकोड 1920px की जगह असली canvas_width
    (जो aspect_ratio से आता है) के सापेक्ष गणना होती है, ताकि 9:16 में
    भी लहर उतनी ही सटीक/दृश्यमान (visible) दिखे जितनी 16:9 में।

    रिटर्न:
        (feather_clip, feather_height) -> पंख की क्लिप + उसकी ऊँचाई
    """
    feather_clip = (
        ImageClip(PEACOCK_FEATHER_IMAGE)
        .set_start(climax_start_time)
        .set_duration(climax_duration)
    )

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

        return (x_fraction, y_fraction)

    feather_clip = feather_clip.set_position(wave_position, relative=True)

    return feather_clip, feather_height


# --------------------------------------------------------------
# 2) सुनहरा "Subscribe" संदेश बनाने वाला फंक्शन (PNG के ज़रिए)
# --------------------------------------------------------------
def _build_subscribe_image_clip(
    climax_start_time: float,
    climax_duration: float,
    feather_height: int,
    canvas_width: int,
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

    # पंख के केंद्र से थोड़ा नीचे (feather_height/2 + थोड़ा मार्जिन) रखना
    # — यह मार्जिन दोनों फॉर्मेट में सेंटर-पोज़िशनिंग की वजह से अपने-आप
    # सही जगह बैठता है, चाहे कैनवस पोर्ट्रेट हो या लैंडस्केप।
    vertical_gap_below_feather = (feather_height / 2) + 20
    subscribe_clip = subscribe_clip.set_position(
        lambda t: ("center", ("center", vertical_gap_below_feather))
    )

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
    font_scale: float,
):
    """
    सब्सक्राइब मैसेज के नीचे यूज़र का दिया हुआ कमेंट/नोट (outro_text)
    दिखाता है — PNG-आधारित ImageClip, TextClip नहीं। canvas_width और
    font_scale से यह भी फॉर्मेट के अनुसार सही ढंग से फिट होता है।
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
    outro_note_clip = outro_note_clip.set_position(
        lambda t: ("center", ("center", vertical_gap_below_subscribe))
    )

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
    वीडियो के आख़िरी 5.5 सेकंड के लिए सभी ओवरले लेयर्स तैयार करता है।

    डायनामिक टाइमस्टैम्प (हमेशा लागू, चाहे वीडियो कितना भी लंबा हो):
        climax_start_time = video_duration - CLIMAX_DURATION_SECONDS
    यानी 40-सेकंड की Shorts हो या 1-घंटे की Long Video — मयूर पंख और
    आउट्रो-टेक्स्ट सिर्फ़ आख़िरी 5.5 सेकंड में ही दिखेंगे।

    पैरामीटर:
        video_duration (float) -> पूरे वीडियो की कुल लंबाई (सेकंड में)
        outro_text (str)       -> यूज़र का दिया हुआ कमेंट/नोट
        aspect_ratio (str)     -> "9:16" (Shorts) या "16:9" (Long Video);
                                   इसी से पंख/टेक्स्ट का साइज़ व पोज़िशन
                                   सही कैनवस के अनुसार एडजस्ट होता है

    रिटर्न:
        list -> [feather_clip, subscribe_image_clip, outro_note_image_clip]
                (अगर कोई टेक्स्ट खाली हो, तो उसकी क्लिप लिस्ट में
                शामिल नहीं की जाएगी)
    """

    if video_duration <= CLIMAX_DURATION_SECONDS:
        raise ValueError(
            f"वीडियो ({video_duration} सेकंड) क्लाइमेक्स लेयर "
            f"({CLIMAX_DURATION_SECONDS} सेकंड) से छोटा है। पहले वीडियो लंबा करें।"
        )

    # --- फॉर्मेट (9:16/16:9) के अनुसार सही कैनवस-चौड़ाई व फॉन्ट-स्केल निकालना ---
    layout_settings = _resolve_layout_settings(aspect_ratio)
    canvas_width = layout_settings["canvas_width"]
    font_scale = layout_settings["font_scale"]

    # --- क्लाइमेक्स लेयर कब से शुरू होगी: कुल लंबाई घटा आख़िरी 5.5 सेकंड ---
    climax_start_time = video_duration - CLIMAX_DURATION_SECONDS

    # --- 1) लहराता हुआ मयूर पंख (फॉर्मेट-अनुसार सही चौड़ाई पर आधारित लहर) ---
    feather_clip, feather_height = _build_feather_clip(
        climax_start_time, CLIMAX_DURATION_SECONDS, canvas_width
    )

    # --- 2) सुनहरा "Subscribe" संदेश ---
    subscribe_image_clip = _build_subscribe_image_clip(
        climax_start_time,
        CLIMAX_DURATION_SECONDS,
        feather_height,
        canvas_width,
        font_scale,
    )

    # --- 3) यूज़र का outro_text ---
    outro_note_image_clip = _build_outro_note_image_clip(
        climax_start_time,
        CLIMAX_DURATION_SECONDS,
        feather_height,
        outro_text,
        canvas_width,
        font_scale,
    )

    # --- सभी लेयर्स की लिस्ट बनाना (खाली/None क्लिप्स को छोड़कर) ---
    climax_layers = [feather_clip, subscribe_image_clip, outro_note_image_clip]
    climax_layers = [clip for clip in climax_layers if clip is not None]

    return climax_layers


# --------------------------------------------------------------
# इस फाइल को सीधे चलाकर टेस्ट करने के लिए (Optional)
# --------------------------------------------------------------
if __name__ == "__main__":
    from moviepy.editor import ColorClip, CompositeVideoClip

    test_duration = 15

    # --- टेस्ट 1: 9:16 Shorts फॉर्मेट ---
    background_shorts = ColorClip(
        size=(1080, 1920), color=(10, 10, 10)
    ).set_duration(test_duration)
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
    ).set_duration(test_duration)
    long_layers = create_climax_layer(
        video_duration=test_duration,
        outro_text="जय बाबा की! अगला वीडियो जल्द आएगा 🙏",
        aspect_ratio="16:9",
    )
    CompositeVideoClip([background_long, *long_layers]).write_videofile(
        "climax_test_long.mp4", fps=24
    )
