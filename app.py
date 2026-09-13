"""
==============================================================
बाबा जनरेटिव वेब स्टूडियो — टैब-मेनू + मिक्सिंग लैब संस्करण
==============================================================
इस वर्ज़न में जोड़ा गया है:
  - 🧪 मिक्सिंग लैब टैब: पूरी टाइमलाइन की बिना-रेंडर जाँच-रिपोर्ट,
    हर क्लिप का थंबनेल/जानकारी, और वहीं से क्रम/Start/End में
    इनलाइन सुधार — Generate से पहले एक जगह सब कुछ फाइनल-चेक होता है।

⚠️ नोट: वीडियो-क्लिप्स का असली फ्रेम-थंबनेल अभी नहीं निकाला जाता
   (सिर्फ़ नाम+टाइमिंग दिखती है) — अगर चाहिए तो अगला छोटा सुधार है।
==============================================================
"""

import os
import subprocess
import tempfile

import streamlit as st

st.set_page_config(
    page_title="बाबा जनरेटिव वेब स्टूडियो",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

from moviepy import VideoFileClip
from engine import compile_cinematic_video

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


def apply_dark_theme():
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
        div.stButton > button:first-child {
            background: linear-gradient(90deg, #ff416c, #ff4b2b); color: white; font-size: 18px;
            font-weight: 800; padding: 12px 0px; border-radius: 12px; border: none; width: 100%;
            box-shadow: 0px 0px 20px rgba(255, 75, 43, 0.6); transition: 0.3s;
        }
        div.stButton > button:first-child:hover { transform: scale(1.02); box-shadow: 0px 0px 30px rgba(255, 75, 43, 0.9); }
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
    st.markdown('<div class="sub-title">मेनू-आधारित प्रो स्टूडियो — हर ट्रैक अपनी टैब में</div>', unsafe_allow_html=True)
    st.divider()


def render_user_guide():
    with st.expander("🦚 बाबा स्टूडियो यूज़र गाइड (User Guide)", expanded=False):
        st.markdown(
            """
            ऊपर दी गई टैब्स में जाकर हर चीज़ अलग-अलग सजाएँ:
            **🖼️ फोटो** — तस्वीरें अपलोड करें (हर एक डिफ़ॉल्ट ५ सेकंड चलेगी)।
            **🎞️ वीडियो क्लिप्स** — वीडियो अपलोड करें और Start/End Second से ट्रिम करें।
            **🎵 म्यूज़िक** — भजन अपलोड करें, क्रम/वॉल्यूम/इंस्ट्रूमेंटल-मोड तय करें।
            **🔊 SFX** — ध्वनि-प्रभाव अपलोड या सर्च करें, टाइम-इवेंट जोड़ें।
            **📝 कहानी व वॉइस** — PDF/Word से कथा निकालें, वॉइसओवर चुनें।
            **⚙️ फॉर्मेट व क्वालिटी** — फॉर्मेट, ड्यूरेशन, सबटाइटल-स्टाइल तय करें।
            **🧪 मिक्सिंग लैब** — Generate से पहले यहाँ पूरी टाइमलाइन की जाँच-रिपोर्ट देखें
            और सीधे यहीं से क्रम/Start/End में सुधार करें।
            सबसे नीचे किसी भी टैब से **Generate** बटन से फाइनल वीडियो बनेगा।
            """
        )


def _initialize_session_state():
    default_values = {
        "story_script_text": "",
        "ticker_text_value": "",
        "ticker_manually_edited": False,
        "video_format_choice": "📱 9:16 Shorts (कहानी के अनुसार)",
        "duration_choice_value": "5 मिनट",
        "custom_duration_minutes": 10,
        "quality_choice_value": "720p HD",
        "subtitle_color_choice": "पीला (Gold)",
        "subtitle_font_size": 65,
        "voiceover_mode": "🕉️ बाबा एआई दिव्य आवाज़ (Edge-TTS)",
        "last_pdf_name": None,

        "photo_clips": [],
        "video_clips": [],

        "music_tracks": [],
        "sfx_files": [],
        "sfx_events": [],
        "master_music_volume": 0.8,

        "photo_uploader_key": 0,
        "video_uploader_key": 0,
        "music_uploader_key": 0,
        "sfx_uploader_key": 0,

        "draft_video_path": None,
    }
    for key, default_value in default_values.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


# --------------------------------------------------------------
# 🖼️ फोटो टैब
# --------------------------------------------------------------
def render_photo_tab():
    st.markdown('<div class="section-heading">🖼️ फोटो अपलोड करें (हर एक डिफ़ॉल्ट ५ सेकंड, Ken Burns ज़ूम)</div>', unsafe_allow_html=True)

    pending_photos = st.file_uploader(
        "तस्वीरें अपलोड करें (PNG/JPG)", type=["jpg", "jpeg", "png"],
        accept_multiple_files=True, key=f"photo_uploader_{st.session_state['photo_uploader_key']}",
    )
    if st.button("➕ फोटो जोड़ें", key="add_photo_button"):
        existing_names = {p["file"].name for p in st.session_state["photo_clips"]}
        added = 0
        for pf in (pending_photos or []):
            if pf.name not in existing_names:
                st.session_state["photo_clips"].append({
                    "file": pf, "order": len(st.session_state["photo_clips"]) + len(st.session_state["video_clips"]) + 1,
                })
                added += 1
        if added:
            st.session_state["photo_uploader_key"] += 1
            st.rerun()
        else:
            st.warning("⚠️ कोई नई फोटो नहीं मिली।")

    if not st.session_state["photo_clips"]:
        st.info("अभी तक कोई फोटो नहीं जोड़ी गई।")
        return

    total_combined = len(st.session_state["photo_clips"]) + len(st.session_state["video_clips"])
    for idx, photo in enumerate(sorted(st.session_state["photo_clips"], key=lambda p: p["order"])):
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            col1, col2, col3 = st.columns([2, 1, 0.6])
            with col1:
                st.markdown(f'<span class="order-badge">🖼️ {photo["file"].name[:22]}</span>', unsafe_allow_html=True)
                st.image(photo["file"], use_container_width=True)
            with col2:
                def _on_change(target=photo, key=f"porder_{photo['file'].name}_{idx}"):
                    target["order"] = st.session_state[key]
                st.selectbox("क्रम (पूरी टाइमलाइन में)", options=list(range(1, total_combined + 1)),
                             index=min(photo["order"], total_combined) - 1,
                             key=f"porder_{photo['file'].name}_{idx}", on_change=_on_change)
            with col3:
                st.write("")
                if st.button("❌", key=f"remove_photo_{idx}"):
                    st.session_state["photo_clips"].remove(photo)
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)


# --------------------------------------------------------------
# 🎞️ वीडियो क्लिप्स टैब
# --------------------------------------------------------------
def render_video_tab():
    st.markdown('<div class="section-heading">🎞️ वीडियो क्लिप्स अपलोड करें (Start/End से ट्रिम करें)</div>', unsafe_allow_html=True)

    pending_videos = st.file_uploader(
        "वीडियो अपलोड करें (MP4/MOV)", type=["mp4", "mov"],
        accept_multiple_files=True, key=f"video_uploader_{st.session_state['video_uploader_key']}",
    )
    if st.button("➕ वीडियो क्लिप जोड़ें", key="add_video_button"):
        existing_names = {v["file"].name for v in st.session_state["video_clips"]}
        added = 0
        for vf in (pending_videos or []):
            if vf.name not in existing_names:
                st.session_state["video_clips"].append({
                    "file": vf, "order": len(st.session_state["photo_clips"]) + len(st.session_state["video_clips"]) + 1,
                    "start": 0.0, "end": 5.0,
                })
                added += 1
        if added:
            st.session_state["video_uploader_key"] += 1
            st.rerun()
        else:
            st.warning("⚠️ कोई नई वीडियो-फाइल नहीं मिली।")

    if not st.session_state["video_clips"]:
        st.info("अभी तक कोई वीडियो-क्लिप नहीं जोड़ी गई।")
        return

    total_combined = len(st.session_state["photo_clips"]) + len(st.session_state["video_clips"])
    for idx, video in enumerate(sorted(st.session_state["video_clips"], key=lambda v: v["order"])):
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 0.6])
            with col1:
                st.markdown(f'<span class="order-badge">🎞️ {video["file"].name[:22]}</span>', unsafe_allow_html=True)
            with col2:
                def _on_order_change(target=video, key=f"vorder_{video['file'].name}_{idx}"):
                    target["order"] = st.session_state[key]
                st.selectbox("क्रम", options=list(range(1, total_combined + 1)),
                             index=min(video["order"], total_combined) - 1,
                             key=f"vorder_{video['file'].name}_{idx}", on_change=_on_order_change)
            with col3:
                def _on_start_change(target=video, key=f"vstart_{video['file'].name}_{idx}"):
                    target["start"] = st.session_state[key]
                st.number_input("Start Sec", min_value=0.0, value=video["start"], step=0.5,
                                 key=f"vstart_{video['file'].name}_{idx}", on_change=_on_start_change)
            with col4:
                def _on_end_change(target=video, key=f"vend_{video['file'].name}_{idx}"):
                    target["end"] = st.session_state[key]
                st.number_input("End Sec", min_value=0.5, value=video["end"], step=0.5,
                                 key=f"vend_{video['file'].name}_{idx}", on_change=_on_end_change)
            with col5:
                st.write("")
                if st.button("❌", key=f"remove_video_{idx}"):
                    st.session_state["video_clips"].remove(video)
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)


