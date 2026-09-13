"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो — ३-ट्रैक ओपन-टाइमलाइन संस्करण (No Tabs)
==============================================================
इस वर्ज़न में पुराना st.tabs वाला मेन्यू-सिस्टम पूरी तरह हटा दिया
गया है। अब सभी ३ ट्रैक्स (विज़ुअल्स, म्यूज़िक, SFX) + कहानी +
सेटिंग्स + लाइव-प्लेयर — सब कुछ स्क्रीन पर एक के नीचे एक, पूरी
तरह खुले हुए (open) दिखते हैं, ताकि यूज़र को कहीं क्लिक करके
टैब बदलने की ज़रूरत न पड़े।

⚠️ ज़रूरी मान्यता (Assumption): यह फाइल मानती है कि engine.py का
compile_cinematic_video() फंक्शन नीचे दिए kwargs
(visual_clips, music_tracks, sfx_events, outro_voice_active आदि)
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
# (moviepy 2.x में "from moviepy import VideoFileClip" चलता है,
#  moviepy 1.x में "from moviepy.editor import VideoFileClip" चाहिए)
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
# 3) डार्क-थीम CSS — पुराना केसरी/सुनहरा लुक पूरी तरह सुरक्षित रखा गया है
# --------------------------------------------------------------
def apply_dark_theme():
    """पुराना डार्क + सुनहरा सिनेमैटिक लुक — बिना किसी बदलाव के।"""
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
    st.markdown('<div class="sub-title">पूरी टाइमलाइन एक ही स्क्रीन पर — कोई टैब नहीं, कोई मेन्यू नहीं</div>', unsafe_allow_html=True)
    st.divider()


