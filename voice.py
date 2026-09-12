"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो — voice.py
==============================================================
यह ब्लॉक "आवाज़ इंजन" (Voice Engine) है।
इसका काम है:
  1) दी गई हिंदी स्क्रिप्ट को AI आवाज़ (Text-to-Speech) में बदलना
  2) बैकग्राउंड में सितार संगीत को धीमा (Duck) करके मिलाना
  3) दोनों को मिलाकर एक फाइनल ऑडियो फाइल बनाना

यह फाइल पूरी तरह स्वतंत्र (independent) है — इसे app.py से
अलग टेस्ट भी किया जा सकता है।
==============================================================
"""

import asyncio
import os

import edge_tts               # टेक्स्ट को आवाज़ में बदलने के लिए
from pydub import AudioSegment  # दो ऑडियो को मिक्स करने के लिए
# प्युडब को बताना कि FFmpeg कहाँ है (ffdl चलाने के बाद यह अपने आप मिल जाता है)
import imageio_ffmpeg as im_ffmpeg
AudioSegment.converter = im_ffmpeg.get_ffmpeg_exe()



# --------------------------------------------------------------
# सेटिंग्स (Constants) — इन्हें ज़रूरत पड़ने पर आसानी से बदला जा सकता है
# --------------------------------------------------------------
BABA_VOICE = "hi-IN-MadhurNeural"          # भारतीय पुरुष आवाज़ (हिंदी)
BACKGROUND_MUSIC_FILE = "sitar_vadand_sfx.mp3"  # बैकग्राउंड सितार संगीत
MUSIC_DUCK_VOLUME = 0.15                   # संगीत को सिर्फ 15% वॉल्यूम पर रखना
TEMP_NARRATION_FILE = "temp_narration.mp3" # अस्थायी (temporary) नैरेशन फाइल


# --------------------------------------------------------------
# 1) स्क्रिप्ट को आवाज़ (Narration) में बदलने वाला फंक्शन
#    edge-tts एक "async" लाइब्रेरी है, इसलिए यह फंक्शन भी async है
# --------------------------------------------------------------
async def _generate_narration(script_text: str, narration_path: str) -> None:
    """
    दी गई हिंदी स्क्रिप्ट (script_text) को Microsoft Edge TTS के
    ज़रिए एक भारतीय पुरुष आवाज़ (hi-IN-MadhurNeural) में बदलता है
    और उसे narration_path पर एक MP3 फाइल के रूप में सेव करता है।
    """
    communicator = edge_tts.Communicate(text=script_text, voice=BABA_VOICE)
    await communicator.save(narration_path)


# --------------------------------------------------------------
# 2) बैकग्राउंड संगीत को "डक" (Duck / धीमा) करने वाला फंक्शन
# --------------------------------------------------------------
def _load_and_duck_background_music(target_duration_ms: int) -> AudioSegment:
    """
    बैकग्राउंड सितार संगीत फाइल को लोड करता है और:
      - उसकी आवाज़ को 15% वॉल्यूम (मखमली/धीमा) पर सेट करता है
      - नैरेशन जितनी ही लंबाई (duration) का संगीत तैयार करता है
        (ज़रूरत पड़ने पर संगीत को दोहराता/लूप करता है)
    """
    if not os.path.exists(BACKGROUND_MUSIC_FILE):
        raise FileNotFoundError(
            f"बैकग्राउंड म्यूज़िक फाइल नहीं मिली: '{BACKGROUND_MUSIC_FILE}'. "
            "कृपया इसे voice.py वाले फोल्डर में रखें।"
        )

    background_music = AudioSegment.from_file(BACKGROUND_MUSIC_FILE)

    # --- वॉल्यूम को 15% पर लाना (Ducking) ---
    # pydub में वॉल्यूम dB (डेसिबल) में बदलता है, इसलिए प्रतिशत को
    # dB में बदलने का गणितीय सूत्र (formula) इस्तेमाल किया गया है।
    import math
    volume_change_db = 20 * math.log10(MUSIC_DUCK_VOLUME)
    ducked_music = background_music + volume_change_db  # dB घटाना

    # --- संगीत की लंबाई नैरेशन जितनी करना ---
    if len(ducked_music) < target_duration_ms:
        # अगर संगीत छोटा है तो उसे बार-बार दोहराओ (loop)
        repeat_count = (target_duration_ms // len(ducked_music)) + 1
        ducked_music = ducked_music * repeat_count

    # आखिर में सिर्फ ज़रूरत जितना हिस्सा काटना
    ducked_music = ducked_music[:target_duration_ms]

    return ducked_music


# --------------------------------------------------------------
# 3) मुख्य फंक्शन — यही बाहर से (app.py से) बुलाया जाएगा
# --------------------------------------------------------------
def create_baba_audio(script_text: str, output_audio_path: str) -> str:
    """
    यह मुख्य फंक्शन है जो पूरी प्रक्रिया को जोड़ता (orchestrate) है:

      चरण 1: स्क्रिप्ट से नैरेशन (बाबा की आवाज़) बनाना
      चरण 2: बैकग्राउंड सितार संगीत को 15% वॉल्यूम पर लाना
      चरण 3: दोनों को आपस में मिक्स करना
      चरण 4: फाइनल ऑडियो को output_audio_path पर सेव करना

    पैरामीटर:
        script_text (str)       -> हिंदी कहानी/स्क्रिप्ट
        output_audio_path (str) -> फाइनल ऑडियो कहाँ सेव करना है

    रिटर्न:
        output_audio_path (str) -> सफल होने पर फाइनल फाइल का पथ
    """

    if not script_text or not script_text.strip():
        raise ValueError("स्क्रिप्ट खाली है! कृपया कोई कहानी दें।")

    # --- चरण 1: नैरेशन (आवाज़) जनरेट करना ---
    # चूँकि edge-tts async है, इसे asyncio.run() से चलाया जाता है
    asyncio.run(_generate_narration(script_text, TEMP_NARRATION_FILE))
    narration_audio = AudioSegment.from_file(TEMP_NARRATION_FILE)

    # --- चरण 2: बैकग्राउंड संगीत तैयार करना (नैरेशन जितना लंबा) ---
    background_audio = _load_and_duck_background_music(
        target_duration_ms=len(narration_audio)
    )

    # --- चरण 3: नैरेशन और संगीत को मिक्स (overlay) करना ---
    # overlay() दोनों ऑडियो को एक साथ (एक के ऊपर एक) बजाता है
    final_mix = narration_audio.overlay(background_audio)

    # --- चरण 4: फाइनल फाइल सेव करना ---
    final_mix.export(output_audio_path, format="mp3")

    # --- अस्थायी (temporary) नैरेशन फाइल को साफ करना ---
    if os.path.exists(TEMP_NARRATION_FILE):
        os.remove(TEMP_NARRATION_FILE)

    return output_audio_path


# --------------------------------------------------------------
# इस फाइल को सीधे चलाकर टेस्ट करने के लिए (Optional)
# --------------------------------------------------------------
if __name__ == "__main__":
    sample_script = "इस पवित्र मंदिर की स्थापना सैकड़ों वर्ष पहले हुई थी।"
    result_path = create_baba_audio(sample_script, "baba_final_output.mp3")
    print(f"✅ ऑडियो सफलतापूर्वक बनी: {result_path}")
    