"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो — ३-ट्रैक नॉन-लीनियर एडिटर (Pro Edition)
==============================================================
इस वर्ज़न में तीन स्वतंत्र ट्रैक्स (लेयर्स) हैं:
  🎬 विज़ुअल ट्रैक   — फोटो/वीडियो, क्रम + Start/End (वीडियो पर ही)
  🎵 म्यूज़िक ट्रैक   — भजन, क्रम, इंस्ट्रूमेंटल-टॉगल, वॉल्यूम, मास्टर-वॉल्यूम
  🔊 SFX ट्रैक      — कस्टम ध्वनि अपलोड + ग्लोबल-सर्च हुक + टाइम-इवेंट्स

⚠️ दो ईमानदार तकनीकी सीमाएँ (कृपया चैट में ऊपर का नोट भी पढ़ें):
  - "लाइव ड्राफ्ट प्रीव्यू" असल में एक अलग "⚡ क्विक ड्राफ्ट रेंडर" बटन है,
    जो कम क्वालिटी में वाकई रेंडर करके दिखाता है — टाइप करते ही अपने-आप
    बदलने वाला जादुई प्रीव्यू तकनीकी रूप से संभव नहीं है (MoviePy को
    रेंडर तो करना ही पड़ेगा)।
  - ग्लोबल साउंड-सर्च के लिए Freesound API-key चाहिए (st.secrets में डालें),
    बिना key के सिर्फ़ एक चेतावनी दिखेगी, क्रैश नहीं होगा।
==============================================================
"""

import os
import subprocess
import tempfile

import streamlit as st

# --------------------------------------------------------------
# 1) पेज की बुनियादी सेटिंग
# --------------------------------------------------------------
st.set_page_config(
    page_title="बाबा जनरेटिव वेब स्टूडियो",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

from moviepy import VideoFileClip
from engine import compile_cinematic_video

# --------------------------------------------------------------
# 1.1) PDF/DOCX-टेक्स्ट-एक्सट्रैक्शन लाइब्रेरी सुरक्षित तरीके से इम्पोर्ट करना
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

# --------------------------------------------------------------
# 1.2) ग्लोबल साउंड-सर्च (Freesound API) — वैकल्पिक, key न हो तो चुप
# --------------------------------------------------------------
try:
    import requests
    REQUESTS_AVAILABLE = True
except Exception:
    REQUESTS_AVAILABLE = False


# --------------------------------------------------------------
# 1.3) Playwright का Chromium ब्राउज़र इंस्टॉल करना — सिर्फ़ एक बार
# --------------------------------------------------------------
@st.cache_resource
def _ensure_playwright_chromium_installed():
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
# 2) डार्क-थीम + टाइमलाइन-कार्ड स्टाइलिंग (पुराना केसरी-डार्क लुक बरकरार)
# --------------------------------------------------------------
def apply_dark_theme():
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(160deg, #0d0d0d 0%, #1a1a2e 100%);
            color: #f5f5f5;
        }
        .main-title {
            text-align: center; font-size: 42px; font-weight: 800;
            background: -webkit-linear-gradient(45deg, #ffd700, #ff8c00);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: 0px;
        }
        .sub-title { text-align: center; color: #b0b0b0; font-size: 16px; margin-bottom: 20px; }
        .track-heading {
            color: #ffd700; font-size: 24px; font-weight: 800;
            margin-top: 10px; margin-bottom: 10px;
            border-bottom: 2px solid rgba(255,215,0,0.3); padding-bottom: 6px;
        }
        .section-heading { color: #ffd700; font-size: 18px; font-weight: 700; margin-top: 15px; margin-bottom: 8px; }
        .timeline-card {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,215,0,0.25);
            border-radius: 12px; padding: 14px; margin-bottom: 14px;
        }
        .order-badge {
            background: linear-gradient(90deg, #ffd700, #ff8c00);
            color: #0d0d0d; font-weight: 800; border-radius: 8px;
            padding: 4px 10px; display: inline-block; margin-bottom: 6px; font-size: 13px;
        }
        .sfx-badge {
            background: linear-gradient(90deg, #8e2de2, #4a00e0);
            color: #fff; font-weight: 700; border-radius: 8px;
            padding: 3px 9px; display: inline-block; font-size: 12px;
        }
        .music-badge {
            background: linear-gradient(90deg, #ff8c00, #ff416c);
            color: #fff; font-weight: 700; border-radius: 8px;
            padding: 3px 9px; display: inline-block; font-size: 12px;
        }
        div.stButton > button:first-child {
            background: linear-gradient(90deg, #ff416c, #ff4b2b); color: white;
            font-size: 18px; font-weight: 800; padding: 12px 0px; border-radius: 12px;
            border: none; width: 100%; box-shadow: 0px 0px 20px rgba(255, 75, 43, 0.6); transition: 0.3s;
        }
        div.stButton > button:first-child:hover { transform: scale(1.02); box-shadow: 0px 0px 30px rgba(255, 75, 43, 0.9); }
        div.stDownloadButton > button:first-child {
            background: linear-gradient(90deg, #11998e, #38ef7d); color: #0d0d0d;
            font-size: 20px; font-weight: 800; padding: 15px 0px; border-radius: 12px;
            border: none; width: 100%; box-shadow: 0px 0px 20px rgba(56, 239, 125, 0.6); transition: 0.3s;
        }
        div.stDownloadButton > button:first-child:hover { transform: scale(1.02); box-shadow: 0px 0px 30px rgba(56, 239, 125, 0.9); }
        </style>
        """,
        unsafe_allow_html=True
    )


