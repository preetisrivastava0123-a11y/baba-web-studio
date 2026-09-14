"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो — climax.py (शुद्ध हिंदी + पार्टिकल 3D आउट्रो)
==============================================================
[मॉड्यूल का काम]:
- मयूर पंख न होने पर भी स्वतंत्र पार्टिकल-ब्लास्ट एनीमेशन रेंडर करना।
- 'चैनल को लाइक और सब्सक्राइब करें 🔔' का शुद्ध देवनागरी हिंदी कार्ड बनाना।
- edge-tts के माध्यम से आख़िरी 10/5.5 सेकंड के लिए AI हिंदी वॉइसओवर ऑडियो तैयार करना।
==============================================================
"""

import math
import os
import random
import tempfile
import asyncio

import numpy as np
from PIL import Image, ImageDraw
from moviepy import ImageClip, VideoClip, AudioFileClip

from subtitle import render_subtitle_html_to_png


# --------------------------------------------------------------
# ⚙️ 1. सेटिंग्स और कांस्टेंट्स (Constants)
# --------------------------------------------------------------
PEACOCK_FEATHER_IMAGE = "peacock_feather.png"
CLIMAX_DURATION_SECONDS = 5.5  # डिफ़ॉल्ट आउट्रो समय (सेकंड में)

WAVE_FREQUENCY = 4.5
WAVE_AMPLITUDE_PX = 15

# शुद्ध देवनागरी हिंदी सब्सक्राइब संदेश
SUBSCRIBE_MESSAGE = "चैनल को लाइक और सब्सक्राइब करें 🔔"
GOLD_COLOR = "#FFD700"
WHITE_COLOR = "#FFFFFF"

# 🎈 प्रोसीजरल पार्टिकल-ब्लास्ट सेटिंग्स (बिना किसी बाहरी इमेज फ़ाइल के)
PARTICLE_COUNT = 90
PARTICLE_MIN_SPEED_PX = 220
PARTICLE_MAX_SPEED_PX = 620
PARTICLE_MIN_SIZE_PX = 4
PARTICLE_MAX_SIZE_PX = 10
PARTICLE_COLOR_CHOICES = [
    (255, 215, 0),    # सुनहरा
    (255, 255, 255),  # सफ़ेद
    (0, 255, 204),    # नीयन-फ़िरोज़ी
    (255, 105, 180),  # गुलाबी
]

FORMAT_LAYOUT_SETTINGS = {
    "9:16": {"canvas_width": 1080, "canvas_height": 1920, "font_scale": 1.0},
    "16:9": {"canvas_width": 1920, "canvas_height": 1080, "font_scale": 1.35},
}
DEFAULT_ASPECT_RATIO = "9:16"

TEMP_PNG_DIR = os.path.join(tempfile.gettempdir(), "baba_climax_pngs")


def _resolve_layout_settings(aspect_ratio: str):
    """[काम]: एस्पेक्ट रेशियो (9:16 या 16:9) के हिसाब से चौड़ाई और फ़ॉन्ट स्केल तय करना"""
    return FORMAT_LAYOUT_SETTINGS.get(aspect_ratio, FORMAT_LAYOUT_SETTINGS[DEFAULT_ASPECT_RATIO])


# --------------------------------------------------------------
# 🔐 2. ऑटो-स्किप गार्ड #1 — पंख सुरक्षित ढंग से लोड करना
# --------------------------------------------------------------
def _safe_load_image_clip(path: str, climax_start_time: float, climax_duration: float):
    """[काम]: पंख की इमेज लोड करना; न मिलने पर क्रैश होने से बचाकर None लौटाना"""
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
# 🔐 3. ऑटो-स्किप गार्ड #2 — हिंदी टेक्स्ट से PNG बनाकर ImageClip बनाना
# --------------------------------------------------------------
def _text_to_image_clip(text, output_filename, font_size, color, climax_start_time, climax_duration, canvas_width):
    """[काम]: HTML/PIL के ज़रिए हिंदी टेक्स्ट की पारदर्शी PNG इमेज रेंडर करना"""
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
# 🌊 4. लहराता हुआ मयूर पंख
# --------------------------------------------------------------
def _build_feather_clip(climax_start_time, climax_duration, canvas_width):
    """[काम]: मयूर पंख को स्क्रीन पर वेव मोशन (लहराता हुआ) देना"""
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
# 🎈 5. प्रोसीजरल पार्टिकल-ब्लास्ट (स्वतंत्र पार्टिकल एनीमेशन)
# --------------------------------------------------------------
def _build_particle_burst_clip(climax_start_time: float, climax_duration: float, canvas_width: int, canvas_height: int):
    """
    [काम]: स्क्रीन के केंद्र से फूटने वाले रंगीन कणों (Particles) का एनीमेशन बनाना।
    यह कोड से (PIL) बनता है, इसलिए मयूर पंख हो या न हो, यह ब्लास्ट हमेशा दिखेगा।
    """
    center_x, center_y = canvas_width // 2, canvas_height // 2

    particles = []
    for _ in range(PARTICLE_COUNT):
        particles.append({
            "angle": random.uniform(0, 2 * math.pi),
            "speed": random.uniform(PARTICLE_MIN_SPEED_PX, PARTICLE_MAX_SPEED_PX),
            "size": random.uniform(PARTICLE_MIN_SIZE_PX, PARTICLE_MAX_SIZE_PX),
            "color": random.choice(PARTICLE_COLOR_CHOICES),
        })

    def make_color_frame(t):
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
# 🔔 6. शुद्ध हिंदी "Subscribe" संदेश क्लिप
# --------------------------------------------------------------
def _build_subscribe_image_clip(climax_start_time, climax_duration, feather_height, canvas_width, canvas_height, font_scale):
    """[काम]: 'चैनल को लाइक और सब्सक्राइब करें 🔔' का हिंदी टेक्स्ट रेंडर करना और पोजीशन सेट करना"""
    subscribe_clip = _text_to_image_clip(
        text=SUBSCRIBE_MESSAGE, output_filename="subscribe_message.png",
        font_size=int(45 * font_scale), color=GOLD_COLOR,
        climax_start_time=climax_start_time, climax_duration=climax_duration, canvas_width=canvas_width,
    )
    if subscribe_clip is None:
        return None
    
    # पंख न होने पर भी टेक्स्ट को स्क्रीन के सही हिस्से पर रखना
    safe_offset = (feather_height / 2) if feather_height > 0 else 40
    vertical_gap = safe_offset + 20
    y_fraction = 0.5 + (vertical_gap / canvas_height)
    return subscribe_clip.with_position(lambda t: [0.5, y_fraction], relative=True)


# --------------------------------------------------------------
# 📰 7. यूज़र का आउट्रो मैसेज स्ट्रिप
# --------------------------------------------------------------
def _build_outro_note_image_clip(climax_start_time, climax_duration, feather_height, outro_text, canvas_width, canvas_height, font_scale):
    """[काम]: यूज़र द्वारा दिए गए आउट्रो हिंदी मैसेज की न्यूज़-पट्टी नीचे दिखाना"""
    if not outro_text or not outro_text.strip():
        return None

    outro_note_clip = _text_to_image_clip(
        text=f"📰 {outro_text.strip()}", output_filename="outro_note.png",
        font_size=int(35 * font_scale), color=WHITE_COLOR,
        climax_start_time=climax_start_time, climax_duration=climax_duration, canvas_width=canvas_width,
    )
    if outro_note_clip is None:
        return None

    safe_offset = (feather_height / 2) if feather_height > 0 else 40
    vertical_gap = safe_offset + 100
    y_fraction = 0.5 + (vertical_gap / canvas_height)
    return outro_note_clip.with_position(lambda t: [0.5, y_fraction], relative=True)


# --------------------------------------------------------------
# 🎬 8. मुख्य फ़ंक्शन — engine.py द्वारा कॉल किया जाने वाला मेन एंट्री पॉइंट
# --------------------------------------------------------------
def create_climax_layer(
    video_duration: float,
    outro_text: str,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    climax_duration_override: float = None,
    voiceover_mode: str = "hi-IN-SwaraNeural"
) -> tuple:
    """
    [मुख्य फ़ंक्शन का काम]:
    1. edge-tts की मदद से AI की शुद्ध हिंदी आवाज़ ("चैनल को लाइक और सब्सक्राइब करें") जनरेट करना।
    2. पार्टिकल-ब्लास्ट, लहराते पंख और हिंदी टेक्स्ट की विज़ुअल लेयर्स तैयार करना।
    3. engine.py के लिए विज़ुअल लेयर्स (climax_layers) और ऑडियो (outro_audio_clip) दोनों रिटर्न करना।
    """
    climax_duration = climax_duration_override if climax_duration_override else CLIMAX_DURATION_SECONDS
    climax_start_time = max(0.0, video_duration - climax_duration)

    layout_settings = _resolve_layout_settings(aspect_ratio)
    canvas_width = layout_settings["canvas_width"]
    canvas_height = layout_settings["canvas_height"]
    font_scale = layout_settings["font_scale"]

    # --- A) AI हिंदी आवाज़ (Edge-TTS) जनरेट करना ---
    outro_audio_clip = None
    spoken_text = "चैनल को लाइक और सब्सक्राइब करें।"
    if outro_text and outro_text.strip():
        spoken_text = f"{outro_text.strip()}। {spoken_text}"

    try:
        import edge_tts
        outro_voice_file = os.path.join(tempfile.gettempdir(), "outro_tts_temp.mp3")

        async def _generate_outro_voice():
            tts_voice = voiceover_mode if voiceover_mode else "hi-IN-SwaraNeural"
            communicate = edge_tts.Communicate(spoken_text, voice=tts_voice)
            await communicate.save(outro_voice_file)

        asyncio.run(_generate_outro_voice())

        if os.path.exists(outro_voice_file):
            outro_audio_clip = AudioFileClip(outro_voice_file).with_start(climax_start_time)
    except Exception as e:
        print(f"⚠️ [ऑटो-स्किप] आउट्रो AI आवाज़ जनरेट नहीं हो सकी: {e}")

    # --- B) विज़ुअल लेयर्स तैयार करना ---
    feather_clip, feather_height = _build_feather_clip(climax_start_time, climax_duration, canvas_width)

    # मयूर पंख हो या न हो, पार्टिकल ब्लास्ट हमेशा बनेगा
    particle_burst_clip = _build_particle_burst_clip(climax_start_time, climax_duration, canvas_width, canvas_height)

    subscribe_image_clip = _build_subscribe_image_clip(
        climax_start_time, climax_duration, feather_height, canvas_width, canvas_height, font_scale,
    )
    outro_note_image_clip = _build_outro_note_image_clip(
        climax_start_time, climax_duration, feather_height, outro_text, canvas_width, canvas_height, font_scale,
    )

    climax_layers = [feather_clip, particle_burst_clip, subscribe_image_clip, outro_note_image_clip]
    climax_layers = [clip for clip in climax_layers if clip is not None]

    return climax_layers, outro_audio_clip
