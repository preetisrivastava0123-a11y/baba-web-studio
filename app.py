"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो — ३-स्वतंत्र-ट्रैक संस्करण (No Tabs)
==============================================================
यह वर्ज़न पुराने "visual_clips" (फोटो+वीडियो मिला हुआ डिब्बा) को
पूरी तरह हटाकर ३ बिल्कुल अलग-अलग, स्वतंत्र डिब्बों में तोड़ता है:

    १) st.session_state["video_clips"]  → केवल वीडियो क्लिप्स (MP4/MOV)
    २) st.session_state["music_tracks"] → केवल म्यूज़िक/भजन (MP3 आदि)
    ३) st.session_state["sfx_events"]   → केवल SFX ध्वनियाँ (शंखनाद, डमरू)

तीनों ट्रैक्स एक जैसे पैटर्न पर बने हैं ताकि १००% स्टेट-सेफ रहें:
"+ जोड़ें" बटन दबाते ही लिस्ट में एक *खाली स्लॉट* (एक यूनीक
slot_id के साथ) जुड़ जाता है। उसके बाद नीचे एक 'for loop' हर
स्लॉट के लिए उसका बिल्कुल अपना, स्वतंत्र st.file_uploader +
समय/वॉल्यूम इनपुट दिखाता है। हर विजेट की key हमेशा उस स्लॉट के
अपरिवर्तनीय slot_id पर टिकी होती है (पोज़िशन/नाम पर नहीं), इसलिए
कोई भी स्लॉट जोड़ें, हटाएँ या दोबारा-रन (rerun) करें — बाकी सभी
स्लॉट्स की अपलोड की गई फाइलें और वैल्यूज़ कभी गायब नहीं होतीं।