def render_header():
    st.markdown('<div class="main-title">🎬 बाबा जनरेटिव वेब स्टूडियो</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">३-ट्रैक प्रो टाइमलाइन एडिटर — विज़ुअल + म्यूज़िक + SFX</div>', unsafe_allow_html=True)
    st.divider()


# --------------------------------------------------------------
# 2.1) विस्तृत यूज़र गाइड (एक्सपैंडर बॉक्स)
# --------------------------------------------------------------
def render_user_guide():
    with st.expander("🦚 बाबा स्टूडियो यूज़र गाइड (User Guide)", expanded=False):
        st.markdown(
            """
            **🎬 विज़ुअल ट्रैक:** फोटो/वीडियो अपलोड करें, "+ क्लिप जोड़ें" दबाएँ, फिर
            हर क्लिप का क्रम-नंबर चुनें। फोटो हमेशा ५ सेकंड चलेगी (Ken Burns ज़ूम के साथ);
            वीडियो पर आप Start/End Second से ट्रिम कर सकते हैं।

            **🎵 म्यूज़िक ट्रैक:** भजन/संगीत अपलोड करें, "+ म्यूज़िक ट्रैक जोड़ें" दबाएँ।
            सिर्फ़ १ भजन हो तो वह पूरा (Full Mode) बजेगा; एक से ज़्यादा हों तो हर एक का
            Start/End तय करें। हर भजन पर अलग वॉल्यूम + "केवल इंस्ट्रूमेंटल" टॉगल है, और
            नीचे एक मास्टर-वॉल्यूम स्लाइडर पूरे संगीत को नियंत्रित करता है।

            **🔊 SFX ट्रैक:** अपनी ध्वनियाँ (शंख, डमरू, चिड़ियाँ) अपलोड करें, या ग्लोबल-सर्च
            बॉक्स से मुफ़्त ध्वनि खोजें। फिर "+ SFX ध्वनि जोड़ें" से तय करें कि वह ध्वनि किस
            Start Time से किस End Time तक और कितनी आवाज़ में बजेगी।

            **📄 कथा PDF/Word से निकालना:** कहानी बॉक्स के ऊपर PDF या DOCX अपलोड करें —
            टेक्स्ट अपने-आप कहानी बॉक्स में भर जाएगा, और वही टेक्स्ट डिफ़ॉल्ट रूप से नीचे
            "आउट्रो कमेंट" में भी सिंक हो जाएगा (चाहें तो बदल सकते हैं)।

            **⚡ ड्राफ्ट प्रीव्यू:** फाइनल Generate करने से पहले "क्विक ड्राफ्ट रेंडर" बटन से
            एक जल्दी, कम-क्वालिटी वाला प्रीव्यू देख सकते हैं।
            """
        )


# --------------------------------------------------------------
# 3) session_state की शुरुआत — सब कुछ यहीं लॉक रहता है
# --------------------------------------------------------------
def _initialize_session_state():
    default_values = {
        "story_script_text": "",
        "ticker_text_value": "",
        "ticker_manually_edited": False,   # ताकि auto-sync यूज़र के मैनुअल बदलाव को न मिटाए
        "video_format_choice": "📱 9:16 Shorts (कहानी के अनुसार)",
        "duration_choice_value": "5 मिनट",
        "custom_duration_minutes": 10,
        "quality_choice_value": "720p HD",
        "subtitle_color_choice": "पीला (Gold)",
        "subtitle_font_size": 65,
        "voiceover_mode": "🕉️ बाबा एआई दिव्य आवाज़ (Edge-TTS)",
        "last_pdf_name": None,

        # --- ट्रैक-लिस्ट्स (हर एंट्री खुद अपनी पूरी सेटिंग रखती है) ---
        "visual_clips": [],   # [{"file", "order", "is_image", "start", "end"}]
        "music_tracks": [],   # [{"file", "order", "instrumental_only", "volume"}]
        "sfx_files": [],      # यूज़र-अपलोड की गई कस्टम SFX फाइलें [UploadedFile,...]
        "sfx_events": [],     # [{"sfx_name", "start", "end", "volume"}]
        "master_music_volume": 0.8,

        # --- अपलोडर विजेट्स को रीसेट करने के लिए काउंटर (key बदलने हेतु) ---
        "visual_uploader_key": 0,
        "music_uploader_key": 0,
        "sfx_uploader_key": 0,

        "draft_video_path": None,   # क्विक-ड्राफ्ट का आउटपुट पाथ
    }
    for key, default_value in default_values.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


