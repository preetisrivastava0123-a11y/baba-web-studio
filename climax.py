"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो — climax.py (प्रोसीजरल पार्टिकल-ब्लास्ट संस्करण)
==============================================================
🆕 इस बार क्या बदला (cloud_media_director_studio.py के particle_burst_clip()
से सीखा गया तरीका):

पुराना तरीका (हटाया गया): पार्टिकल-ब्लास्ट के लिए 6 अलग PNG फ़ाइलें
(फूल/गुब्बारे/आइकन) ज़रूरी थीं — अगर वे प्रोजेक्ट में मौजूद नहीं होतीं
(ज़्यादातर मामलों में नहीं होंगी), तो ब्लास्ट पूरी तरह चुपचाप स्किप हो
जाता था। यूज़र को कभी पार्टिकल-इफ़ेक्ट दिखता ही नहीं था।

नया तरीका (procedural, कोई asset-फ़ाइल ज़रूरी नहीं): हर पार्टिकल सीधे कोड
से एक रंगीन गोल बिंदु (PIL ImageDraw.ellipse) के रूप में बनाया जाता है —
random रंग, random गति, random कोण। एक अलग "mask" फ्रेम-जनरेटर पारदर्शिता
(fade-out) संभालता है। इस तरह पार्टिकल-ब्लास्ट **हमेशा** दिखेगा, चाहे
प्रोजेक्ट में कोई भी असेट-फ़ाइल हो या न हो।