# --------------------------------------------------------------
# 🎵 म्यूज़िक टैब
# --------------------------------------------------------------
def render_music_tab():
    st.markdown('<div class="section-heading">🎵 भजन / संगीत अपलोड करें</div>', unsafe_allow_html=True)
    pending_music = st.file_uploader(
        "भजन/संगीत (MP3/MP4/WAV)", type=["mp3", "mp4", "wav", "m4a"],
        accept_multiple_files=True, key=f"music_uploader_{st.session_state['music_uploader_key']}",
    )
    if st.button("➕ म्यूज़िक ट्रैक जोड़ें", key="add_music_button"):
        existing_names = {m["file"].name for m in st.session_state["music_tracks"]}
        added = 0
        for mf in (pending_music or []):
            if mf.name not in existing_names:
                st.session_state["music_tracks"].append({
                    "file": mf, "order": len(st.session_state["music_tracks"]) + 1,
                    "instrumental_only": False, "volume": 0.8, "start": 0.0, "end": 0.0,
                })
                added += 1
        if added:
            st.session_state["music_uploader_key"] += 1
            st.rerun()
        else:
            st.warning("⚠️ कोई नई फाइल नहीं मिली।")

    if not st.session_state["music_tracks"]:
        st.caption("ℹ️ कोई भजन नहीं जोड़ा गया — डिफ़ॉल्ट सितार-संगीत इस्तेमाल होगा।")
        return [], st.session_state["master_music_volume"]

    tracks = sorted(st.session_state["music_tracks"], key=lambda t: t["order"])
    multi_mode = len(tracks) > 1
    for idx, track in enumerate(tracks):
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            c1, c2, c3, c4, c5 = st.columns([2, 1, 1.6, 1.4, 0.6])
            with c1:
                st.markdown(f'<span class="music-badge">🎶 {track["file"].name[:20]}</span>', unsafe_allow_html=True)
                if multi_mode:
                    sc1, sc2 = st.columns(2)
                    with sc1:
                        def _on_s(t=track, k=f"mst_{track['file'].name}_{idx}"):
                            t["start"] = st.session_state[k]
                        st.number_input("Start", min_value=0.0, value=track["start"], step=1.0,
                                         key=f"mst_{track['file'].name}_{idx}", on_change=_on_s)
                    with sc2:
                        def _on_e(t=track, k=f"men_{track['file'].name}_{idx}"):
                            t["end"] = st.session_state[k]
                        st.number_input("End(0=पूरा)", min_value=0.0, value=track["end"], step=1.0,
                                         key=f"men_{track['file'].name}_{idx}", on_change=_on_e)
                else:
                    st.caption("🔁 Full Mode")
            with c2:
                def _on_o(t=track, k=f"mor_{track['file'].name}_{idx}"):
                    t["order"] = st.session_state[k]
                st.selectbox("क्रम", options=list(range(1, len(tracks) + 1)), index=track["order"] - 1,
                             key=f"mor_{track['file'].name}_{idx}", on_change=_on_o)
            with c3:
                def _on_i(t=track, k=f"min_{track['file'].name}_{idx}"):
                    t["instrumental_only"] = st.session_state[k]
                st.toggle("केवल इंस्ट्रूमेंटल", value=track["instrumental_only"],
                          key=f"min_{track['file'].name}_{idx}", on_change=_on_i)
            with c4:
                def _on_v(t=track, k=f"mvo_{track['file'].name}_{idx}"):
                    t["volume"] = st.session_state[k]
                st.slider("वॉल्यूम", 0.0, 1.0, value=track["volume"], step=0.05,
                          key=f"mvo_{track['file'].name}_{idx}", on_change=_on_v)
            with c5:
                st.write("")
                if st.button("❌", key=f"remove_music_{idx}"):
                    st.session_state["music_tracks"].remove(track)
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    st.slider("🎛️ मास्टर म्यूज़िक वॉल्यूम", 0.0, 1.0, key="master_music_volume")
    return tracks, st.session_state["master_music_volume"]