# --------------------------------------------------------------
# 4) 🎬 विज़ुअल ट्रैक
# --------------------------------------------------------------
def render_visual_track():
    st.markdown('<div class="track-heading">🎬 विज़ुअल ट्रैक (फोटो/वीडियो लेयर)</div>', unsafe_allow_html=True)

    pending_files = st.file_uploader(
        label="फोटो (PNG/JPG) या वीडियो (MP4) अपलोड करें",
        type=["jpg", "jpeg", "png", "mp4", "mov"],
        accept_multiple_files=True,
        key=f"visual_uploader_{st.session_state['visual_uploader_key']}",
    )

    if st.button("➕ क्लिप जोड़ें", key="add_visual_clip_button"):
        existing_names = {clip["file"].name for clip in st.session_state["visual_clips"]}
        newly_added_count = 0
        for pending_file in (pending_files or []):
            if pending_file.name not in existing_names:
                is_image_file = pending_file.type and pending_file.type.startswith("image")
                st.session_state["visual_clips"].append({
                    "file": pending_file,
                    "order": len(st.session_state["visual_clips"]) + 1,
                    "is_image": is_image_file,
                    "start": 0.0,
                    "end": 5.0,   # फोटो के लिए यही डिफ़ॉल्ट/फिक्स रहेगा
                })
                newly_added_count += 1
        if newly_added_count > 0:
            st.session_state["visual_uploader_key"] += 1   # अपलोडर खाली करना ताकि अगला बैच जोड़ा जा सके
            st.rerun()
        else:
            st.warning("⚠️ कोई नई फाइल नहीं मिली — पहले ऊपर से फाइलें चुनें।")

    if not st.session_state["visual_clips"]:
        st.info("अभी तक कोई क्लिप नहीं जोड़ी गई।")
        return []

    sorted_clips = sorted(st.session_state["visual_clips"], key=lambda c: c["order"])
    total_clips = len(sorted_clips)

    for clip_index, clip in enumerate(sorted_clips):
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            preview_col, order_col, time_col, remove_col = st.columns([2, 1, 2, 0.7])

            with preview_col:
                st.markdown(f'<span class="order-badge">🎬 {clip["file"].name[:20]}</span>', unsafe_allow_html=True)
                if clip["is_image"]:
                    st.image(clip["file"], use_container_width=True)
                else:
                    st.markdown("🎞️ *(वीडियो क्लिप)*")

            with order_col:
                def _on_order_change(target_clip=clip, widget_key=f"vorder_{clip['file'].name}_{clip_index}"):
                    target_clip["order"] = st.session_state[widget_key]

                st.selectbox(
                    "क्रम", options=list(range(1, total_clips + 1)),
                    index=clip["order"] - 1,
                    key=f"vorder_{clip['file'].name}_{clip_index}", on_change=_on_order_change,
                )

            with time_col:
                # ⚠️ फोटो पर Start/End बॉक्स छुपे रहते हैं — फिक्स ५ सेकंड डिफ़ॉल्ट
                if clip["is_image"]:
                    st.caption("🖼️ फोटो — डिफ़ॉल्ट ५ सेकंड (Ken Burns ज़ूम)")
                else:
                    start_col, end_col = st.columns(2)
                    with start_col:
                        def _on_start_change(target_clip=clip, widget_key=f"vstart_{clip['file'].name}_{clip_index}"):
                            target_clip["start"] = st.session_state[widget_key]
                        st.number_input("Start Sec", min_value=0.0, value=clip["start"], step=0.5,
                                         key=f"vstart_{clip['file'].name}_{clip_index}", on_change=_on_start_change)
                    with end_col:
                        def _on_end_change(target_clip=clip, widget_key=f"vend_{clip['file'].name}_{clip_index}"):
                            target_clip["end"] = st.session_state[widget_key]
                        st.number_input("End Sec", min_value=0.5, value=clip["end"], step=0.5,
                                         key=f"vend_{clip['file'].name}_{clip_index}", on_change=_on_end_change)

            with remove_col:
                st.write("")
                if st.button("❌", key=f"remove_visual_{clip_index}"):
                    st.session_state["visual_clips"].remove(clip)
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

    all_orders = [c["order"] for c in sorted_clips]
    if len(set(all_orders)) != len(all_orders):
        st.warning("⚠️ दो या अधिक क्लिप्स को एक ही क्रम-संख्या मिली है।")

    return sorted(sorted_clips, key=lambda c: c["order"])