बाकी सब कुछ (मयूर पंख, सब्सक्राइब-मैसेज, आउट्रो-टेक्स्ट, MoviePy 2.x
सिंटैक्स, aspect-ratio-अवेयर लेआउट, ऑटो-स्किप-गार्ड) बिल्कुल पहले जैसा
बरकरार है — सिर्फ़ पार्टिकल-सिस्टम बदला है।
==============================================================
"""

import math
import os
import random
import tempfile

import numpy as np
from PIL import Image, ImageDraw
from moviepy import ImageClip, VideoClip

from subtitle import render_subtitle_html_to_png


# --------------------------------------------------------------
# सेटिंग्स (Constants)
# --------------------------------------------------------------
PEACOCK_FEATHER_IMAGE = "peacock_feather.png"
CLIMAX_DURATION_SECONDS = 5.5   # डिफ़ॉल्ट — अगर CTA आवाज़ इससे लंबी हो तो engine.py इसे बढ़ा सकता है

WAVE_FREQUENCY = 4.5
WAVE_AMPLITUDE_PX = 15

SUBSCRIBE_MESSAGE = "Channel ko like, subscribe karein"
GOLD_COLOR = "#FFD700"
WHITE_COLOR = "#FFFFFF"

# --- 🎈 प्रोसीजरल पार्टिकल-ब्लास्ट सेटिंग्स (अब कोई PNG फ़ाइल ज़रूरी नहीं) ---
PARTICLE_COUNT = 90                 # कुल कितने कण उड़ेंगे
PARTICLE_MIN_SPEED_PX = 220         # हर पार्टिकल की गति की रेंज (px/sec)
PARTICLE_MAX_SPEED_PX = 620
PARTICLE_MIN_SIZE_PX = 4
PARTICLE_MAX_SIZE_PX = 10
PARTICLE_COLOR_CHOICES = [
    (255, 215, 0),    # सुनहरा
    (255, 255, 255),  # सफ़ेद
    (0, 255, 204),    # नीयन-फ़िरोज़ी (like/subscribe जैसा पॉप रंग)
    (255, 105, 180),  # गुलाबी
]

FORMAT_LAYOUT_SETTINGS = {
    "9:16": {"canvas_width": 1080, "canvas_height": 1920, "font_scale": 1.0},
    "16:9": {"canvas_width": 1920, "canvas_height": 1080, "font_scale": 1.35},
}
DEFAULT_ASPECT_RATIO = "9:16"

TEMP_PNG_DIR = os.path.join(tempfile.gettempdir(), "baba_climax_pngs")


def _resolve_layout_settings(aspect_ratio: str):
    return FORMAT_LAYOUT_SETTINGS.get(aspect_ratio, FORMAT_LAYOUT_SETTINGS[DEFAULT_ASPECT_RATIO])


# --------------------------------------------------------------
# 🔐 ऑटो-स्किप गार्ड #1 — पंख (या कोई भी इमेज-फ़ाइल) सुरक्षित ढंग से लोड करना
# --------------------------------------------------------------
def _safe_load_image_clip(path: str, climax_start_time: float, climax_duration: float):
    if not path:
        return None
    try:
        if not os.path.exists(path):
            print(f"⚠️ [ऑटो-स्किप] '{path}' सर्वर पर नहीं मिली — यह लेयर छोड़ी जा रही है।")
            return None
        return ImageClip(path).with_start(climax_start_time).with_duration(climax_duration)
    except Exception as error:
        print(f"⚠️ [ऑटो-स्किप] '{path}' लोड नहीं हो सकी: {error}")
        return None


# --------------------------------------------------------------
# 🔐 ऑटो-स्किप गार्ड #2 — टेक्स्ट को PNG में बदलकर सुरक्षित ImageClip बनाना
# --------------------------------------------------------------
def _text_to_image_clip(text, output_filename, font_size, color, climax_start_time, climax_duration, canvas_width):
    if not text or not text.strip():
        return None
    try:
        os.makedirs(TEMP_PNG_DIR, exist_ok=True)
        output_path = os.path.join(TEMP_PNG_DIR, output_filename)
        rendered_png_path = render_subtitle_html_to_png(
            text_string=text, output_image_path=output_path,
            font_size=font_size, text_color=color, canvas_width=canvas_width,
        )
        return ImageClip(rendered_png_path).with_start(climax_start_time).with_duration(climax_duration)
    except Exception as error:
        print(f"⚠️ [ऑटो-स्किप] टेक्स्ट-लेयर '{output_filename}' नहीं बन सकी: {error}")
        return None


# --------------------------------------------------------------
# 1) लहराता हुआ मयूर पंख
# --------------------------------------------------------------
def _build_feather_clip(climax_start_time, climax_duration, canvas_width):
    feather_clip = _safe_load_image_clip(PEACOCK_FEATHER_IMAGE, climax_start_time, climax_duration)
    if feather_clip is None:
        return None, 0

    feather_height = feather_clip.size[1]

    def wave_position(t):
        horizontal_offset = math.sin(t * WAVE_FREQUENCY) * WAVE_AMPLITUDE_PX
        return [0.5 + (horizontal_offset / canvas_width), 0.5]

    feather_clip = feather_clip.with_position(wave_position, relative=True)
    return feather_clip, feather_height


# --------------------------------------------------------------
# 1.1) 🎈 प्रोसीजरल पार्टिकल-ब्लास्ट — cloud_media_director_studio.py से पोर्ट किया गया तरीका
# --------------------------------------------------------------
def _build_particle_burst_clip(climax_start_time: float, climax_duration: float, canvas_width: int, canvas_height: int):
    """
    मयूर पंख के केंद्र से फूटने वाला "like/subscribe" जैसा रंगीन कण-विस्फोट —
    कोई भी PNG फ़ाइल ज़रूरी नहीं, सब कुछ कोड से (PIL ImageDraw.ellipse) बनता है।
    हर कण का अपना random कोण/गति/रंग/साइज़ होता है, और समय के साथ बाहर की
    ओर उड़ते हुए धीरे-धीरे पारदर्शी (fade-out) होता जाता है।

    यह हमेशा दिखेगा — किसी असेट-फ़ाइल पर निर्भर नहीं, इसलिए कभी "चुपचाप
    स्किप" नहीं होगा (पुराने PNG-आधारित तरीके के उलट)।
    """
    center_x, center_y = canvas_width // 2, canvas_height // 2

    # हर पार्टिकल के लिए एक बार random गुण तय करना (पूरी क्लिप में स्थिर रहेंगे)
    particles = []
    for _ in range(PARTICLE_COUNT):
        particles.append({
            "angle": random.uniform(0, 2 * math.pi),
            "speed": random.uniform(PARTICLE_MIN_SPEED_PX, PARTICLE_MAX_SPEED_PX),
            "size": random.uniform(PARTICLE_MIN_SIZE_PX, PARTICLE_MAX_SIZE_PX),
            "color": random.choice(PARTICLE_COLOR_CHOICES),
        })

    def make_color_frame(t):
        """इस पल (t) पर सभी पार्टिकल्स की रंगीन तस्वीर (RGB) बनाना।"""
        frame_image = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        draw_context = ImageDraw.Draw(frame_image)
        travel_fraction = t / max(climax_duration, 0.001)
        fade_alpha = int(255 * max(0.0, 1.0 - travel_fraction))
        for particle in particles:
            radius_traveled = particle["speed"] * travel_fraction
            particle_x = center_x + math.cos(particle["angle"]) * radius_traveled
            particle_y = center_y + math.sin(particle["angle"]) * radius_traveled
            half_size = particle["size"]
            draw_context.ellipse(
                [particle_x - half_size, particle_y - half_size,
                 particle_x + half_size, particle_y + half_size],
                fill=particle["color"] + (fade_alpha,),
            )
        return np.array(frame_image.convert("RGB"))

    def make_mask_frame(t):
        """इसी पल पर पारदर्शिता-मास्क (सिर्फ़ अल्फ़ा-चैनल, 0.0-1.0) बनाना।"""
        mask_image = Image.new("L", (canvas_width, canvas_height), 0)
        draw_context = ImageDraw.Draw(mask_image)
        travel_fraction = t / max(climax_duration, 0.001)
        fade_alpha = int(255 * max(0.0, 1.0 - travel_fraction))
        for particle in particles:
            radius_traveled = particle["speed"] * travel_fraction
            particle_x = center_x + math.cos(particle["angle"]) * radius_traveled
            particle_y = center_y + math.sin(particle["angle"]) * radius_traveled
            half_size = particle["size"]
            draw_context.ellipse(
                [particle_x - half_size, particle_y - half_size,
                 particle_x + half_size, particle_y + half_size],
                fill=fade_alpha,
            )
        return np.array(mask_image).astype(float) / 255.0

    color_clip = VideoClip(make_color_frame, duration=climax_duration)
    mask_clip = VideoClip(make_mask_frame, duration=climax_duration, is_mask=True)
    particle_burst_clip = color_clip.with_mask(mask_clip).with_start(climax_start_time)

    return particle_burst_clip


# --------------------------------------------------------------
# 2) सुनहरा "Subscribe" संदेश
# --------------------------------------------------------------
def _build_subscribe_image_clip(climax_start_time, climax_duration, feather_height, canvas_width, canvas_height, font_scale):
    subscribe_clip = _text_to_image_clip(
        text=SUBSCRIBE_MESSAGE, output_filename="subscribe_message.png",
        font_size=int(45 * font_scale), color=GOLD_COLOR,
        climax_start_time=climax_start_time, climax_duration=climax_duration, canvas_width=canvas_width,
    )
    if subscribe_clip is None:
        return None
    vertical_gap = (feather_height / 2) + 20
    y_fraction = 0.5 + (vertical_gap / canvas_height)
    return subscribe_clip.with_position(lambda t: [0.5, y_fraction], relative=True)


# --------------------------------------------------------------
# 3) यूज़र का outro_text
# --------------------------------------------------------------
def _build_outro_note_image_clip(climax_start_time, climax_duration, feather_height, outro_text, canvas_width, canvas_height, font_scale):
    outro_note_clip = _text_to_image_clip(
        text=outro_text, output_filename="outro_note.png",
        font_size=int(35 * font_scale), color=WHITE_COLOR,
        climax_start_time=climax_start_time, climax_duration=climax_duration, canvas_width=canvas_width,
    )
    if outro_note_clip is None:
        return None
    vertical_gap = (feather_height / 2) + 90
    y_fraction = 0.5 + (vertical_gap / canvas_height)
    return outro_note_clip.with_position(lambda t: [0.5, y_fraction], relative=True)


# --------------------------------------------------------------
# 4) मुख्य फंक्शन — engine.py से बुलाया जाता है
# --------------------------------------------------------------
def create_climax_layer(
    video_duration: float,
    outro_text: str,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    climax_duration_override: float = None,
) -> tuple:
    """
    वीडियो के आख़िरी हिस्से के लिए सभी ओवरले लेयर्स तैयार करता है: लहराता
    मयूर पंख, प्रोसीजरल पार्टिकल-ब्लास्ट, सुनहरा सब्सक्राइब-मैसेज, आउट्रो-नोट।

    🆕 climax_duration_override: अगर engine.py में असली बोली गई CTA-आवाज़
    (spoken "like/subscribe" audio) डिफ़ॉल्ट 5.5 सेकंड से लंबी निकले, तो
    यहाँ वह असली ज़रूरी लंबाई पास की जा सकती है — climax विंडो अपने-आप
    उतनी बड़ी हो जाएगी ताकि आवाज़ कभी बीच में न कटे। None दिया जाए तो
    डिफ़ॉल्ट CLIMAX_DURATION_SECONDS (5.5s) इस्तेमाल होता है।

    रिटर्न:
        (climax_layers: list, climax_duration_used: float)
        -> climax_duration_used वही असली लंबाई है जो इस्तेमाल हुई; engine.py
           को यह बताना ज़रूरी है ताकि CTA-आवाज़ को सही विंडो में रखा जा सके।
    """
    climax_duration = climax_duration_override if climax_duration_override else CLIMAX_DURATION_SECONDS

    if video_duration <= climax_duration:
        raise ValueError(
            f"वीडियो ({video_duration} सेकंड) क्लाइमेक्स लेयर "
            f"({climax_duration} सेकंड) से छोटा है। पहले वीडियो लंबा करें।"
        )

    layout_settings = _resolve_layout_settings(aspect_ratio)
    canvas_width = layout_settings["canvas_width"]
    canvas_height = layout_settings["canvas_height"]
    font_scale = layout_settings["font_scale"]

    climax_start_time = video_duration - climax_duration

    feather_clip, feather_height = _build_feather_clip(climax_start_time, climax_duration, canvas_width)

    particle_burst_clip = (
        _build_particle_burst_clip(climax_start_time, climax_duration, canvas_width, canvas_height)
        if feather_clip is not None else None
    )

    subscribe_image_clip = _build_subscribe_image_clip(
        climax_start_time, climax_duration, feather_height, canvas_width, canvas_height, font_scale,
    )
    outro_note_image_clip = _build_outro_note_image_clip(
        climax_start_time, climax_duration, feather_height, outro_text, canvas_width, canvas_height, font_scale,
    )

    climax_layers = [feather_clip, particle_burst_clip, subscribe_image_clip, outro_note_image_clip]
    climax_layers = [clip for clip in climax_layers if clip is not None]

    return climax_layers, climax_duration


# --------------------------------------------------------------
# टेस्ट
# --------------------------------------------------------------
if __name__ == "__main__":
    from moviepy import ColorClip, CompositeVideoClip

    test_duration = 15
    background = ColorClip(size=(1080, 1920), color=(10, 10, 10)).with_duration(test_duration)
    layers, used_duration = create_climax_layer(
        video_duration=test_duration,
        outro_text="जय बाबा की! अगला वीडियो जल्द आएगा 🙏",
        aspect_ratio="9:16",
    )
    print(f"✅ {len(layers)} लेयर्स बनीं, climax_duration इस्तेमाल हुई: {used_duration}s")
    CompositeVideoClip([background, *layers]).write_videofile("climax_particle_test.mp4", fps=24)