# --------------------------------------------------------------
# 🔊 SFX टैब
# --------------------------------------------------------------
def _search_freesound(query_text):
    if not REQUESTS_AVAILABLE:
        st.warning("⚠️ 'requests' उपलब्ध नहीं है।")
        return []
    api_key = st.secrets.get("FREESOUND_API_KEY", None) if hasattr(st, "secrets") else None
    if not api_key:
        st.warning("⚠️ Freesound API-key सेट नहीं है।")
        return []
    try:
        r = requests.get("https://freesound.org/apiv2/search/text/",
                          params={"query": query_text, "token": api_key, "fields": "id,name"}, timeout=10)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        st.warning(f"⚠️ सर्च में समस्या: {e}")
        return []


def render_sfx_tab():
    st.markdown('<div class="section-heading">🔊 कस्टम ध्वनियाँ अपलोड करें</div>', unsafe_allow_html=True)
    pending_sfx = st.file_uploader(
        "ध्वनि-फाइलें (MP3/WAV)", type=["mp3", "wav"], accept_multiple_files=True,
        key=f"sfx_uploader_{st.session_state['sfx_uploader_key']}",
    )
    if st.button("➕ SFX फाइल जोड़ें", key="add_sfx_file_button"):
        existing = {f.name for f in st.session_state["sfx_files"]}
        new_files = [f for f in (pending_sfx or []) if f.name not in existing]
        st.session_state["sfx_files"].extend(new_files)
        if new_files:
            st.session_state["sfx_uploader_key"] += 1
            st.rerun()

    st.markdown('<div class="section-heading">🌐 ग्लोबल-सर्च (Freesound)</div>', unsafe_allow_html=True)
    sc1, sc2 = st.columns([3, 1])
    with sc1:
        query = st.text_input("ध्वनि खोजें", key="sfx_search_query")
    with sc2:
        st.write("")
        if st.button("🔍 खोजें", key="sfx_search_button"):
            st.session_state["sfx_search_results"] = _search_freesound(query)
    if st.session_state.get("sfx_search_results"):
        for res in st.session_state["sfx_search_results"][:5]:
            st.markdown(f"🔉 {res.get('name', 'अज्ञात')}")

    available_names = [f.name for f in st.session_state["sfx_files"]] or ["शंखनाद 🐚", "डमरू बीट्स 🥁", "चिड़ियों की चहचहाहट 🐦"]

    st.divider()
    for idx, event in enumerate(st.session_state["sfx_events"]):
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            st.markdown(f'<span class="sfx-badge">🎯 {event["sfx_name"][:18]}</span>', unsafe_allow_html=True)
            e1, e2, e3, e4 = st.columns([1, 1, 1.5, 0.7])
            with e1: st.markdown(f"**Start: {event['start']}s**")
            with e2: st.markdown(f"**End: {event['end']}s**")
            with e3: st.markdown(f"🔊 {event['volume']}")
            with e4:
                if st.button("❌", key=f"remove_sfxevent_{idx}"):
                    st.session_state["sfx_events"].pop(idx)
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("**➕ नया SFX-इवेंट**")
    a1, a2, a3, a4, a5 = st.columns([2, 1, 1, 1.2, 0.8])
    with a1: name = st.selectbox("ध्वनि", options=available_names, key="new_sfx_name")
    with a2: start = st.number_input("Start", min_value=0.0, step=0.5, key="new_sfx_start")
    with a3: end = st.number_input("End", min_value=0.5, step=0.5, value=2.0, key="new_sfx_end")
    with a4: vol = st.slider("वॉल्यूम", 0.0, 1.0, value=0.7, step=0.05, key="new_sfx_volume")
    with a5:
        st.write("")
        if st.button("➕", key="add_sfx_event_button"):
            st.session_state["sfx_events"].append({"sfx_name": name, "start": start, "end": end, "volume": vol})
            st.rerun()

    return st.session_state["sfx_files"], st.session_state["sfx_events"]