⚠️ ज़रूरी मान्यता (Assumption): यूज़र के निर्देश में साफ़ लिखा है
"तस्वीरों को भूल जाओ" — इसलिए इस अपग्रेड में ट्रैक 1 से फोटो/इमेज
सपोर्ट पूरी तरह हटा दिया गया है, वह सिर्फ़ वीडियो क्लिप्स के लिए
है। साथ ही यह फाइल मानती है कि engine.py का
compile_cinematic_video() फंक्शन नीचे दिए kwargs
(video_clips, music_tracks, sfx_events, outro_voice_active आदि)
स्वीकार करता है। अगर पैरामीटर-नाम अलग हैं, तो सिर्फ़
_build_engine_kwargs() फंक्शन बदलना होगा, बाकी कोड वैसा ही रहेगा।
==============================================================
"""

import os
import subprocess
import tempfile

import streamlit as st

# --------------------------------------------------------------
# 1) पेज की बुनियादी सेटिंग — सबसे पहला Streamlit-कमांड
# --------------------------------------------------------------
st.set_page_config(
    page_title="बाबा जनरेटिव वेब स्टूडियो",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# moviepy के दोनों प्रमुख वर्ज़न-स्टाइल सपोर्ट करने के लिए सुरक्षित import
try:
    from moviepy import VideoFileClip  # moviepy >= 2.0
except ImportError:
    from moviepy.editor import VideoFileClip  # moviepy 1.x

from engine import compile_cinematic_video

# --------------------------------------------------------------
# वैकल्पिक (Optional) लाइब्रेरी — अगर उपलब्ध न हों तो ऐप न टूटे
# --------------------------------------------------------------
try:
    from pypdf import PdfReader
    PDF_SUPPORT_AVAILABLE = True
except Exception:
    PDF_SUPPORT_AVAILABLE = False

try:
    import docx as docx_lib
    DOCX_SUPPORT_AVAILABLE = True
except Exception:
    DOCX_SUPPORT_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except Exception:
    REQUESTS_AVAILABLE = False


# --------------------------------------------------------------
# 2) Playwright Chromium इंस्टॉल — सिर्फ़ एक बार (set_page_config के बाद)
# --------------------------------------------------------------
@st.cache_resource
def _ensure_playwright_chromium_installed():
    """Playwright का हेडलेस Chromium ब्राउज़र इंस्टॉल करता है (सिर्फ़ एक बार)।"""
    try:
        result = subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode == 0:
            return True, None
        return False, (result.stderr or result.stdout or "अज्ञात त्रुटि")
    except Exception as install_error:
        return False, str(install_error)


# --------------------------------------------------------------
# 3) डार्क-थीम CSS — पुराना केसरी/सुनहरा लुक १००% सुरक्षित रखा गया है
#    (सिर्फ़ नए वीडियो-बैज के लिए एक छोटा-सा class जोड़ा गया है)
# --------------------------------------------------------------
def apply_dark_theme():
    """पुराना डार्क + सुनहरा सिनेमैटिक लुक — बिना किसी पुराने बदलाव के तोड़े।"""
    st.markdown(
        """
        <style>
        .stApp { background: linear-gradient(160deg, #0d0d0d 0%, #1a1a2e 100%); color: #f5f5f5; }
        .main-title {
            text-align: center; font-size: 42px; font-weight: 800;
            background: -webkit-linear-gradient(45deg, #ffd700, #ff8c00);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 0px;
        }
        .sub-title { text-align: center; color: #b0b0b0; font-size: 16px; margin-bottom: 20px; }
        .track-heading {
            color: #ffd700; font-size: 22px; font-weight: 800; margin-top: 30px; margin-bottom: 10px;
            border-bottom: 2px solid rgba(255,215,0,0.3); padding-bottom: 6px;
        }
        .section-heading { color: #ffd700; font-size: 18px; font-weight: 700; margin-top: 15px; margin-bottom: 8px; }
        .timeline-card {
            background: rgba(255,255,255,0.04); border: 1px solid rgba(255,215,0,0.25);
            border-radius: 12px; padding: 14px; margin-bottom: 14px;
        }
        .order-badge {
            background: linear-gradient(90deg, #ffd700, #ff8c00); color: #0d0d0d; font-weight: 800;
            border-radius: 8px; padding: 4px 10px; display: inline-block; margin-bottom: 6px; font-size: 13px;
        }
        .video-badge {
            background: linear-gradient(90deg, #00c6ff, #0072ff); color: #fff; font-weight: 700;
            border-radius: 8px; padding: 3px 9px; display: inline-block; font-size: 12px;
        }
        .sfx-badge {
            background: linear-gradient(90deg, #8e2de2, #4a00e0); color: #fff; font-weight: 700;
            border-radius: 8px; padding: 3px 9px; display: inline-block; font-size: 12px;
        }
        .music-badge {
            background: linear-gradient(90deg, #ff8c00, #ff416c); color: #fff; font-weight: 700;
            border-radius: 8px; padding: 3px 9px; display: inline-block; font-size: 12px;
        }
        /* लाल रंग का "जोड़ें" बटन — सभी ट्रैक्स के लिए एक जैसा */
        div.stButton > button:first-child {
            background: linear-gradient(90deg, #ff416c, #ff4b2b); color: white; font-size: 17px;
            font-weight: 800; padding: 10px 0px; border-radius: 12px; border: none; width: 100%;
            box-shadow: 0px 0px 18px rgba(255, 75, 43, 0.55); transition: 0.3s;
        }
        div.stButton > button:first-child:hover { transform: scale(1.02); box-shadow: 0px 0px 28px rgba(255, 75, 43, 0.9); }
        div.stDownloadButton > button:first-child {
            background: linear-gradient(90deg, #11998e, #38ef7d); color: #0d0d0d; font-size: 20px;
            font-weight: 800; padding: 15px 0px; border-radius: 12px; border: none; width: 100%;
            box-shadow: 0px 0px 20px rgba(56, 239, 125, 0.6); transition: 0.3s;
        }
        div.stDownloadButton > button:first-child:hover { transform: scale(1.02); box-shadow: 0px 0px 30px rgba(56, 239, 125, 0.9); }
        </style>
        """,
        unsafe_allow_html=True
    )


def render_header():
    st.markdown('<div class="main-title">🎬 बाबा जनरेटिव वेब स्टूडियो</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">३ बिल्कुल स्वतंत्र ट्रैक्स — वीडियो, म्यूज़िक और SFX कभी आपस में नहीं मिलेंगे</div>', unsafe_allow_html=True)
    st.divider()


# --------------------------------------------------------------
# 4) सारा session_state एक जगह इनिशियलाइज़ — १००% स्टेट प्रिज़र्वेशन
# --------------------------------------------------------------
def _initialize_session_state():
    """
    यह फंक्शन हर rerun पर चलता है, लेकिन 'if key not in st.session_state'
    की वजह से सिर्फ़ पहली बार ही डिफ़ॉल्ट मान भरता है — इसके बाद यूज़र
    का डेटा कभी रीसेट नहीं होता, चाहे कितनी भी फाइलें अपलोड हों या
    बटन दबें। हर ट्रैक का अपना अलग _slot_counter है जो सिर्फ़ बढ़ता
    है (कभी दोबारा इस्तेमाल नहीं होता) ताकि हर स्लॉट की widget-key
    हमेशा-हमेशा के लिए यूनीक और स्थिर रहे।
    """
    default_values = {
        # --- कहानी / आउट्रो ---
        "story_script_text": "",
        "ticker_text_value": "",
        "ticker_manually_edited": False,
        "last_story_doc_name": None,

        # --- फॉर्मेट व क्वालिटी ---
        "video_format_choice": "📱 9:16 Shorts (कहानी के अनुसार)",
        "duration_choice_value": "5 मिनट",
        "custom_duration_minutes": 10,
        "quality_choice_value": "720p HD",
        "subtitle_color_choice": "पीला (Gold)",
        "subtitle_font_size": 65,
        "voiceover_mode": "🕉️ बाबा एआई दिव्य आवाज़ (Edge-TTS)",

        # --- 🎬 ट्रैक 1: स्वतंत्र वीडियो क्लिप्स (केवल MP4/MOV, कोई फोटो नहीं) ---
        "video_clips": [],
        "video_slot_counter": 0,

        # --- 🎵 ट्रैक 2: स्वतंत्र म्यूज़िक/भजन ट्रैक ---
        "music_tracks": [],
        "music_slot_counter": 0,
        "master_music_volume": 0.8,

        # --- 🔊 ट्रैक 3: स्वतंत्र SFX ध्वनि टाइमलाइन ---
        "sfx_events": [],
        "sfx_slot_counter": 0,
        "sfx_search_results": [],

        # --- लाइव ड्राफ्ट प्लेयर ---
        "draft_video_path": None,
    }
    for key, default_value in default_values.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


# --------------------------------------------------------------
# 5) छोटे हेल्पर्स
# --------------------------------------------------------------
def _save_uploaded_file_to_temp(uploaded_file):
    """Streamlit UploadedFile को अस्थायी डिस्क-फाइल में बदलता है (moviepy को असली पाथ चाहिए)।"""
    file_extension = os.path.splitext(uploaded_file.name)[1]
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
    temp_file.write(uploaded_file.getvalue())
    temp_file.close()
    return temp_file.name


def _probe_video_duration_and_thumbnail(video_path, unique_tag):
    """
    वीडियो की असली लंबाई पढ़ता है (ताकि End Second का डिफ़ॉल्ट सही मिले)
    और बीच का एक फ्रेम थंबनेल के तौर पर सेव करता है। कोई भी दिक्कत आए
    तो चुपचाप डिफ़ॉल्ट मान लौटा देता है — ऐप कभी क्रैश नहीं होता।
    """
    default_duration = 5.0
    thumbnail_path = None
    try:
        with VideoFileClip(video_path) as clip:
            actual_duration = clip.duration or default_duration
            safe_default_end = min(default_duration, actual_duration)
            thumbnail_path = os.path.join(tempfile.gettempdir(), f"thumb_{unique_tag}.jpg")
            clip.save_frame(thumbnail_path, t=min(0.5, actual_duration / 2))
            return safe_default_end, thumbnail_path
    except Exception:
        return default_duration, thumbnail_path


# ================================================================
# 🎬 ट्रैक 1 — स्वतंत्र वीडियो क्लिप्स टाइमलाइन (केवल वीडियो, कोई फोटो नहीं)
# ================================================================
def render_video_track():
    st.markdown('<div class="track-heading">🎬 ट्रैक 1: वीडियो क्लिप्स टाइमलाइन (Separate Video Track)</div>', unsafe_allow_html=True)
    st.caption("यह पटरी केवल वीडियो क्लिप्स (MP4/MOV) के लिए है — म्यूज़िक या SFX से पूरी तरह स्वतंत्र और अलग।")

    if st.button("➕ नया वीडियो क्लिप टाइमलाइन पर जोड़ें", key="add_video_slot_button"):
        st.session_state["video_slot_counter"] += 1
        new_slot_id = st.session_state["video_slot_counter"]
        st.session_state["video_clips"].append({
            "slot_id": new_slot_id,
            "path": None,
            "name": None,
            "start": 0.0,
            "end": 5.0,
            "thumbnail": None,
        })
        st.rerun()

    if not st.session_state["video_clips"]:
        st.info("अभी तक कोई वीडियो-क्लिप स्लॉट नहीं जोड़ा गया। ऊपर वाला बटन दबाकर पहला स्लॉट जोड़ें।")
        return

    for slot in st.session_state["video_clips"]:
        slot_id = slot["slot_id"]
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            st.markdown(f'<span class="video-badge">🎞️ वीडियो स्लॉट #{slot_id}</span>', unsafe_allow_html=True)

            uploader_col, trim_col, remove_col = st.columns([2, 2, 0.6])

            with uploader_col:
                uploaded_file = st.file_uploader(
                    "इस स्लॉट के लिए वीडियो अपलोड करें (MP4, MOV)",
                    type=["mp4", "mov"],
                    key=f"video_file_{slot_id}",
                )
                if uploaded_file is not None and uploaded_file.name != slot["name"]:
                    saved_path = _save_uploaded_file_to_temp(uploaded_file)
                    default_end, thumb = _probe_video_duration_and_thumbnail(saved_path, f"video_{slot_id}")
                    slot["path"] = saved_path
                    slot["name"] = uploaded_file.name
                    slot["end"] = default_end
                    slot["thumbnail"] = thumb
                if slot["thumbnail"]:
                    st.image(slot["thumbnail"], use_container_width=True)

            with trim_col:
                start_key = f"vstart_{slot_id}"
                end_key = f"vend_{slot_id}"

                def _on_start_change(target_slot=slot, widget_key=start_key):
                    target_slot["start"] = st.session_state[widget_key]

                def _on_end_change(target_slot=slot, widget_key=end_key):
                    target_slot["end"] = st.session_state[widget_key]

                st.number_input("प्रकट होने का समय — Start Second", min_value=0.0, value=slot["start"],
                                 step=0.5, key=start_key, on_change=_on_start_change)
                st.number_input("हटने का समय — End Second", min_value=0.5, value=slot["end"],
                                 step=0.5, key=end_key, on_change=_on_end_change)

            with remove_col:
                st.write("")
                if st.button("❌", key=f"remove_video_slot_{slot_id}"):
                    st.session_state["video_clips"] = [
                        c for c in st.session_state["video_clips"] if c["slot_id"] != slot_id
                    ]
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)


# ================================================================
# 🎵 ट्रैक 2 — स्वतंत्र म्यूज़िक क्लिप्स टाइमलाइन
# ================================================================
def render_music_track():
    st.markdown('<div class="track-heading">🎵 ट्रैक 2: म्यूज़िक/भजन क्लिप्स टाइमलाइन (Separate Music Track)</div>', unsafe_allow_html=True)
    st.caption("यह पटरी वीडियो और SFX से बिल्कुल अलग है — यहाँ सिर्फ़ भजन/संगीत सिंक होते हैं।")

    if st.button("➕ नया म्यूज़िक/भजन ट्रैक टाइमलाइन पर जोड़ें", key="add_music_slot_button"):
        st.session_state["music_slot_counter"] += 1
        new_slot_id = st.session_state["music_slot_counter"]
        st.session_state["music_tracks"].append({
            "slot_id": new_slot_id,
            "path": None,
            "name": None,
            "start": 0.0,
            "end": 0.0,  # 0.0 = पूरा ट्रैक (Full Mode)
            "instrumental_only": False,
            "volume": 0.8,
        })
        st.rerun()

    if not st.session_state["music_tracks"]:
        st.info("अभी तक कोई म्यूज़िक स्लॉट नहीं जोड़ा गया — डिफ़ॉल्ट बैकग्राउंड सितार-संगीत इस्तेमाल होगा।")
    else:
        for slot in st.session_state["music_tracks"]:
            slot_id = slot["slot_id"]
            with st.container():
                st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
                st.markdown(f'<span class="music-badge">🎶 म्यूज़िक स्लॉट #{slot_id}</span>', unsafe_allow_html=True)

                uploader_col, start_col, end_col, toggle_col, volume_col, remove_col = st.columns(
                    [1.8, 1.1, 1.1, 1.3, 1.3, 0.5]
                )

                with uploader_col:
                    uploaded_file = st.file_uploader(
                        "भजन/संगीत अपलोड करें (MP3, WAV, M4A)",
                        type=["mp3", "wav", "m4a"],
                        key=f"music_file_{slot_id}",
                    )
                    if uploaded_file is not None and uploaded_file.name != slot["name"]:
                        slot["path"] = _save_uploaded_file_to_temp(uploaded_file)
                        slot["name"] = uploaded_file.name

                with start_col:
                    start_key = f"mstart_{slot_id}"

                    def _on_m_start(target_slot=slot, widget_key=start_key):
                        target_slot["start"] = st.session_state[widget_key]

                    st.number_input("शुरू होने का समय (Start Second)", min_value=0.0, value=slot["start"],
                                     step=1.0, key=start_key, on_change=_on_m_start)

                with end_col:
                    end_key = f"mend_{slot_id}"

                    def _on_m_end(target_slot=slot, widget_key=end_key):
                        target_slot["end"] = st.session_state[widget_key]

                    st.number_input("बंद होने का समय (End, 0=पूरा)", min_value=0.0, value=slot["end"],
                                     step=1.0, key=end_key, on_change=_on_m_end)

                with toggle_col:
                    toggle_key = f"minstr_{slot_id}"

                    def _on_instrumental_change(target_slot=slot, widget_key=toggle_key):
                        target_slot["instrumental_only"] = st.session_state[widget_key]

                    st.toggle("केवल इंस्ट्रूमेंटल", value=slot["instrumental_only"],
                              key=toggle_key, on_change=_on_instrumental_change)

                with volume_col:
                    volume_key = f"mvol_{slot_id}"

                    def _on_volume_change(target_slot=slot, widget_key=volume_key):
                        target_slot["volume"] = st.session_state[widget_key]

                    st.slider("ट्रैक वॉल्यूम", 0.0, 1.0, value=slot["volume"], step=0.05,
                              key=volume_key, on_change=_on_volume_change)

                with remove_col:
                    st.write("")
                    if st.button("❌", key=f"remove_music_slot_{slot_id}"):
                        st.session_state["music_tracks"] = [
                            m for m in st.session_state["music_tracks"] if m["slot_id"] != slot_id
                        ]
                        st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-heading">🎛️ मुख्य संगीत वॉल्यूम (पूरे वीडियो के लिए ग्लोबल)</div>', unsafe_allow_html=True)
    st.slider("मुख्य संगीत वॉल्यूम", 0.0, 1.0, key="master_music_volume", label_visibility="collapsed")


# ================================================================
# 🔊 ट्रैक 3 — स्वतंत्र SFX ध्वनि टाइमलाइन
# ================================================================
def _search_freesound(query_text):
    """Freesound पर ध्वनि खोजता है (API-key की ज़रूरत है)।"""
    if not REQUESTS_AVAILABLE:
        st.warning("⚠️ 'requests' लाइब्रेरी उपलब्ध नहीं है — requirements.txt में जोड़ें।")
        return []
    api_key = st.secrets.get("FREESOUND_API_KEY", None) if hasattr(st, "secrets") else None
    if not api_key:
        st.warning("⚠️ Freesound API-key सेट नहीं है (Settings → Secrets में FREESOUND_API_KEY जोड़ें)।")
        return []
    try:
        response = requests.get(
            "https://freesound.org/apiv2/search/text/",
            params={"query": query_text, "token": api_key, "fields": "id,name"}, timeout=10,
        )
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as search_error:
        st.warning(f"⚠️ सर्च में समस्या: {search_error}")
        return []


def render_sfx_track():
    st.markdown('<div class="track-heading">🔊 ट्रैक 3: SFX ध्वनि टाइमलाइन (Separate SFX Track)</div>', unsafe_allow_html=True)
    st.caption("शंखनाद, डमरू जैसी ध्वनियाँ — वीडियो और म्यूज़िक से बिल्कुल अलग, तीसरी स्वतंत्र पटरी।")

    st.markdown('<div class="section-heading">🌐 इंटरनेट साउंड सर्च (Freesound) — वैकल्पिक</div>', unsafe_allow_html=True)
    search_col1, search_col2 = st.columns([3, 1])
    with search_col1:
        search_query = st.text_input("ध्वनि खोजें", key="sfx_search_query", label_visibility="collapsed",
                                       placeholder="जैसे: शंखनाद, घंटी, डमरू...")
    with search_col2:
        if st.button("🔍 खोजें", key="sfx_search_button"):
            st.session_state["sfx_search_results"] = _search_freesound(search_query)

    if st.session_state["sfx_search_results"]:
        st.caption("खोज परिणाम (Freesound पर जाकर डाउनलोड करें, फिर नीचे किसी स्लॉट में अपलोड करें):")
        for result in st.session_state["sfx_search_results"][:5]:
            st.markdown(f"🔉 {result.get('name', 'अज्ञात ध्वनि')}")

    if st.button("➕ SFX ध्वनि जोड़ें", key="add_sfx_slot_button"):
        st.session_state["sfx_slot_counter"] += 1
        new_slot_id = st.session_state["sfx_slot_counter"]
        st.session_state["sfx_events"].append({
            "slot_id": new_slot_id,
            "path": None,
            "name": None,
            "trigger_second": 0.0,
            "duration": 2.0,
            "volume": 0.7,
        })
        st.rerun()

    if not st.session_state["sfx_events"]:
        st.info("अभी तक कोई SFX ध्वनि-इवेंट नहीं जोड़ा गया।")
        return

    for slot in st.session_state["sfx_events"]:
        slot_id = slot["slot_id"]
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            st.markdown(f'<span class="sfx-badge">🎯 SFX स्लॉट #{slot_id}</span>', unsafe_allow_html=True)

            uploader_col, trigger_col, duration_col, volume_col, remove_col = st.columns(
                [1.8, 1.1, 1.1, 1.3, 0.5]
            )

            with uploader_col:
                uploaded_file = st.file_uploader(
                    "SFX ध्वनि-फाइल अपलोड करें (MP3, WAV)",
                    type=["mp3", "wav"],
                    key=f"sfx_file_{slot_id}",
                )
                if uploaded_file is not None and uploaded_file.name != slot["name"]:
                    slot["path"] = _save_uploaded_file_to_temp(uploaded_file)
                    slot["name"] = uploaded_file.name

            with trigger_col:
                trigger_key = f"sfxtrigger_{slot_id}"

                def _on_trigger_change(target_slot=slot, widget_key=trigger_key):
                    target_slot["trigger_second"] = st.session_state[widget_key]

                st.number_input("ट्रिगर सेकंड", min_value=0.0, value=slot["trigger_second"],
                                 step=0.5, key=trigger_key, on_change=_on_trigger_change)

            with duration_col:
                duration_key = f"sfxduration_{slot_id}"

                def _on_duration_change(target_slot=slot, widget_key=duration_key):
                    target_slot["duration"] = st.session_state[widget_key]

                st.number_input("ड्यूरेशन (सेकंड)", min_value=0.1, value=slot["duration"],
                                 step=0.5, key=duration_key, on_change=_on_duration_change)

            with volume_col:
                volume_key = f"sfxvol_{slot_id}"

                def _on_sfx_vol_change(target_slot=slot, widget_key=volume_key):
                    target_slot["volume"] = st.session_state[widget_key]

                st.slider("वॉल्यूम", 0.0, 1.0, value=slot["volume"], step=0.05,
                          key=volume_key, on_change=_on_sfx_vol_change)

            with remove_col:
                st.write("")
                if st.button("❌", key=f"remove_sfx_slot_{slot_id}"):
                    st.session_state["sfx_events"] = [
                        e for e in st.session_state["sfx_events"] if e["slot_id"] != slot_id
                    ]
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)


# ================================================================
# 📄 ग्रन्थ अपलोडर + कथा ऑटो-सिंक + न्यूज़ पट्टी
# ================================================================
def render_story_section():
    st.markdown('<div class="track-heading">📄 कथा / ग्रन्थ (PDF या Word) — कहानी और वॉइस</div>', unsafe_allow_html=True)

    uploaded_document = st.file_uploader(
        "कथा/ग्रन्थ अपलोड करें (वैकल्पिक — PDF या Word दोनों चलेंगे)",
        type=["pdf", "docx"], key="story_document_uploader",
    )

    if uploaded_document is not None and st.session_state["last_story_doc_name"] != uploaded_document.name:
        extracted_text = ""
        file_extension = os.path.splitext(uploaded_document.name)[1].lower()

        if file_extension == ".pdf" and PDF_SUPPORT_AVAILABLE:
            try:
                pdf_reader = PdfReader(uploaded_document)
                extracted_text = "\n".join((page.extract_text() or "") for page in pdf_reader.pages).strip()
            except Exception as pdf_error:
                st.warning(f"⚠️ PDF पढ़ने में समस्या: {pdf_error}")
        elif file_extension == ".docx" and DOCX_SUPPORT_AVAILABLE:
            try:
                word_document = docx_lib.Document(uploaded_document)
                extracted_text = "\n".join(paragraph.text for paragraph in word_document.paragraphs).strip()
            except Exception as docx_error:
                st.warning(f"⚠️ Word फाइल पढ़ने में समस्या: {docx_error}")
        elif file_extension == ".pdf":
            st.warning("⚠️ PDF सपोर्ट के लिए requirements.txt में 'pypdf' जोड़ें।")
        elif file_extension == ".docx":
            st.warning("⚠️ Word सपोर्ट के लिए requirements.txt में 'python-docx' जोड़ें।")

        if extracted_text:
            st.session_state["story_script_text"] = extracted_text
            st.session_state["last_story_doc_name"] = uploaded_document.name
            # अगर यूज़र ने न्यूज़-पट्टी को हाथ से एडिट नहीं किया, तो ऑटो-सिंक करना
            if not st.session_state["ticker_manually_edited"]:
                st.session_state["ticker_text_value"] = extracted_text
            st.success("✅ दस्तावेज़ से टेक्स्ट निकालकर कहानी-बॉक्स में भर दिया गया है।")

    st.markdown('<div class="section-heading">📝 कहानी / स्क्रिप्ट लिखें</div>', unsafe_allow_html=True)

    def _on_story_text_change():
        """
        जब भी यूज़र कहानी-बॉक्स में कुछ लिखे/बदले, और उसने न्यूज़-पट्टी
        को खुद से एडिट न किया हो, तो न्यूज़-पट्टी अपने आप उसी टेक्स्ट
        से सिंक हो जाए (डिफ़ॉल्ट सिंक व्यवहार)।
        """
        if not st.session_state["ticker_manually_edited"]:
            st.session_state["ticker_text_value"] = st.session_state["story_script_text"]

    st.text_area(
        "अपनी कहानी या स्क्रिप्ट यहाँ लिखें/एडिट करें", height=200,
        key="story_script_text", on_change=_on_story_text_change,
    )

    st.markdown('<div class="section-heading">📰 न्यूज़ पट्टी / आउट्रो कमेंट (डिफ़ॉल्ट रूप से कहानी से सिंक)</div>', unsafe_allow_html=True)

    def _on_ticker_manual_edit():
        st.session_state["ticker_manually_edited"] = True

    st.text_input(
        "न्यूज़ पट्टी / आउट्रो टेक्स्ट", key="ticker_text_value",
        on_change=_on_ticker_manual_edit,
    )

    st.markdown('<div class="section-heading">🎙️ वॉइसओवर मोड</div>', unsafe_allow_html=True)
    st.radio(
        "वॉइसओवर", options=["🕉️ बाबा एआई दिव्य आवाज़ (Edge-TTS)", "🎤 मेरी अपनी रिकॉर्डेड आवाज़"],
        key="voiceover_mode", label_visibility="collapsed",
    )

    custom_audio_file = None
    if st.session_state["voiceover_mode"].startswith("🎤"):
        custom_audio_file = st.file_uploader(
            "रिकॉर्डेड ऑडियो अपलोड करें (MP3/WAV)", type=["mp3", "wav", "m4a"], key="custom_voice_uploader",
        )
        if custom_audio_file is None:
            st.warning("⚠️ कृपया अपनी रिकॉर्डेड ऑडियो अपलोड करें।")

    return custom_audio_file


# ================================================================
# ⏱️ फॉर्मेट, ड्यूरेशन (Custom सहित) और क्वालिटी सेटिंग्स
# ================================================================
def render_settings_section():
    st.markdown('<div class="track-heading">⚙️ फॉर्मेट, ड्यूरेशन और क्वालिटी</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-heading">🎞️ वीडियो फॉर्मेट</div>', unsafe_allow_html=True)
    st.radio(
        "फॉर्मेट", options=["📱 9:16 Shorts (कहानी के अनुसार)", "🖥️ 16:9 Long Video"],
        horizontal=True, key="video_format_choice", label_visibility="collapsed",
    )
    is_long_format = st.session_state["video_format_choice"].startswith("🖥️")

    st.markdown('<div class="section-heading">⏱️ वीडियो लंबाई</div>', unsafe_allow_html=True)
    st.radio(
        "ड्यूरेशन", options=["5 मिनट", "30 मिनट", "1 घंटा", "Custom (कस्टम)"],
        horizontal=True, key="duration_choice_value",
    )
    duration_minutes_map = {"5 मिनट": 5, "30 मिनट": 30, "1 घंटा": 60}

    if st.session_state["duration_choice_value"] == "Custom (कस्टम)":
        # --- कस्टम चुनते ही १ से ६० मिनट का इनपुट बॉक्स खुलता है ---
        st.number_input(
            "कस्टम ड्यूरेशन (मिनट में, 1 से 60 तक)", min_value=1, max_value=60,
            key="custom_duration_minutes",
        )
        duration_seconds = st.session_state["custom_duration_minutes"] * 60
    else:
        duration_seconds = duration_minutes_map[st.session_state["duration_choice_value"]] * 60

    st.markdown('<div class="section-heading">🎨 सबटाइटल स्टाइल (हिंदी फॉन्ट-फिक्स सुरक्षित)</div>', unsafe_allow_html=True)
    st.selectbox("सबटाइटल रंग", options=["पीला (Gold)", "सफ़ेद (White)"], key="subtitle_color_choice")
    st.slider("सबटाइटल फॉन्ट साइज़", 50, 90, key="subtitle_font_size")

    st.markdown('<div class="section-heading">🎚️ आउटपुट क्वालिटी</div>', unsafe_allow_html=True)
    st.radio(
        "क्वालिटी", options=["720p HD", "1080p Full HD"], horizontal=True,
        key="quality_choice_value", label_visibility="collapsed",
    )

    return is_long_format, duration_seconds


# ================================================================
# हेल्पर्स — फाइनल रेंडर के लिए kwargs, वैलिडेशन और थंबनेल
# ================================================================
def _generate_final_thumbnail(video_path):
    thumbnail_path = os.path.join(tempfile.gettempdir(), "cinematic_thumbnail.jpg")
    with VideoFileClip(video_path) as clip:
        clip.save_frame(thumbnail_path, t=clip.duration / 2)
    return thumbnail_path


def _build_engine_kwargs(inputs, output_path):
    """
    session_state में रखे तीनों स्वतंत्र ट्रैक्स (video_clips/
    music_tracks/sfx_events) को सीधे engine.py के अपेक्षित फॉर्मेट
    में बदलकर kwargs dictionary बनाता है। तीनों लिस्ट पूरी तरह
    अलग-अलग रहती हैं — कहीं भी आपस में नहीं मिलतीं।
    """
    resolved_video_clips = [
        {"path": c["path"], "start": c["start"], "end": c["end"]}
        for c in st.session_state["video_clips"] if c["path"]
    ]
    resolved_music_tracks = [
        {"path": m["path"], "instrumental_only": m["instrumental_only"],
         "volume": m["volume"], "start": m["start"], "end": m["end"]}
        for m in st.session_state["music_tracks"] if m["path"]
    ]
    resolved_sfx_events = [
        {"path": e["path"], "trigger_second": e["trigger_second"],
         "duration": e["duration"], "volume": e["volume"]}
        for e in st.session_state["sfx_events"] if e["path"]
    ]

    return dict(
        video_clips=resolved_video_clips,
        music_tracks=resolved_music_tracks,
        master_music_volume=st.session_state["master_music_volume"],
        sfx_events=resolved_sfx_events,
        script_text=inputs["story_script"],
        outro_text=inputs["ticker_text"],
        output_video_path=output_path,
        aspect_ratio=inputs["aspect_ratio"],
        duration_seconds=inputs["duration_seconds"],
        quality=inputs["quality"],
        sub_color=inputs["sub_color"],
        sub_size=inputs["sub_size"],
        voiceover_mode=inputs["voiceover_mode"],
        custom_audio_path=inputs["custom_audio_path"],
        outro_voice_active=True,  # आख़िरी 5.5 सेकंड में मयूर-पंख + VFX ब्लास्ट + बाबा-स्पीच
    )


def _validate_timeline():
    """Generate दबाने से पहले बुनियादी जाँच — कोई भी गंभीर समस्या हो तो रोकना।"""
    problems = []

    video_slots_with_file = [c for c in st.session_state["video_clips"] if c["path"]]
    if not video_slots_with_file:
        problems.append("❌ ट्रैक 1 में कम-से-कम एक वीडियो क्लिप अपलोड करें।")
    for clip in video_slots_with_file:
        if clip["end"] <= clip["start"]:
            problems.append(f"❌ '{clip['name']}' में End Second, Start Second से बड़ा नहीं है।")

    for event in st.session_state["sfx_events"]:
        if event["path"] and event["duration"] <= 0:
            problems.append(f"❌ SFX '{event['name']}' का ड्यूरेशन 0 से बड़ा होना चाहिए।")

    if not st.session_state["story_script_text"].strip():
        problems.append("❌ कहानी/स्क्रिप्ट खाली है।")

    return problems


# ================================================================
# 🎬 मुख्य फंक्शन — सारे ट्रैक्स यहीं एक के नीचे एक जुड़ते हैं
# ================================================================
def main():
    _initialize_session_state()
    apply_dark_theme()
    render_header()

    # Playwright स्टेटस चेक (set_page_config के बाद, इसलिए safe)
    playwright_ok, playwright_error = _ensure_playwright_chromium_installed()
    if playwright_error and not playwright_ok:
        st.warning(f"⚠️ Playwright Chromium समस्या: {playwright_error}")

    # --- ३ बिल्कुल स्वतंत्र ट्रैक्स — एक के नीचे एक, कोई tabs नहीं ---
    render_video_track()
    st.divider()
    render_music_track()
    st.divider()
    render_sfx_track()
    st.divider()
    custom_audio_file = render_story_section()
    st.divider()
    is_long_format, duration_seconds = render_settings_section()
    st.divider()

    # --- सारे इनपुट्स को एक जगह इकट्ठा करना ---
    subtitle_color_hex = "#FFD700" if st.session_state["subtitle_color_choice"].startswith("पीला") else "#FFFFFF"
    inputs = {
        "story_script": st.session_state["story_script_text"],
        "ticker_text": st.session_state["ticker_text_value"],
        "aspect_ratio": "16:9" if is_long_format else "9:16",
        "duration_seconds": duration_seconds,
        "quality": "1080p" if st.session_state["quality_choice_value"].startswith("1080p") else "720p",
        "sub_color": subtitle_color_hex,
        "sub_size": st.session_state["subtitle_font_size"],
        "voiceover_mode": "custom" if st.session_state["voiceover_mode"].startswith("🎤") else "ai_tts",
        "custom_audio_path": _save_uploaded_file_to_temp(custom_audio_file) if custom_audio_file else None,
    }

    validation_problems = _validate_timeline()
    if validation_problems:
        with st.expander(f"⚠️ {len(validation_problems)} समस्याएँ मिलीं — पहले ठीक करें", expanded=True):
            for problem in validation_problems:
                st.markdown(f"- {problem}")

    # --- 📺 लाइव प्लेयर पैनल: क्विक ड्राफ्ट रेंडर बटन + प्लेयर (फाइनल बटन के ठीक ऊपर) ---
    st.markdown('<div class="track-heading">📺 लाइव प्लेयर पैनल</div>', unsafe_allow_html=True)

    if st.button("⚡ क्विक ड्राफ्ट रेंडर", key="draft_render_button", disabled=bool(validation_problems)):
        try:
            with st.spinner("⚡ कच्चा प्रीव्यू बन रहा है..."):
                draft_output_path = os.path.join(tempfile.gettempdir(), "draft_preview.mp4")
                draft_inputs = dict(inputs)
                draft_inputs["quality"] = "720p"  # ड्राफ्ट हमेशा कम क्वालिटी में तुरंत बने
                st.session_state["draft_video_path"] = compile_cinematic_video(
                    **_build_engine_kwargs(draft_inputs, draft_output_path)
                )
        except Exception as draft_error:
            st.error(f"❌ ड्राफ्ट बनाते समय त्रुटि: {draft_error}")

    if st.session_state["draft_video_path"] and os.path.exists(st.session_state["draft_video_path"]):
        st.video(st.session_state["draft_video_path"])
    else:
        st.caption("अभी तक कोई ड्राफ्ट प्रीव्यू नहीं बना।")

    # --- 🚀 फाइनल जनरेट बटन (क्विक ड्राफ्ट के ठीक नीचे, बीच में कुछ नहीं) ---
    if st.button("🚀 GENERATE CINEMATIC VIDEO (FINAL)", use_container_width=True,
                 disabled=bool(validation_problems)):
        try:
            with st.spinner("🎥 आपका फाइनल सिनेमैटिक वीडियो बन रहा है..."):
                output_directory = "generated_video"
                os.makedirs(output_directory, exist_ok=True)
                final_output_path = os.path.join(output_directory, "final_cinematic_output.mp4")
                final_video_path = compile_cinematic_video(**_build_engine_kwargs(inputs, final_output_path))
                final_thumbnail_path = _generate_final_thumbnail(final_video_path)
        except Exception as render_error:
            st.error(f"❌ वीडियो बनाते समय त्रुटि आई: {render_error}")
            import traceback
            with st.expander("🔍 पूरी तकनीकी जानकारी (Technical Details) देखें"):
                st.code(traceback.format_exc())
            return

        st.success("✅ आपका सिनेमैटिक वीडियो सफलतापूर्वक तैयार हो गया है!")
        st.video(final_video_path)

        with open(final_video_path, "rb") as video_file:
            video_bytes = video_file.read()
        with open(final_thumbnail_path, "rb") as thumbnail_file:
            thumbnail_bytes = thumbnail_file.read()

        st.download_button(
            "📥 DOWNLOAD YOUR CINEMATIC VIDEO & THUMBNAIL", data=video_bytes,
            file_name="baba_cinematic_video.mp4", mime="video/mp4", use_container_width=True,
        )
        st.download_button(
            "🖼️ थंबनेल डाउनलोड करें", data=thumbnail_bytes,
            file_name="baba_cinematic_thumbnail.jpg", mime="image/jpeg", use_container_width=True,
        )


if __name__ == "__main__":
    main()
