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

⚠️ मास्टर डायरेक्टिव के अनुसार:
   - यहाँ ImageMagick / MoviePy का TextClip बिल्कुल नहीं
     इस्तेमाल किया गया है, क्योंकि यह क्लाउड सर्वर्स पर crash
     हो जाता है और हिंदी की मात्राएँ (जैसे ी, ू, ौ आदि) कट जाती हैं।
   - इसके बजाय, सारा टेक्स्ट पहले `subtitle.py` (जो Playwright के
     ज़रिए HTML/CSS को पारदर्शी PNG में रेंडर करता है) से बनवाया
     जाता है, और फिर उस PNG को सिर्फ़ MoviePy के ImageClip से
     वीडियो पर ओवरले किया जाता है।

यह फाइल पूरी तरह स्वतंत्र (independent) है। यह सिर्फ MoviePy
क्लिप्स की एक लिस्ट लौटाती है — असली मुख्य वीडियो के साथ जोड़ना
(CompositeVideoClip) आगे किसी अलग "combiner" ब्लॉक में होगा।
==============================================================
"""

import math
import os
import tempfile

from moviepy import ImageClip

# --------------------------------------------------------------
# subtitle.py से Playwright-आधारित PNG रेंडरर इम्पोर्ट करना
# --------------------------------------------------------------
# मान्यता (Assumption): subtitle.py में एक function है जो
# text -> पारदर्शी PNG (transparent background) बनाकर उसका
# फाइल-पाथ (path) लौटाता है। अगर आपके subtitle.py में function
# का नाम/पैरामीटर अलग हैं, तो सिर्फ़ यही import line और उसका
# इस्तेमाल नीचे बदलें — बाकी कोड जस का तस चलेगा।
from subtitle import render_subtitle_html_to_png


# --------------------------------------------------------------
# सेटिंग्स (Constants) — ज़रूरत पड़ने पर आसानी से बदले जा सकते हैं
# --------------------------------------------------------------
PEACOCK_FEATHER_IMAGE = "peacock_feather.png"   # मयूर पंख की तस्वीर
CLIMAX_DURATION_SECONDS = 5.5                    # आख़िरी कितने सेकंड में यह लेयर दिखेगी

WAVE_FREQUENCY = 4.5     # पंख कितनी तेज़ी से लहराए (sin के अंदर)
WAVE_AMPLITUDE_PX = 15   # पंख कितने पिक्सेल बाएँ-दाएँ हिले

# ⚠️ ध्यान दें: नीचे दिया गया VIDEO_WIDTH एक मानक (standard) मान है,
# जिसका उपयोग लहर (wave) को प्रतिशत (relative) स्थिति में बदलने के
# लिए किया जाता है। अगर आपका मुख्य वीडियो 1920px चौड़ा नहीं है,
# तो जोड़ते (combine) समय इसे उस असली चौड़ाई से बदल दें।
VIDEO_WIDTH_ASSUMED = 1920

SUBSCRIBE_MESSAGE = "Channel ko like, subscribe karein"
GOLD_COLOR = "#FFD700"   # सुनहरा रंग (subscribe संदेश के लिए)
WHITE_COLOR = "#FFFFFF"  # सफ़ेद रंग (outro नोट के लिए)

# PNG रेंडर करते समय इस्तेमाल होने वाला temporary फोल्डर
# (ताकि हर बार नई अस्थायी फ़ाइलें साफ़-सुथरे ढंग से बनें)
TEMP_PNG_DIR = os.path.join(tempfile.gettempdir(), "baba_climax_pngs")


# --------------------------------------------------------------
# 0) एक छोटा सहायक (helper) फंक्शन — टेक्स्ट को PNG में बदलकर
#    सीधे MoviePy ImageClip के रूप में लौटाता है
# --------------------------------------------------------------
def _text_to_image_clip(
    text: str,
    output_filename: str,
    font_size: int,
    color: str,
    climax_start_time: float,
    climax_duration: float,
):
    """
    यह फंक्शन TextClip का विकल्प (replacement) है।

    काम करने का तरीका:
      1) subtitle.py के render_text_png() को कॉल करके पहले
         Playwright के ज़रिए टेक्स्ट का एक पारदर्शी PNG बनवाया
         जाता है (इससे हिंदी की मात्राएँ सही तरह रेंडर होती हैं
         और ImageMagick की ज़रूरत नहीं पड़ती)।
      2) फिर उस PNG को सीधे MoviePy के ImageClip से लोड करके
         वीडियो पर ओवरले करने लायक क्लिप बना दिया जाता है।

    पैरामीटर:
        text (str)               -> जो टेक्स्ट PNG में बदलना है
        output_filename (str)    -> अस्थायी PNG का नाम (जैसे "subscribe.png")
        font_size (int)          -> फॉन्ट साइज़ (subtitle.py को भेजा जाएगा)
        color (str)              -> टेक्स्ट का रंग (जैसे "#FFD700")
        climax_start_time (float)-> क्लिप वीडियो में कब से शुरू होगी
        climax_duration (float)  -> क्लिप कितनी देर चलेगी

    रिटर्न:
        ImageClip -> रेंडर की गई PNG वाली MoviePy क्लिप
    """
    # अगर टेक्स्ट खाली है, तो कुछ भी रेंडर न करें (None लौटाएँ)
    if not text or not text.strip():
        return None

    os.makedirs(TEMP_PNG_DIR, exist_ok=True)
    output_path = os.path.join(TEMP_PNG_DIR, output_filename)

    # Playwright के ज़रिए पारदर्शी PNG बनवाना
    # (font_size और color subtitle.py के अंदर HTML/CSS में इस्तेमाल होंगे)
    # ⚠️ फिक्स: पहले यहाँ "render_text_png" नाम का कभी-न-import हुआ फंक्शन
    # कॉल हो रहा था (NameError), और पैरामीटर-नाम भी असली subtitle.py से
    # मेल नहीं खाते थे। अब सही फंक्शन-नाम व सही पैरामीटर-नाम इस्तेमाल हुए हैं।
    rendered_png_path = render_subtitle_html_to_png(
        text_string=text,
        output_image_path=output_path,
        font_size=font_size,
        text_color=color,
    )

    # PNG को ImageClip के रूप में लोड करना और समय (timing) सेट करना
    image_clip = (
        ImageClip(rendered_png_path)
        .set_start(climax_start_time)
        .set_duration(climax_duration)
    )

    return image_clip


# --------------------------------------------------------------
# 1) लहराता हुआ मयूर पंख बनाने वाला फंक्शन
# --------------------------------------------------------------
def _build_feather_clip(climax_start_time: float, climax_duration: float):
    """
    peacock_feather.png को लोड करता है और उसे स्क्रीन के केंद्र में
    इस तरह सेट करता है कि हर फ्रेम पर वह math.sin() के ज़रिए
    बाएँ-से-दाएँ धीरे-धीरे लहराता (wave) हुआ दिखे।

    पैरामीटर:
        climax_start_time (float) -> यह लेयर वीडियो में कब से शुरू होगी
        climax_duration (float)   -> यह लेयर कितनी देर चलेगी (यानी 5.5 सेकंड)

    रिटर्न:
        (feather_clip, feather_height) -> पंख की क्लिप + उसकी ऊँचाई
        (ऊँचाई आगे टेक्स्ट-PNG लेयर्स को "ठीक नीचे" रखने के लिए चाहिए)
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

        math.sin(t * WAVE_FREQUENCY) * WAVE_AMPLITUDE_PX
        -> यह -15 से +15 पिक्सेल के बीच एक स्मूद, धीमी लहर (wave) बनाता है

        चूँकि हमें x को "केंद्र + लहर-ऑफसेट" के रूप में चाहिए, इसलिए
        हम relative positioning (0 से 1 के बीच का फ्रैक्शन) का
        उपयोग करते हैं — यह मुख्य वीडियो के आकार के सापेक्ष काम करता है।
        """
        horizontal_wave_offset = math.sin(t * WAVE_FREQUENCY) * WAVE_AMPLITUDE_PX

        # केंद्र (0.5) में लहर का ऑफसेट प्रतिशत के रूप में जोड़ना
        x_fraction = 0.5 + (horizontal_wave_offset / VIDEO_WIDTH_ASSUMED)
        y_fraction = 0.5   # ऊँचाई हमेशा केंद्र में स्थिर रहेगी

        return (x_fraction, y_fraction)

    # relative=True का मतलब है कि ऊपर लौटाए गए (x, y) मान
    # 0 से 1 के बीच के फ्रैक्शन के रूप में लिए जाएँगे,
    # पिक्सेल के रूप में नहीं — इसी से पंख हर फ्रेम पर स्मूद
    # ढंग से बाएँ-दाएँ लहराता (wave) है।
    feather_clip = feather_clip.set_position(wave_position, relative=True)

    return feather_clip, feather_height


# --------------------------------------------------------------
# 2) सुनहरा "Subscribe" संदेश बनाने वाला फंक्शन (अब PNG के ज़रिए)
# --------------------------------------------------------------
def _build_subscribe_image_clip(climax_start_time: float, climax_duration: float, feather_height: int):
    """
    मयूर पंख के ठीक नीचे एक सुनहरे रंग का स्थिर संदेश दिखाता है:
    "Channel ko like, subscribe karein"

    यह अब TextClip से नहीं बल्कि subtitle.py द्वारा पहले से
    रेंडर की गई PNG इमेज से बनता है, ताकि क्रैश और मात्रा-कटने
    की समस्या न आए।
    """
    subscribe_clip = _text_to_image_clip(
        text=SUBSCRIBE_MESSAGE,
        output_filename="subscribe_message.png",
        font_size=45,
        color=GOLD_COLOR,
        climax_start_time=climax_start_time,
        climax_duration=climax_duration,
    )

    if subscribe_clip is None:
        return None

    # पंख के केंद्र से थोड़ा नीचे (feather_height/2 + थोड़ा मार्जिन) रखना
    vertical_gap_below_feather = (feather_height / 2) + 20
    subscribe_clip = subscribe_clip.set_position(
        lambda t: ("center", ("center", vertical_gap_below_feather))
    )

    return subscribe_clip


# --------------------------------------------------------------
# 3) यूज़र का outro_text बनाने वाला फंक्शन (अब PNG के ज़रिए)
# --------------------------------------------------------------
def _build_outro_note_image_clip(
    climax_start_time: float,
    climax_duration: float,
    feather_height: int,
    outro_text: str,
):
    """
    सब्सक्राइब मैसेज के नीचे यूज़र का दिया हुआ कमेंट/नोट (outro_text)
    दिखाता है — यह भी अब PNG-आधारित ImageClip है, TextClip नहीं।
    """
    outro_note_clip = _text_to_image_clip(
        text=outro_text,
        output_filename="outro_note.png",
        font_size=35,
        color=WHITE_COLOR,
        climax_start_time=climax_start_time,
        climax_duration=climax_duration,
    )

    if outro_note_clip is None:
        return None

    vertical_gap_below_subscribe = (feather_height / 2) + 90
    outro_note_clip = outro_note_clip.set_position(
        lambda t: ("center", ("center", vertical_gap_below_subscribe))
    )

    return outro_note_clip


# --------------------------------------------------------------
# 4) मुख्य फंक्शन — यही बाहर से (app.py / combiner से) बुलाया जाएगा
# --------------------------------------------------------------
def create_climax_layer(video_duration: float, outro_text: str) -> list:
    """
    वीडियो के आख़िरी 5.5 सेकंड के लिए सभी ओवरले लेयर्स तैयार करता है
    और उन्हें एक लिस्ट (list) के रूप में लौटाता है, ताकि इन्हें आगे
    मुख्य वीडियो के साथ CompositeVideoClip([main_video, *these_layers])
    की तरह जोड़ा जा सके।

    पैरामीटर:
        video_duration (float) -> पूरे वीडियो की कुल लंबाई (सेकंड में)
        outro_text (str)       -> यूज़र का दिया हुआ कमेंट/नोट

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

    # --- क्लाइमेक्स लेयर कब से शुरू होगी, इसकी गणना ---
    # यानी: कुल लंबाई घटा आख़िरी 5.5 सेकंड
    climax_start_time = video_duration - CLIMAX_DURATION_SECONDS

    # --- 1) लहराता हुआ मयूर पंख (सीधे PNG से, TextClip यहाँ है ही नहीं) ---
    feather_clip, feather_height = _build_feather_clip(
        climax_start_time, CLIMAX_DURATION_SECONDS
    )

    # --- 2) सुनहरा "Subscribe" संदेश (Playwright PNG + ImageClip) ---
    subscribe_image_clip = _build_subscribe_image_clip(
        climax_start_time, CLIMAX_DURATION_SECONDS, feather_height
    )

    # --- 3) यूज़र का outro_text (Playwright PNG + ImageClip) ---
    outro_note_image_clip = _build_outro_note_image_clip(
        climax_start_time, CLIMAX_DURATION_SECONDS, feather_height, outro_text
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

    # टेस्ट के लिए एक साधारण काली बैकग्राउंड क्लिप (15 सेकंड)
    test_duration = 15
    background = ColorClip(
        size=(VIDEO_WIDTH_ASSUMED, 1080), color=(10, 10, 10)
    ).set_duration(test_duration)

    layers = create_climax_layer(
        video_duration=test_duration,
        outro_text="जय बाबा की! अगला वीडियो जल्द आएगा 🙏",
    )

    final_test_video = CompositeVideoClip([background, *layers])
    final_test_video.write_videofile("climax_test_output.mp4", fps=24)