# --------------------------------------------------------------
# 📝 कहानी व वॉइस टैब
# --------------------------------------------------------------
def render_story_tab():
    st.markdown('<div class="section-heading">📂 धार्मिक कथा / ग्रन्थ अपलोड करें (PDF या Word)</div>', unsafe_allow_html=True)
    uploaded_doc = st.file_uploader("कथा अपलोड करें (वैकल्पिक)", type=["pdf", "docx"], key="story_document_uploader")

    if uploaded_doc is not None and st.session_state.get("last_pdf_name") != uploaded_doc.name:
        extracted = ""
        ext = os.path.splitext(uploaded_doc.name)[1].lower()
        if ext == ".pdf" and PDF_SUPPORT_AVAILABLE:
            try:
                reader = PdfReader(uploaded_doc)
                extracted = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
            except Exception as e:
                st.warning(f"⚠️ PDF पढ़ने में समस्या: {e}")
        elif ext == ".docx" and DOCX_SUPPORT_AVAILABLE:
            try:
                doc = docx_lib.Document(uploaded_doc)
                extracted = "\n".join(p.text for p in doc.paragraphs).strip()
            except Exception as e:
                st.warning(f"⚠️ Word पढ़ने में समस्या: {e}")
        elif ext == ".pdf":
            st.warning("⚠️ requirements.txt में 'pypdf' जोड़ें।")
        elif ext == ".docx":
            st.warning("⚠️ requirements.txt में 'python-docx' जोड़ें।")

        if extracted:
            st.session_state["story_script_text"] = extracted
            st.session_state["last_pdf_name"] = uploaded_doc.name
            if not st.session_state["ticker_manually_edited"]:
                st.session_state["ticker_text_value"] = extracted[:200]
            st.success("✅ टेक्स्ट निकालकर भर दिया गया है।")

    st.markdown('<div class="section-heading">📝 कहानी / स्क्रिप्ट</div>', unsafe_allow_html=True)
    st.text_area("कहानी यहाँ लिखें/एडिट करें", height=180, key="story_script_text")

    st.markdown('<div class="section-heading">📰 आउट्रो कमेंट</div>', unsafe_allow_html=True)
    def _on_manual_edit():
        st.session_state["ticker_manually_edited"] = True
    st.text_input("आउट्रो टेक्स्ट (डिफ़ॉल्ट रूप से कहानी से सिंक)", key="ticker_text_value", on_change=_on_manual_edit)

    st.markdown('<div class="section-heading">🎙️ वॉइसओवर</div>', unsafe_allow_html=True)
    st.radio("मोड", options=["🕉️ बाबा एआई दिव्य आवाज़ (Edge-TTS)", "🎤 मेरी अपनी रिकॉर्डेड आवाज़"],
             key="voiceover_mode", label_visibility="collapsed")
    custom_audio = None
    if st.session_state["voiceover_mode"].startswith("🎤"):
        custom_audio = st.file_uploader("रिकॉर्डेड ऑडियो (MP3/WAV)", type=["mp3", "wav", "m4a"], key="custom_voice_uploader")
        if custom_audio is None:
            st.warning("⚠️ ऑडियो अपलोड करें।")
    return st.session_state["voiceover_mode"], custom_audio