# --------------------------------------------------------------
# 5) 🎵 म्यूज़िक ट्रैक
# --------------------------------------------------------------
def render_music_track():
    st.markdown('<div class="track-heading">🎵 म्यूज़िक ट्रैक (बैकग्राउंड भजन लेयर)</div>', unsafe_allow_html=True)

    pending_music_files = st.file_uploader(
        label="भजन / संगीत फाइलें अपलोड करें (MP3/MP4/WAV)",
        type=["mp3", "mp4", "wav", "m4a"],
        accept_multiple_files=True,
        key=f"music_uploader_{st.session_state['music_uploader_key']}",
    )

    if st.button("➕ म्यूज़िक ट्रैक जोड़ें", key="add_music_track_button"):
        existing_names = {track["file"].name for track in st.session_state["music_tracks"]}
        newly_added_count = 0
        for pending_file in (pending_music_files or []):
            if pending_file.name not in existing_names:
                st.session_state["music_tracks"].append({
                    "file": pending_file,
                    "order": len(st.session_state["music_tracks"]) + 1,
                    "instrumental_only": False,
                    "volume": 0.8,
                    "start": 0.0,
                    "end": 0.0,   # 0.0 = "Full Mode" (पूरा गाना)
                })
                newly_added_count += 1
        if newly_added_count > 0:
            st.session_state["music_uploader_key"] += 1
            st.rerun()
        else:
            st.warning("⚠️ कोई नई फाइल नहीं मिली — पहले ऊपर से फाइलें चुनें।")

    if not st.session_state["music_tracks"]:
        st.caption("ℹ️ अभी कोई भजन जोड़ा नहीं गया — डिफ़ॉल्ट सितार-संगीत इस्तेमाल होगा।")
        return [], st.session_state["master_music_volume"]

    sorted_tracks = sorted(st.session_state["music_tracks"], key=lambda t: t["order"])
    total_tracks = len(sorted_tracks)
    is_multi_track_mode = total_tracks > 1   # ⚠️ एक से ज़्यादा हों तभी Trimmer एक्टिवेट होगा

    for track_index, track in enumerate(sorted_tracks):
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            name_col, order_col, mode_col, volume_col, remove_col = st.columns([2, 1, 1.6, 1.4, 0.6])

            with name_col:
                st.markdown(f'<span class="music-badge">🎶 {track["file"].name[:20]}</span>', unsafe_allow_html=True)
                if is_multi_track_mode:
                    trim_start_col, trim_end_col = st.columns(2)
                    with trim_start_col:
                        def _on_mstart_change(target_track=track, widget_key=f"mstart_{track['file'].name}_{track_index}"):
                            target_track["start"] = st.session_state[widget_key]
                        st.number_input("Start Sec", min_value=0.0, value=track["start"], step=1.0,
                                         key=f"mstart_{track['file'].name}_{track_index}", on_change=_on_mstart_change)
                    with trim_end_col:
                        def _on_mend_change(target_track=track, widget_key=f"mend_{track['file'].name}_{track_index}"):
                            target_track["end"] = st.session_state[widget_key]
                        st.number_input("End Sec (0=पूरा)", min_value=0.0, value=track["end"], step=1.0,
                                         key=f"mend_{track['file'].name}_{track_index}", on_change=_on_mend_change)
                else:
                    st.caption("🔁 Full Mode (पूरा भजन बजेगा — सिर्फ़ १ ही ट्रैक है)")

            with order_col:
                def _on_morder_change(target_track=track, widget_key=f"morder_{track['file'].name}_{track_index}"):
                    target_track["order"] = st.session_state[widget_key]
                st.selectbox("क्रम", options=list(range(1, total_tracks + 1)), index=track["order"] - 1,
                             key=f"morder_{track['file'].name}_{track_index}", on_change=_on_morder_change)

            with mode_col:
                def _on_instrumental_change(target_track=track, widget_key=f"instr_{track['file'].name}_{track_index}"):
                    target_track["instrumental_only"] = st.session_state[widget_key]
                st.toggle("केवल इंस्ट्रूमेंटल", value=track["instrumental_only"],
                          key=f"instr_{track['file'].name}_{track_index}", on_change=_on_instrumental_change,
                          help="गायक की आवाज़ हटाकर सिर्फ़ बैकग्राउंड-संगीत रखने की कोशिश करेगा")

            with volume_col:
                def _on_mvol_change(target_track=track, widget_key=f"mvol_{track['file'].name}_{track_index}"):
                    target_track["volume"] = st.session_state[widget_key]
                st.slider("वॉल्यूम", min_value=0.0, max_value=1.0, value=track["volume"], step=0.05,
                          key=f"mvol_{track['file'].name}_{track_index}", on_change=_on_mvol_change)

            with remove_col:
                st.write("")
                if st.button("❌", key=f"remove_music_{track_index}"):
                    st.session_state["music_tracks"].remove(track)
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-heading">🎛️ मुख्य संगीत वॉल्यूम (Master Volume)</div>', unsafe_allow_html=True)
    st.slider("मास्टर म्यूज़िक वॉल्यूम", min_value=0.0, max_value=1.0,
              key="master_music_volume")

    return sorted(sorted_tracks, key=lambda t: t["order"]), st.session_state["master_music_volume"]