# --------------------------------------------------------------
# 4) सारा session_state एक जगह इनिशियलाइज़ — १००% स्टेट प्रिज़र्वेशन
# --------------------------------------------------------------
def _initialize_session_state():
    """
    यह फंक्शन हर rerun पर चलता है, लेकिन 'if key not in st.session_state'
    की वजह से सिर्फ़ पहली बार ही डिफ़ॉल्ट मान भरता है — इसके बाद यूज़र
    का डेटा कभी रीसेट नहीं होता, चाहे कितनी भी फाइलें अपलोड हों या
    बटन दबें।
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

        # --- ट्रैक 1: विज़ुअल्स (फोटो + वीडियो एक ही लिस्ट में) ---
        "visual_clips": [],
        "visual_uploader_key": 0,

        # --- ट्रैक 2: म्यूज़िक ---
        "music_tracks": [],
        "music_uploader_key": 0,
        "master_music_volume": 0.8,

        # --- ट्रैक 3: SFX ---
        "sfx_files": [],
        "sfx_events": [],
        "sfx_uploader_key": 0,
        "sfx_search_results": [],

        # --- लाइव ड्राफ्ट प्लेयर ---
        "draft_video_path": None,
    }
    for key, default_value in default_values.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


# --------------------------------------------------------------
# 5) छोटा हेल्पर — अपलोड की गई फाइल को डिस्क पर सेव करना
# --------------------------------------------------------------
def _save_uploaded_file_to_temp(uploaded_file):
    """Streamlit UploadedFile को अस्थायी डिस्क-फाइल में बदलता है (moviepy को असली पाथ चाहिए)।"""
    file_extension = os.path.splitext(uploaded_file.name)[1]
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
    temp_file.write(uploaded_file.getvalue())
    temp_file.close()
    return temp_file.name


def _probe_video_duration_and_thumbnail(video_path, uploaded_name):
    """
    वीडियो की असली लंबाई पढ़ता है (ताकि Start/End का डिफ़ॉल्ट सही मिले)
    और बीच का एक फ्रेम थंबनेल के तौर पर सेव करता है। कोई भी दिक्कत आए
    तो चुपचाप डिफ़ॉल्ट मान लौटा देता है — ऐप कभी क्रैश नहीं होता।
    """
    default_duration = 5.0
    thumbnail_path = None
    try:
        with VideoFileClip(video_path) as clip:
            actual_duration = clip.duration or default_duration
            safe_default_end = min(default_duration, actual_duration)
            thumbnail_path = os.path.join(tempfile.gettempdir(), f"thumb_{uploaded_name}.jpg")
            clip.save_frame(thumbnail_path, t=min(0.5, actual_duration / 2))
            return safe_default_end, thumbnail_path
    except Exception:
        return default_duration, thumbnail_path


# ================================================================
# 🎬 ट्रैक 1 — विज़ुअल्स (फोटो + वीडियो एक ही डिब्बे में)
# ================================================================
def render_visuals_track():
    st.markdown('<div class="track-heading">🎬 ट्रैक 1: विज़ुअल्स (फोटो / वीडियो क्लिप्स)</div>', unsafe_allow_html=True)
    st.caption("तस्वीरें और वीडियो क्लिप्स — दोनों एक ही डिब्बे में एक साथ अपलोड करें।")

    pending_visuals = st.file_uploader(
        "फोटो/वीडियो अपलोड करें (PNG, JPG, MP4, MOV)",
        type=["png", "jpg", "jpeg", "mp4", "mov"],
        accept_multiple_files=True,
        key=f"visual_uploader_{st.session_state['visual_uploader_key']}",
    )

    if st.button("➕ विज़ुअल क्लिप जोड़ें", key="add_visual_button"):
        existing_names = {c["name"] for c in st.session_state["visual_clips"]}
        added_count = 0
        for uploaded_file in (pending_visuals or []):
            if uploaded_file.name in existing_names:
                continue  # डुप्लीकेट फाइल दोबारा न जोड़ें

            file_extension = os.path.splitext(uploaded_file.name)[1].lower()
            is_image = file_extension in (".png", ".jpg", ".jpeg")
            saved_path = _save_uploaded_file_to_temp(uploaded_file)

            new_order = len(st.session_state["visual_clips"]) + 1

            if is_image:
                # --- फोटो: Start/End बॉक्स की ज़रूरत नहीं, फिक्स ५ सेकंड ---
                st.session_state["visual_clips"].append({
                    "name": uploaded_file.name, "path": saved_path, "is_image": True,
                    "order": new_order, "start": 0.0, "end": 5.0, "thumbnail": saved_path,
                })
            else:
                # --- वीडियो: असली लंबाई पढ़कर Start/End ट्रिमर एक्टिवेट करना ---
                default_end, thumb = _probe_video_duration_and_thumbnail(saved_path, uploaded_file.name)
                st.session_state["visual_clips"].append({
                    "name": uploaded_file.name, "path": saved_path, "is_image": False,
                    "order": new_order, "start": 0.0, "end": default_end, "thumbnail": thumb,
                })
            added_count += 1

        if added_count > 0:
            st.session_state["visual_uploader_key"] += 1  # अपलोडर रीसेट, लेकिन डेटा सुरक्षित
            st.rerun()
        else:
            st.warning("⚠️ कोई नई फाइल नहीं मिली (या पहले से जोड़ी जा चुकी है)।")

    if not st.session_state["visual_clips"]:
        st.info("अभी तक कोई विज़ुअल क्लिप नहीं जोड़ी गई।")
        return

    st.markdown('<div class="section-heading">📽️ लाइव टाइमलाइन (क्रम बदलने के लिए ड्रॉपडाउन इस्तेमाल करें)</div>', unsafe_allow_html=True)

    total_clips = len(st.session_state["visual_clips"])
    sorted_clips = sorted(st.session_state["visual_clips"], key=lambda c: c["order"])

    for position_index, clip in enumerate(sorted_clips):
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            thumb_col, order_col, trim_col, remove_col = st.columns([1.4, 1, 2, 0.6])

            with thumb_col:
                clip_icon = "🖼️" if clip["is_image"] else "🎞️"
                st.markdown(f'<span class="order-badge">{clip_icon} {clip["name"][:22]}</span>', unsafe_allow_html=True)
                if clip["thumbnail"]:
                    st.image(clip["thumbnail"], use_container_width=True)
                else:
                    st.caption("थंबनेल उपलब्ध नहीं")

            with order_col:
                unique_key = f"vorder_{clip['name']}_{position_index}"

                def _on_order_change(target_clip=clip, widget_key=unique_key):
                    target_clip["order"] = st.session_state[widget_key]

                st.selectbox(
                    "क्रम संख्या", options=list(range(1, total_clips + 1)),
                    index=min(clip["order"], total_clips) - 1,
                    key=unique_key, on_change=_on_order_change,
                )

            with trim_col:
                if clip["is_image"]:
                    # फोटो के लिए Start/End बॉक्स छुपाए गए हैं
                    st.caption("🖼️ फोटो — डिफ़ॉल्ट ड्यूरेशन: 5 सेकंड (फिक्स)")
                else:
                    start_col, end_col = st.columns(2)
                    start_key = f"vstart_{clip['name']}_{position_index}"
                    end_key = f"vend_{clip['name']}_{position_index}"

                    with start_col:
                        def _on_start_change(target_clip=clip, widget_key=start_key):
                            target_clip["start"] = st.session_state[widget_key]
                        st.number_input("Start Second", min_value=0.0, value=clip["start"], step=0.5,
                                         key=start_key, on_change=_on_start_change)
                    with end_col:
                        def _on_end_change(target_clip=clip, widget_key=end_key):
                            target_clip["end"] = st.session_state[widget_key]
                        st.number_input("End Second", min_value=0.5, value=clip["end"], step=0.5,
                                         key=end_key, on_change=_on_end_change)

            with remove_col:
                st.write("")
                if st.button("❌", key=f"remove_visual_{position_index}"):
                    st.session_state["visual_clips"].remove(clip)
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)


# ================================================================
# 🎵 ट्रैक 2 — बैकग्राउंड म्यूज़िक
# ================================================================
def render_music_track():
    st.markdown('<div class="track-heading">🎵 ट्रैक 2: बैकग्राउंड म्यूज़िक ट्रैक</div>', unsafe_allow_html=True)
    st.caption("एक या कई भजन/संगीत फाइलें अपलोड करें। एक से ज़्यादा हों तो हर एक को अलग-अलग समय पर सिंक कर सकते हैं।")

    pending_music = st.file_uploader(
        "भजन / संगीत अपलोड करें (MP3, MP4, WAV, M4A)",
        type=["mp3", "mp4", "wav", "m4a"], accept_multiple_files=True,
        key=f"music_uploader_{st.session_state['music_uploader_key']}",
    )

    if st.button("➕ म्यूज़िक ट्रैक जोड़ें", key="add_music_button"):
        existing_names = {m["name"] for m in st.session_state["music_tracks"]}
        added_count = 0
        for uploaded_file in (pending_music or []):
            if uploaded_file.name in existing_names:
                continue
            saved_path = _save_uploaded_file_to_temp(uploaded_file)
            st.session_state["music_tracks"].append({
                "name": uploaded_file.name, "path": saved_path,
                "order": len(st.session_state["music_tracks"]) + 1,
                "instrumental_only": False, "volume": 0.8,
                "start": 0.0, "end": 0.0,  # end = 0.0 का मतलब है "पूरा ट्रैक" (Full Mode)
            })
            added_count += 1

        if added_count > 0:
            st.session_state["music_uploader_key"] += 1
            st.rerun()
        else:
            st.warning("⚠️ कोई नई फाइल नहीं मिली (या पहले से जोड़ी जा चुकी है)।")

    if not st.session_state["music_tracks"]:
        st.caption("ℹ️ कोई भजन नहीं जोड़ा गया — डिफ़ॉल्ट बैकग्राउंड सितार-संगीत इस्तेमाल होगा।")
        return

    tracks_sorted = sorted(st.session_state["music_tracks"], key=lambda t: t["order"])
    is_multi_track_mode = len(tracks_sorted) > 1
    total_tracks = len(tracks_sorted)

    for position_index, track in enumerate(tracks_sorted):
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            name_col, order_col, trim_col, toggle_col, volume_col, remove_col = st.columns(
                [1.6, 0.9, 1.6, 1.3, 1.3, 0.5]
            )

            with name_col:
                st.markdown(f'<span class="music-badge">🎶 {track["name"][:20]}</span>', unsafe_allow_html=True)
                if not is_multi_track_mode:
                    st.caption("🔁 Full Mode (पूरा ट्रैक चलेगा)")

            with order_col:
                order_key = f"morder_{track['name']}_{position_index}"

                def _on_music_order_change(target_track=track, widget_key=order_key):
                    target_track["order"] = st.session_state[widget_key]

                st.selectbox("क्रम", options=list(range(1, total_tracks + 1)),
                             index=min(track["order"], total_tracks) - 1,
                             key=order_key, on_change=_on_music_order_change)

            with trim_col:
                if is_multi_track_mode:
                    # एक से ज़्यादा ट्रैक होने पर ही Start/End ट्रिमर एक्टिवेट होता है
                    start_key = f"mstart_{track['name']}_{position_index}"
                    end_key = f"mend_{track['name']}_{position_index}"
                    sc1, sc2 = st.columns(2)
                    with sc1:
                        def _on_m_start(target_track=track, widget_key=start_key):
                            target_track["start"] = st.session_state[widget_key]
                        st.number_input("Start Sec", min_value=0.0, value=track["start"], step=1.0,
                                         key=start_key, on_change=_on_m_start)
                    with sc2:
                        def _on_m_end(target_track=track, widget_key=end_key):
                            target_track["end"] = st.session_state[widget_key]
                        st.number_input("End Sec (0=पूरा)", min_value=0.0, value=track["end"], step=1.0,
                                         key=end_key, on_change=_on_m_end)
                else:
                    st.caption("—")

            with toggle_col:
                toggle_key = f"minstr_{track['name']}_{position_index}"

                def _on_instrumental_change(target_track=track, widget_key=toggle_key):
                    target_track["instrumental_only"] = st.session_state[widget_key]

                st.toggle("केवल इंस्ट्रूमेंटल (Vocal Remover)", value=track["instrumental_only"],
                          key=toggle_key, on_change=_on_instrumental_change)

            with volume_col:
                volume_key = f"mvol_{track['name']}_{position_index}"

                def _on_volume_change(target_track=track, widget_key=volume_key):
                    target_track["volume"] = st.session_state[widget_key]

                st.slider("ट्रैक वॉल्यूम", 0.0, 1.0, value=track["volume"], step=0.05,
                          key=volume_key, on_change=_on_volume_change)

            with remove_col:
                st.write("")
                if st.button("❌", key=f"remove_music_{position_index}"):
                    st.session_state["music_tracks"].remove(track)
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-heading">🎛️ मुख्य संगीत वॉल्यूम (पूरे वीडियो के लिए ग्लोबल)</div>', unsafe_allow_html=True)
    st.slider("मुख्य संगीत वॉल्यूम", 0.0, 1.0, key="master_music_volume", label_visibility="collapsed")


# ================================================================
# 🔊 ट्रैक 3 — SFX ध्वनि प्रभाव
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
    st.markdown('<div class="track-heading">🔊 ट्रैक 3: SFX ध्वनि प्रभाव</div>', unsafe_allow_html=True)
    st.caption("कस्टम ध्वनि अपलोड करें या इंटरनेट पर खोजें, फिर सटीक सेकंड पर इवेंट जोड़ें।")

    pending_sfx = st.file_uploader(
        "SFX ध्वनि-फाइलें अपलोड करें (MP3, WAV)", type=["mp3", "wav"], accept_multiple_files=True,
        key=f"sfx_uploader_{st.session_state['sfx_uploader_key']}",
    )
    if st.button("➕ SFX ध्वनि जोड़ें", key="add_sfx_file_button"):
        existing_names = {f["name"] for f in st.session_state["sfx_files"]}
        added_count = 0
        for uploaded_file in (pending_sfx or []):
            if uploaded_file.name in existing_names:
                continue
            saved_path = _save_uploaded_file_to_temp(uploaded_file)
            st.session_state["sfx_files"].append({"name": uploaded_file.name, "path": saved_path})
            added_count += 1
        if added_count > 0:
            st.session_state["sfx_uploader_key"] += 1
            st.rerun()
        else:
            st.warning("⚠️ कोई नई ध्वनि-फाइल नहीं मिली।")

    st.markdown('<div class="section-heading">🌐 इंटरनेट साउंड सर्च (Freesound)</div>', unsafe_allow_html=True)
    search_col1, search_col2 = st.columns([3, 1])
    with search_col1:
        search_query = st.text_input("ध्वनि खोजें", key="sfx_search_query", label_visibility="collapsed",
                                       placeholder="जैसे: शंखनाद, घंटी, डमरू...")
    with search_col2:
        if st.button("🔍 खोजें", key="sfx_search_button"):
            st.session_state["sfx_search_results"] = _search_freesound(search_query)

    if st.session_state["sfx_search_results"]:
        st.caption("खोज परिणाम (डाउनलोड के लिए Freesound पर जाकर फाइल यहाँ अपलोड करें):")
        for result in st.session_state["sfx_search_results"][:5]:
            st.markdown(f"🔉 {result.get('name', 'अज्ञात ध्वनि')}")

    st.markdown('<div class="section-heading">🎯 SFX टाइम-इवेंट्स</div>', unsafe_allow_html=True)

    for position_index, event in enumerate(st.session_state["sfx_events"]):
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            name_col, start_col, end_col, vol_col, remove_col = st.columns([1.6, 1.2, 1.2, 1.4, 0.6])

            with name_col:
                st.markdown(f'<span class="sfx-badge">🎯 {event["sfx_name"][:18]}</span>', unsafe_allow_html=True)

            with start_col:
                start_key = f"sfxstart_{position_index}"

                def _on_sfx_start_change(target_event=event, widget_key=start_key):
                    target_event["start"] = st.session_state[widget_key]

                st.number_input("Start Time", min_value=0.0, value=event["start"], step=0.5,
                                 key=start_key, on_change=_on_sfx_start_change)

            with end_col:
                end_key = f"sfxend_{position_index}"

                def _on_sfx_end_change(target_event=event, widget_key=end_key):
                    target_event["end"] = st.session_state[widget_key]

                st.number_input("End Time", min_value=0.5, value=event["end"], step=0.5,
                                 key=end_key, on_change=_on_sfx_end_change)

            with vol_col:
                vol_key = f"sfxvol_{position_index}"

                def _on_sfx_vol_change(target_event=event, widget_key=vol_key):
                    target_event["volume"] = st.session_state[widget_key]

                st.slider("वॉल्यूम", 0.0, 1.0, value=event["volume"], step=0.05,
                          key=vol_key, on_change=_on_sfx_vol_change)

            with remove_col:
                st.write("")
                if st.button("❌", key=f"remove_sfxevent_{position_index}"):
                    st.session_state["sfx_events"].pop(position_index)
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

    # --- नया SFX-इवेंट जोड़ने का फॉर्म ---
    available_sfx_names = [f["name"] for f in st.session_state["sfx_files"]] or [
        "शंखनाद 🐚", "डमरू बीट्स 🥁", "चिड़ियों की चहचहाहट 🐦"
    ]
    st.markdown("**➕ नया SFX-इवेंट जोड़ें**")
    a1, a2, a3, a4, a5 = st.columns([2, 1, 1, 1.2, 0.8])
    with a1:
        new_sfx_name = st.selectbox("ध्वनि चुनें", options=available_sfx_names, key="new_sfx_name")
    with a2:
        new_sfx_start = st.number_input("Start Time", min_value=0.0, step=0.5, key="new_sfx_start")
    with a3:
        new_sfx_end = st.number_input("End Time", min_value=0.5, step=0.5, value=2.0, key="new_sfx_end")
    with a4:
        new_sfx_volume = st.slider("वॉल्यूम", 0.0, 1.0, value=0.7, step=0.05, key="new_sfx_volume")
    with a5:
        st.write("")
        if st.button("➕", key="add_sfx_event_button"):
            st.session_state["sfx_events"].append({
                "sfx_name": new_sfx_name, "start": new_sfx_start,
                "end": new_sfx_end, "volume": new_sfx_volume,
            })
            st.rerun()


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
# हेल्पर्स — फाइनल रेंडर के लिए kwargs और थंबनेल
# ================================================================
def _generate_final_thumbnail(video_path):
    thumbnail_path = os.path.join(tempfile.gettempdir(), "cinematic_thumbnail.jpg")
    with VideoFileClip(video_path) as clip:
        clip.save_frame(thumbnail_path, t=clip.duration / 2)
    return thumbnail_path


def _build_engine_kwargs(inputs, output_path):
    """
    session_state में रखे visual_clips/music_tracks/sfx_events को
    सीधे engine.py के अपेक्षित फॉर्मेट में बदलकर kwargs dictionary
    बनाता है।
    """
    resolved_visual_clips = [
        {"path": c["path"], "is_image": c["is_image"], "order": c["order"],
         "start": c["start"], "end": c["end"]}
        for c in sorted(st.session_state["visual_clips"], key=lambda c: c["order"])
    ]
    resolved_music_tracks = [
        {"path": m["path"], "instrumental_only": m["instrumental_only"],
         "volume": m["volume"], "start": m["start"], "end": m["end"]}
        for m in sorted(st.session_state["music_tracks"], key=lambda m: m["order"])
    ]
    sfx_name_to_path = {f["name"]: f["path"] for f in st.session_state["sfx_files"]}
    resolved_sfx_events = [
        {"path": sfx_name_to_path.get(e["sfx_name"]), "sfx_name": e["sfx_name"],
         "start": e["start"], "end": e["end"], "volume": e["volume"]}
        for e in st.session_state["sfx_events"]
    ]

    return dict(
        visual_clips=resolved_visual_clips,
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
    if not st.session_state["visual_clips"]:
        problems.append("❌ कम-से-कम एक फोटो/वीडियो विज़ुअल-क्लिप जोड़ें।")
    for clip in st.session_state["visual_clips"]:
        if not clip["is_image"] and clip["end"] <= clip["start"]:
            problems.append(f"❌ '{clip['name']}' में End Second, Start Second से बड़ा नहीं है।")
    for event in st.session_state["sfx_events"]:
        if event["end"] <= event["start"]:
            problems.append(f"❌ SFX '{event['sfx_name']}' का End Time, Start Time से बड़ा नहीं है।")
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

    # --- सभी ट्रैक्स और सेक्शन — कोई tabs नहीं, सब कुछ खुला हुआ ---
    render_visuals_track()
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

    # --- 📺 लाइव प्लेयर पैनल: क्विक ड्राफ्ट रेंडर बटन + प्लेयर ---
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

    st.divider()

    # --- 🚀 फाइनल जनरेट बटन ---
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