# --------------------------------------------------------------
# ⚙️ फॉर्मेट व क्वालिटी टैब
# --------------------------------------------------------------
def render_settings_tab():
    st.markdown('<div class="section-heading">🎞️ वीडियो फॉर्मेट</div>', unsafe_allow_html=True)
    st.radio("फॉर्मेट", options=["📱 9:16 Shorts (कहानी के अनुसार)", "🖥️ 16:9 Long Video"],
             horizontal=True, key="video_format_choice", label_visibility="collapsed")
    is_long = st.session_state["video_format_choice"].startswith("🖥️")

    duration_seconds = None
    if is_long:
        st.radio("ड्यूरेशन", options=["5 मिनट", "30 मिनट", "1 घंटा", "कस्टम (Custom)"],
                  horizontal=True, key="duration_choice_value")
        dmap = {"5 मिनट": 5, "30 मिनट": 30, "1 घंटा": 60}
        if st.session_state["duration_choice_value"] == "कस्टम (Custom)":
            st.number_input("कस्टम ड्यूरेशन (मिनट)", min_value=1, max_value=60, key="custom_duration_minutes")
            duration_seconds = st.session_state["custom_duration_minutes"] * 60
        else:
            duration_seconds = dmap[st.session_state["duration_choice_value"]] * 60

    st.markdown('<div class="section-heading">🎨 सबटाइटल स्टाइल</div>', unsafe_allow_html=True)
    st.selectbox("रंग", options=["पीला (Gold)", "सफ़ेद (White)"], key="subtitle_color_choice")
    st.slider("फॉन्ट साइज़", 50, 90, key="subtitle_font_size")

    st.markdown('<div class="section-heading">🎚️ क्वालिटी</div>', unsafe_allow_html=True)
    st.radio("क्वालिटी", options=["720p HD", "1080p Full HD"], horizontal=True,
             key="quality_choice_value", label_visibility="collapsed")

    return is_long, duration_seconds