# --------------------------------------------------------------
# 6) 🔊 SFX ट्रैक — कस्टम अपलोड + ग्लोबल-सर्च + टाइम-इवेंट्स
# --------------------------------------------------------------
def _search_freesound(query_text: str):
    """
    Freesound API से मुफ़्त ध्वनियाँ खोजता है। इसके लिए st.secrets में
    FREESOUND_API_KEY ज़रूरी है। बिना key या बिना 'requests' लाइब्रेरी के
    यह सिर्फ़ एक चेतावनी दिखाकर लौट जाता है — क्रैश नहीं करता।
    """
    if not REQUESTS_AVAILABLE:
        st.warning("⚠️ 'requests' लाइब्रेरी उपलब्ध नहीं है — ग्लोबल-सर्च काम नहीं करेगा।")
        return []
    api_key = st.secrets.get("FREESOUND_API_KEY", None) if hasattr(st, "secrets") else None
    if not api_key:
        st.warning("⚠️ ग्लोबल साउंड-सर्च के लिए Freesound API-key नहीं मिली। कृपया Streamlit Secrets में 'FREESOUND_API_KEY' जोड़ें।")
        return []
    try:
        response = requests.get(
            "https://freesound.org/apiv2/search/text/",
            params={"query": query_text, "token": api_key, "fields": "id,name,previews"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as search_error:
        st.warning(f"⚠️ साउंड-सर्च में समस्या आई: {search_error}")
        return []


def render_sfx_track():
    st.markdown('<div class="track-heading">🔊 SFX ट्रैक (ध्वनि-प्रभाव लेयर)</div>', unsafe_allow_html=True)

    # --- कस्टम SFX फाइल अपलोड ---
    pending_sfx_files = st.file_uploader(
        label="कस्टम ध्वनियाँ अपलोड करें (शंख/डमरू/चिड़ियाँ आदि MP3/WAV)",
        type=["mp3", "wav"],
        accept_multiple_files=True,
        key=f"sfx_uploader_{st.session_state['sfx_uploader_key']}",
    )
    if st.button("➕ SFX फाइल जोड़ें", key="add_sfx_file_button"):
        existing_names = {f.name for f in st.session_state["sfx_files"]}
        newly_added_count = sum(1 for f in (pending_sfx_files or []) if f.name not in existing_names)
        st.session_state["sfx_files"].extend(
            [f for f in (pending_sfx_files or []) if f.name not in existing_names]
        )
        if newly_added_count > 0:
            st.session_state["sfx_uploader_key"] += 1
            st.rerun()
        else:
            st.warning("⚠️ कोई नई ध्वनि-फाइल नहीं मिली।")

    # --- ग्लोबल साउंड-सर्च बॉक्स (Freesound हुक) ---
    st.markdown('<div class="section-heading">🌐 मुफ़्त ध्वनि ग्लोबल-सर्च (Freesound)</div>', unsafe_allow_html=True)
    search_col1, search_col2 = st.columns([3, 1])
    with search_col1:
        sfx_search_query = st.text_input("ध्वनि खोजें (जैसे: temple bell, conch shell)", key="sfx_search_query")
    with search_col2:
        st.write("")
        if st.button("🔍 खोजें", key="sfx_search_button"):
            search_results = _search_freesound(sfx_search_query)
            st.session_state["sfx_search_results"] = search_results

    if st.session_state.get("sfx_search_results"):
        st.caption(f"{len(st.session_state['sfx_search_results'])} ध्वनियाँ मिलीं (इंटीग्रेशन के लिए API-key ज़रूरी)।")
        for sound_result in st.session_state["sfx_search_results"][:5]:
            st.markdown(f"🔉 {sound_result.get('name', 'अज्ञात')}")

    available_sfx_names = [f.name for f in st.session_state["sfx_files"]] or ["शंखनाद 🐚", "डमरू बीट्स 🥁", "चिड़ियों की चहचहाहट 🐦"]

    st.divider()

    # --- मौजूदा SFX-इवेंट्स दिखाना ---
    for event_index, sfx_event in enumerate(st.session_state["sfx_events"]):
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            st.markdown(f'<span class="sfx-badge">🎯 {sfx_event["sfx_name"][:18]}</span>', unsafe_allow_html=True)
            e_col1, e_col2, e_col3, e_col4 = st.columns([1, 1, 1.5, 0.7])
            with e_col1:
                st.markdown(f"**Start: {sfx_event['start']}s**")
            with e_col2:
                st.markdown(f"**End: {sfx_event['end']}s**")
            with e_col3:
                st.markdown(f"🔊 वॉल्यूम: {sfx_event['volume']}")
            with e_col4:
                if st.button("❌", key=f"remove_sfxevent_{event_index}"):
                    st.session_state["sfx_events"].pop(event_index)
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # --- नया SFX-इवेंट जोड़ना ---
    st.markdown("**➕ नया SFX-इवेंट जोड़ें**")
    add_col1, add_col2, add_col3, add_col4, add_col5 = st.columns([2, 1, 1, 1.2, 0.8])
    with add_col1:
        chosen_sfx_name = st.selectbox("कौन सी ध्वनि?", options=available_sfx_names, key="new_sfx_name")
    with add_col2:
        new_sfx_start = st.number_input("Start Time", min_value=0.0, step=0.5, key="new_sfx_start")
    with add_col3:
        new_sfx_end = st.number_input("End Time", min_value=0.5, step=0.5, value=2.0, key="new_sfx_end")
    with add_col4:
        new_sfx_volume = st.slider("वॉल्यूम", min_value=0.0, max_value=1.0, value=0.7, step=0.05, key="new_sfx_volume")
    with add_col5:
        st.write("")
        if st.button("➕", key="add_sfx_event_button"):
            st.session_state["sfx_events"].append({
                "sfx_name": chosen_sfx_name, "start": new_sfx_start,
                "end": new_sfx_end, "volume": new_sfx_volume,
            })
            st.rerun()

    return st.session_state["sfx_files"], st.session_state["sfx_events"]


# --------------------------------------------------------------
# 7) कथा (PDF/DOCX) एक्सट्रैक्टर + आउट्रो-सिंक
# --------------------------------------------------------------
def render_story_extractor_and_sync():
    st.markdown('<div class="section-heading">📂 धार्मिक कथा / ग्रन्थ अपलोड करें (PDF या Word)</div>', unsafe_allow_html=True)

    uploaded_story_file = st.file_uploader(
        label="कथा/ग्रन्थ अपलोड करें (वैकल्पिक)",
        type=["pdf", "docx"],
        key="story_document_uploader",
    )

    if uploaded_story_file is not None and st.session_state.get("last_pdf_name") != uploaded_story_file.name:
        extracted_text = ""
        file_extension = os.path.splitext(uploaded_story_file.name)[1].lower()

        if file_extension == ".pdf":
            if PDF_SUPPORT_AVAILABLE:
                try:
                    pdf_reader = PdfReader(uploaded_story_file)
                    extracted_text = "\n".join((page.extract_text() or "") for page in pdf_reader.pages).strip()
                except Exception as pdf_error:
                    st.warning(f"⚠️ PDF पढ़ने में समस्या: {pdf_error}")
            else:
                st.warning("⚠️ PDF-सपोर्ट के लिए requirements.txt में 'pypdf' जोड़ें।")

        elif file_extension == ".docx":
            if DOCX_SUPPORT_AVAILABLE:
                try:
                    word_document = docx_lib.Document(uploaded_story_file)
                    extracted_text = "\n".join(paragraph.text for paragraph in word_document.paragraphs).strip()
                except Exception as docx_error:
                    st.warning(f"⚠️ Word फाइल पढ़ने में समस्या: {docx_error}")
            else:
                st.warning("⚠️ Word-सपोर्ट के लिए requirements.txt में 'python-docx' जोड़ें।")

        if extracted_text:
            st.session_state["story_script_text"] = extracted_text
            st.session_state["last_pdf_name"] = uploaded_story_file.name
            # ⚠️ कहानी → आउट्रो ऑटो-सिंक: सिर्फ़ तभी, जब यूज़र ने आउट्रो को मैनुअली न बदला हो
            if not st.session_state["ticker_manually_edited"]:
                st.session_state["ticker_text_value"] = extracted_text[:200]
            st.success("✅ टेक्स्ट निकालकर कहानी बॉक्स (और आउट्रो) में भर दिया गया है।")

    st.markdown('<div class="section-heading">📝 कहानी / स्क्रिप्ट लिखें</div>', unsafe_allow_html=True)
    st.text_area(
        "अपनी कहानी या स्क्रिप्ट यहाँ पेस्ट करें (या ऊपर से ऑटो-फिल करें)", height=180,
        key="story_script_text",
    )

    st.markdown('<div class="section-heading">📰 न्यूज़ पट्टी / आउट्रो कमेंट</div>', unsafe_allow_html=True)

    def _on_ticker_manual_edit():
        st.session_state["ticker_manually_edited"] = True

    st.text_input(
        "वीडियो के क्लाइमेक्स में क्या दिखे? (डिफ़ॉल्ट रूप से कहानी से सिंक होता है)",
        key="ticker_text_value", on_change=_on_ticker_manual_edit,
    )


# --------------------------------------------------------------
# 8) वॉइसओवर सेक्शन
# --------------------------------------------------------------
def render_voiceover_section():
    st.markdown('<div class="section-heading">🎙️ वॉइसओवर चुनें</div>', unsafe_allow_html=True)
    st.radio(
        "वॉइसओवर मोड",
        options=["🕉️ बाबा एआई दिव्य आवाज़ (Edge-TTS)", "🎤 मेरी अपनी रिकॉर्ड की हुई आवाज़ (Custom Audio Upload)"],
        key="voiceover_mode", label_visibility="collapsed",
    )
    custom_audio_file = None
    if st.session_state["voiceover_mode"].startswith("🎤"):
        custom_audio_file = st.file_uploader(
            "अपनी रिकॉर्ड की हुई ऑडियो फाइल अपलोड करें (MP3/WAV)",
            type=["mp3", "wav", "m4a"], key="custom_voice_uploader",
        )
        if custom_audio_file is None:
            st.warning("⚠️ कृपया अपनी रिकॉर्डेड ऑडियो फाइल अपलोड करें।")
    return st.session_state["voiceover_mode"], custom_audio_file


# --------------------------------------------------------------
# 9) फॉर्मेट + कस्टम-ड्यूरेशन + क्वालिटी + सबटाइटल-स्टाइल
# --------------------------------------------------------------
def render_format_and_quality_section():
    settings_col1, settings_col2 = st.columns(2)

    with settings_col1:
        st.markdown('<div class="section-heading">🎞️ वीडियो फॉर्मेट</div>', unsafe_allow_html=True)
        st.radio("फॉर्मेट", options=["📱 9:16 Shorts (कहानी के अनुसार)", "🖥️ 16:9 Long Video"],
                  horizontal=True, key="video_format_choice", label_visibility="collapsed")
        is_long_video = st.session_state["video_format_choice"].startswith("🖥️")

        selected_duration_seconds = None
        if is_long_video:
            st.radio("ड्यूरेशन", options=["5 मिनट", "30 मिनट", "1 घंटा", "कस्टम (Custom)"],
                      horizontal=True, key="duration_choice_value")
            duration_map_minutes = {"5 मिनट": 5, "30 मिनट": 30, "1 घंटा": 60}

            if st.session_state["duration_choice_value"] == "कस्टम (Custom)":
                st.number_input("कस्टम ड्यूरेशन (मिनट में, 1-60)", min_value=1, max_value=60,
                                 key="custom_duration_minutes")
                selected_duration_seconds = st.session_state["custom_duration_minutes"] * 60
            else:
                selected_duration_seconds = duration_map_minutes[st.session_state["duration_choice_value"]] * 60

    with settings_col2:
        st.markdown('<div class="section-heading">🎨 सबटाइटल स्टाइल</div>', unsafe_allow_html=True)
        st.selectbox("रंग", options=["पीला (Gold)", "सफ़ेद (White)"], key="subtitle_color_choice")
        st.slider("फॉन्ट साइज़ (px)", min_value=50, max_value=90, key="subtitle_font_size")
        st.markdown('<div class="section-heading">🎚️ वीडियो क्वालिटी</div>', unsafe_allow_html=True)
        st.radio("क्वालिटी", options=["720p HD", "1080p Full HD"], horizontal=True,
                  key="quality_choice_value", label_visibility="collapsed")

    return is_long_video, selected_duration_seconds


# --------------------------------------------------------------
# 10) फाइलों को डिस्क पर सेव करना (हेल्पर्स)
# --------------------------------------------------------------
def _save_uploaded_file_to_temp(uploaded_file):
    file_extension = os.path.splitext(uploaded_file.name)[1]
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
    temp_file.write(uploaded_file.getvalue())
    temp_file.close()
    return temp_file.name


def _resolve_all_track_paths(visual_clips, music_tracks, sfx_files, sfx_events):
    resolved_visual_clips = [{
        "path": _save_uploaded_file_to_temp(c["file"]), "is_image": c["is_image"],
        "start": c["start"], "end": c["end"],
    } for c in visual_clips]

    resolved_music_tracks = [{
        "path": _save_uploaded_file_to_temp(m["file"]), "instrumental_only": m["instrumental_only"],
        "volume": m["volume"], "start": m["start"], "end": m["end"],
    } for m in music_tracks]

    sfx_name_to_path = {f.name: _save_uploaded_file_to_temp(f) for f in sfx_files}
    resolved_sfx_events = [{
        "path": sfx_name_to_path.get(event["sfx_name"]),   # None = बिल्ट-इन प्रीसेट ध्वनि (engine.py में नाम से पहचानी जाएगी)
        "sfx_name": event["sfx_name"], "start": event["start"],
        "end": event["end"], "volume": event["volume"],
    } for event in sfx_events]

    return resolved_visual_clips, resolved_music_tracks, resolved_sfx_events


def _generate_thumbnail_from_video(video_path: str) -> str:
    thumbnail_path = os.path.join(tempfile.gettempdir(), "cinematic_thumbnail.jpg")
    with VideoFileClip(video_path) as video_clip:
        video_clip.save_frame(thumbnail_path, t=video_clip.duration / 2)
    return thumbnail_path


def _build_common_kwargs(inputs, resolved_visual, resolved_music, resolved_sfx, output_path):
    return dict(
        visual_clips=resolved_visual,
        music_tracks=resolved_music,
        master_music_volume=inputs["master_music_volume"],
        sfx_events=resolved_sfx,
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
        outro_voice_active=True,   # ⚠️ मयूर-पंख हिलने पर VFX-ब्लास्ट + बाबा-स्पीच एक्टिवेट
    )


# --------------------------------------------------------------
# 11) मुख्य फंक्शन
# --------------------------------------------------------------
def main():
    _initialize_session_state()
    apply_dark_theme()
    render_header()
    render_user_guide()

    playwright_ok, playwright_error = _ensure_playwright_chromium_installed()
    if playwright_error and not playwright_ok:
        st.warning(f"⚠️ Playwright Chromium इंस्टॉल करते समय समस्या आई: {playwright_error}")

    st.info("💡 निर्देश: तीनों ट्रैक्स (विज़ुअल/म्यूज़िक/SFX) को नीचे अलग-अलग सजाएँ, फिर कहानी लिखकर वीडियो जनरेट करें।")

    visual_clips = render_visual_track()
    st.divider()
    music_tracks, master_music_volume = render_music_track()
    st.divider()
    sfx_files, sfx_events = render_sfx_track()
    st.divider()
    render_story_extractor_and_sync()
    st.divider()
    voiceover_mode, custom_audio_file = render_voiceover_section()
    st.divider()
    is_long_video, selected_duration_seconds = render_format_and_quality_section()
    st.divider()

    subtitle_color_hex = "#FFD700" if st.session_state["subtitle_color_choice"].startswith("पीला") else "#FFFFFF"

    inputs = {
        "visual_clips": visual_clips,
        "music_tracks": music_tracks,
        "master_music_volume": master_music_volume,
        "sfx_files": sfx_files,
        "sfx_events": sfx_events,
        "story_script": st.session_state["story_script_text"],
        "ticker_text": st.session_state["ticker_text_value"],
        "aspect_ratio": "16:9" if is_long_video else "9:16",
        "duration_seconds": selected_duration_seconds,
        "quality": "1080p" if st.session_state["quality_choice_value"].startswith("1080p") else "720p",
        "sub_color": subtitle_color_hex,
        "sub_size": st.session_state["subtitle_font_size"],
        "voiceover_mode": "custom" if voiceover_mode.startswith("🎤") else "ai_tts",
        "custom_audio_path": None,
    }

    if custom_audio_file is not None:
        inputs["custom_audio_path"] = _save_uploaded_file_to_temp(custom_audio_file)

    # --- वैलिडेशन ---
    validation_ok = True
    if not visual_clips or not inputs["story_script"].strip():
        st.warning("⚠️ कृपया कम से कम एक विज़ुअल-क्लिप जोड़ें और कहानी लिखें।")
        validation_ok = False
    if inputs["voiceover_mode"] == "custom" and inputs["custom_audio_path"] is None:
        st.warning("⚠️ 'कस्टम आवाज़' मोड के लिए रिकॉर्डेड ऑडियो अपलोड करें।")
        validation_ok = False

    st.divider()

    # ------------------------------------------------------
    # 📺 लाइव ड्राफ्ट प्लेयर पैनल
    # ------------------------------------------------------
    st.markdown('<div class="section-heading">📺 ड्राफ्ट प्लेयर (Quick Preview)</div>', unsafe_allow_html=True)
    draft_clicked = st.button("⚡ क्विक ड्राफ्ट रेंडर (कम क्वालिटी, तेज़)", key="draft_render_button")

    if draft_clicked and validation_ok:
        try:
            with st.spinner("⚡ जल्दी ड्राफ्ट बन रहा है..."):
                resolved_visual, resolved_music, resolved_sfx = _resolve_all_track_paths(
                    visual_clips, music_tracks, sfx_files, sfx_events
                )
                draft_output_path = os.path.join(tempfile.gettempdir(), "draft_preview.mp4")
                draft_inputs = dict(inputs)
                draft_inputs["quality"] = "720p"   # ड्राफ्ट हमेशा तेज़-क्वालिटी में
                draft_kwargs = _build_common_kwargs(draft_inputs, resolved_visual, resolved_music, resolved_sfx, draft_output_path)
                draft_video_path = compile_cinematic_video(**draft_kwargs)
                st.session_state["draft_video_path"] = draft_video_path
        except Exception as draft_error:
            st.error(f"❌ ड्राफ्ट बनाते समय त्रुटि: {draft_error}")

    if st.session_state["draft_video_path"] and os.path.exists(st.session_state["draft_video_path"]):
        st.video(st.session_state["draft_video_path"])

    st.divider()
    generate_clicked = st.button("🚀 GENERATE CINEMATIC VIDEO (FINAL)", use_container_width=True)

    if generate_clicked:
        if not validation_ok:
            return
        try:
            with st.spinner("🎥 आपका फाइनल सिनेमैटिक वीडियो बन रहा है..."):
                resolved_visual, resolved_music, resolved_sfx = _resolve_all_track_paths(
                    visual_clips, music_tracks, sfx_files, sfx_events
                )
                output_dir = "generated_video"
                os.makedirs(output_dir, exist_ok=True)
                output_video_path = os.path.join(output_dir, "final_cinematic_output.mp4")

                final_kwargs = _build_common_kwargs(inputs, resolved_visual, resolved_music, resolved_sfx, output_video_path)
                final_video_path = compile_cinematic_video(**final_kwargs)
                final_thumbnail_path = _generate_thumbnail_from_video(final_video_path)

        except Exception as error:
            st.error(f"❌ वीडियो बनाते समय एक त्रुटि आई: {error}")
            import traceback
            with st.expander("🔍 पूरी तकनीकी जानकारी देखें"):
                st.code(traceback.format_exc())
            return

        st.success("✅ आपका सिनेमैटिक वीडियो सफलतापूर्वक तैयार हो गया है!")
        st.video(final_video_path)

        with open(final_video_path, "rb") as video_file:
            video_bytes = video_file.read()
        with open(final_thumbnail_path, "rb") as thumbnail_file:
            thumbnail_bytes = thumbnail_file.read()

        st.download_button("📥 DOWNLOAD YOUR CINEMATIC VIDEO & THUMBNAIL", data=video_bytes,
                            file_name="baba_cinematic_video.mp4", mime="video/mp4", use_container_width=True)
        st.download_button("🖼️ डाउनलोड थंबनेल (Thumbnail JPG)", data=thumbnail_bytes,
                            file_name="baba_cinematic_thumbnail.jpg", mime="image/jpeg", use_container_width=True)


if __name__ == "__main__":
    main()