# --------------------------------------------------------------
# 🧪 मिक्सिंग लैब टैब — पूरी टाइमलाइन की जाँच + इनलाइन सुधार
# --------------------------------------------------------------
def render_mixing_lab_tab(inputs, music_tracks, sfx_files, sfx_events):
    """
    यह टैब बिना वीडियो रेंडर किए पूरी टाइमलाइन की जाँच-रिपोर्ट दिखाता है,
    हर विज़ुअल-क्लिप का थंबनेल दिखाता है, और यहीं से Start/End/क्रम/वॉल्यूम
    में सुधार करने देता है — यूज़र को दूसरे टैब्स में वापस नहीं जाना पड़ता।
    """
    st.markdown('<div class="section-heading">🧪 मिक्सिंग लैब — पूरी टाइमलाइन जाँच व सुधार</div>', unsafe_allow_html=True)

    problem_messages = []

    combined_visuals = (
        [{"kind": "photo", "data": p} for p in st.session_state["photo_clips"]]
        + [{"kind": "video", "data": v} for v in st.session_state["video_clips"]]
    )
    combined_visuals.sort(key=lambda item: item["data"]["order"])

    if not combined_visuals:
        problem_messages.append("❌ कोई फोटो/वीडियो नहीं जोड़ा गया।")

    all_orders = [item["data"]["order"] for item in combined_visuals]
    if len(set(all_orders)) != len(all_orders):
        problem_messages.append("❌ दो या अधिक विज़ुअल्स को एक ही क्रम-संख्या मिली है।")

    estimated_visual_duration = 0.0
    for item in combined_visuals:
        if item["kind"] == "photo":
            estimated_visual_duration += 5.0
        else:
            clip_duration = item["data"]["end"] - item["data"]["start"]
            if clip_duration <= 0:
                problem_messages.append(f"❌ '{item['data']['file'].name}' में End Second, Start Second से बड़ा नहीं है।")
            else:
                estimated_visual_duration += clip_duration

    for event in sfx_events:
        if event["end"] <= event["start"]:
            problem_messages.append(f"❌ SFX '{event['sfx_name']}' का End Time, Start Time से बड़ा नहीं है।")
        if event["start"] > estimated_visual_duration:
            problem_messages.append(f"⚠️ SFX '{event['sfx_name']}' का Start Time ({event['start']}s) अनुमानित वीडियो-लंबाई ({estimated_visual_duration:.1f}s) से आगे है।")

    if not inputs["story_script"].strip():
        problem_messages.append("❌ कहानी/स्क्रिप्ट खाली है।")
    if inputs["voiceover_mode"] == "custom" and inputs["custom_audio_path"] is None:
        problem_messages.append("❌ कस्टम-आवाज़ मोड चुना है पर ऑडियो अपलोड नहीं हुआ।")

    st.divider()

    if problem_messages:
        st.error(f"❌ {len(problem_messages)} समस्याएँ मिलीं — पहले इन्हें ठीक करें:")
        for message in problem_messages:
            st.markdown(f"- {message}")
    else:
        st.success(f"✅ सब कुछ ठीक है! अनुमानित विज़ुअल-लंबाई: {estimated_visual_duration:.1f} सेकंड।")

    st.divider()
    st.markdown('<div class="section-heading">🎞️ पूरी टाइमलाइन (क्रम में) — यहीं से सुधारें</div>', unsafe_allow_html=True)

    for position_index, item in enumerate(combined_visuals):
        clip_data = item["data"]
        with st.container():
            st.markdown('<div class="timeline-card">', unsafe_allow_html=True)
            thumb_col, info_col, edit_col = st.columns([1.2, 1.5, 2])

            with thumb_col:
                if item["kind"] == "photo":
                    st.image(clip_data["file"], use_container_width=True)
                else:
                    st.markdown("🎞️ *(वीडियो — फ्रेम-थंबनेल अभी नहीं)*")

            with info_col:
                st.markdown(f"**#{clip_data['order']} — {clip_data['file'].name[:22]}**")
                st.caption("🖼️ फोटो (5 सेकंड फिक्स)" if item["kind"] == "photo" else f"🎞️ वीडियो ({clip_data['start']}s → {clip_data['end']}s)")

            with edit_col:
                total_combined = len(combined_visuals)
                unique_key_suffix = f"lab_{item['kind']}_{clip_data['file'].name}_{position_index}"

                def _on_lab_order_change(target=clip_data, widget_key=f"order_{unique_key_suffix}"):
                    target["order"] = st.session_state[widget_key]

                st.selectbox("क्रम बदलें", options=list(range(1, total_combined + 1)),
                             index=min(clip_data["order"], total_combined) - 1,
                             key=f"order_{unique_key_suffix}", on_change=_on_lab_order_change)

                if item["kind"] == "video":
                    trim_col1, trim_col2 = st.columns(2)
                    with trim_col1:
                        def _on_lab_start_change(target=clip_data, widget_key=f"start_{unique_key_suffix}"):
                            target["start"] = st.session_state[widget_key]
                        st.number_input("Start", min_value=0.0, value=clip_data["start"], step=0.5,
                                         key=f"start_{unique_key_suffix}", on_change=_on_lab_start_change)
                    with trim_col2:
                        def _on_lab_end_change(target=clip_data, widget_key=f"end_{unique_key_suffix}"):
                            target["end"] = st.session_state[widget_key]
                        st.number_input("End", min_value=0.5, value=clip_data["end"], step=0.5,
                                         key=f"end_{unique_key_suffix}", on_change=_on_lab_end_change)

            st.markdown('</div>', unsafe_allow_html=True)

    st.divider()
    summary_col1, summary_col2 = st.columns(2)
    with summary_col1:
        st.markdown('<div class="section-heading">🎵 म्यूज़िक सारांश</div>', unsafe_allow_html=True)
        if music_tracks:
            for track in music_tracks:
                st.caption(f"🎶 #{track['order']} {track['file'].name[:20]} — वॉल्यूम {track['volume']}")
        else:
            st.caption("कोई भजन नहीं जोड़ा गया।")
    with summary_col2:
        st.markdown('<div class="section-heading">🔊 SFX सारांश</div>', unsafe_allow_html=True)
        if sfx_events:
            for event in sfx_events:
                st.caption(f"🎯 {event['sfx_name']} — {event['start']}s→{event['end']}s")
        else:
            st.caption("कोई SFX-इवेंट नहीं जोड़ा गया।")

    return len(problem_messages) == 0


# --------------------------------------------------------------
# हेल्पर्स: फाइल-सेव, थंबनेल, कॉमन-kwargs
# --------------------------------------------------------------
def _save_uploaded_file_to_temp(uploaded_file):
    ext = os.path.splitext(uploaded_file.name)[1]
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    tf.write(uploaded_file.getvalue())
    tf.close()
    return tf.name


def _resolve_all_tracks(photo_clips, video_clips, music_tracks, sfx_files, sfx_events):
    resolved_visual = []
    for p in photo_clips:
        resolved_visual.append({"path": _save_uploaded_file_to_temp(p["file"]), "is_image": True,
                                 "order": p["order"], "start": 0.0, "end": 5.0})
    for v in video_clips:
        resolved_visual.append({"path": _save_uploaded_file_to_temp(v["file"]), "is_image": False,
                                 "order": v["order"], "start": v["start"], "end": v["end"]})
    resolved_visual.sort(key=lambda c: c["order"])

    resolved_music = [{"path": _save_uploaded_file_to_temp(m["file"]), "instrumental_only": m["instrumental_only"],
                        "volume": m["volume"], "start": m["start"], "end": m["end"]} for m in music_tracks]

    sfx_name_to_path = {f.name: _save_uploaded_file_to_temp(f) for f in sfx_files}
    resolved_sfx = [{"path": sfx_name_to_path.get(e["sfx_name"]), "sfx_name": e["sfx_name"],
                      "start": e["start"], "end": e["end"], "volume": e["volume"]} for e in sfx_events]

    return resolved_visual, resolved_music, resolved_sfx


def _generate_thumbnail_from_video(video_path):
    thumb_path = os.path.join(tempfile.gettempdir(), "cinematic_thumbnail.jpg")
    with VideoFileClip(video_path) as clip:
        clip.save_frame(thumb_path, t=clip.duration / 2)
    return thumb_path


def _build_kwargs(inputs, resolved_visual, resolved_music, resolved_sfx, output_path):
    return dict(
        visual_clips=resolved_visual, music_tracks=resolved_music,
        master_music_volume=inputs["master_music_volume"], sfx_events=resolved_sfx,
        script_text=inputs["story_script"], outro_text=inputs["ticker_text"],
        output_video_path=output_path, aspect_ratio=inputs["aspect_ratio"],
        duration_seconds=inputs["duration_seconds"], quality=inputs["quality"],
        sub_color=inputs["sub_color"], sub_size=inputs["sub_size"],
        voiceover_mode=inputs["voiceover_mode"], custom_audio_path=inputs["custom_audio_path"],
        outro_voice_active=True,
    )


# --------------------------------------------------------------
# मुख्य फंक्शन — टैब-मेनू यहीं जुड़ता है
# --------------------------------------------------------------
def main():
    _initialize_session_state()
    apply_dark_theme()
    render_header()
    render_user_guide()

    playwright_ok, playwright_error = _ensure_playwright_chromium_installed()
    if playwright_error and not playwright_ok:
        st.warning(f"⚠️ Playwright समस्या: {playwright_error}")

    tab_photo, tab_video, tab_music, tab_sfx, tab_story, tab_settings, tab_lab = st.tabs(
        ["🖼️ फोटो", "🎞️ वीडियो क्लिप्स", "🎵 म्यूज़िक", "🔊 SFX", "📝 कहानी व वॉइस", "⚙️ फॉर्मेट व क्वालिटी", "🧪 मिक्सिंग लैब"]
    )

    with tab_photo:
        render_photo_tab()
    with tab_video:
        render_video_tab()
    with tab_music:
        music_tracks, master_music_volume = render_music_tab()
    with tab_sfx:
        sfx_files, sfx_events = render_sfx_tab()
    with tab_story:
        voiceover_mode, custom_audio_file = render_story_tab()
    with tab_settings:
        is_long_video, duration_seconds = render_settings_tab()

    st.divider()
    subtitle_color_hex = "#FFD700" if st.session_state["subtitle_color_choice"].startswith("पीला") else "#FFFFFF"

    inputs = {
        "story_script": st.session_state["story_script_text"],
        "ticker_text": st.session_state["ticker_text_value"],
        "aspect_ratio": "16:9" if is_long_video else "9:16",
        "duration_seconds": duration_seconds,
        "quality": "1080p" if st.session_state["quality_choice_value"].startswith("1080p") else "720p",
        "sub_color": subtitle_color_hex,
        "sub_size": st.session_state["subtitle_font_size"],
        "voiceover_mode": "custom" if voiceover_mode.startswith("🎤") else "ai_tts",
        "custom_audio_path": _save_uploaded_file_to_temp(custom_audio_file) if custom_audio_file else None,
        "master_music_volume": master_music_volume,
    }

    with tab_lab:
        validation_ok = render_mixing_lab_tab(inputs, music_tracks, sfx_files, sfx_events)

    if not validation_ok:
        st.warning("⚠️ '🧪 मिक्सिंग लैब' टैब में जाकर बताई गई समस्याएँ पहले ठीक करें, फिर Generate करें।")

    st.markdown('<div class="section-heading">📺 ड्राफ्ट प्लेयर (Quick Preview)</div>', unsafe_allow_html=True)
    if st.button("⚡ क्विक ड्राफ्ट रेंडर", key="draft_render_button") and validation_ok:
        try:
            with st.spinner("⚡ ड्राफ्ट बन रहा है..."):
                rv, rm, rs = _resolve_all_tracks(
                    st.session_state["photo_clips"], st.session_state["video_clips"],
                    music_tracks, sfx_files, sfx_events,
                )
                draft_path = os.path.join(tempfile.gettempdir(), "draft_preview.mp4")
                draft_inputs = dict(inputs); draft_inputs["quality"] = "720p"
                st.session_state["draft_video_path"] = compile_cinematic_video(
                    **_build_kwargs(draft_inputs, rv, rm, rs, draft_path)
                )
        except Exception as e:
            st.error(f"❌ ड्राफ्ट त्रुटि: {e}")

    if st.session_state["draft_video_path"] and os.path.exists(st.session_state["draft_video_path"]):
        st.video(st.session_state["draft_video_path"])

    st.divider()
    if st.button("🚀 GENERATE CINEMATIC VIDEO (FINAL)", use_container_width=True) and validation_ok:
        try:
            with st.spinner("🎥 फाइनल वीडियो बन रहा है..."):
                rv, rm, rs = _resolve_all_tracks(
                    st.session_state["photo_clips"], st.session_state["video_clips"],
                    music_tracks, sfx_files, sfx_events,
                )
                output_dir = "generated_video"
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, "final_cinematic_output.mp4")
                final_video_path = compile_cinematic_video(**_build_kwargs(inputs, rv, rm, rs, output_path))
                final_thumb_path = _generate_thumbnail_from_video(final_video_path)
        except Exception as e:
            st.error(f"❌ वीडियो बनाते समय त्रुटि: {e}")
            import traceback
            with st.expander("🔍 तकनीकी जानकारी"):
                st.code(traceback.format_exc())
            return

        st.success("✅ वीडियो सफलतापूर्वक तैयार!")
        st.video(final_video_path)
        with open(final_video_path, "rb") as vf:
            video_bytes = vf.read()
        with open(final_thumb_path, "rb") as tf:
            thumb_bytes = tf.read()
        st.download_button("📥 वीडियो डाउनलोड करें", data=video_bytes,
                            file_name="baba_cinematic_video.mp4", mime="video/mp4", use_container_width=True)
        st.download_button("🖼️ थंबनेल डाउनलोड करें", data=thumb_bytes,
                            file_name="baba_cinematic_thumbnail.jpg", mime="image/jpeg", use_container_width=True)


if __name__ == "__main__":
    main()
