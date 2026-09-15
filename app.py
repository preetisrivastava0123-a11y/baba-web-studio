# ==============================================================
# बाबा जनरेटिव वेब स्टूडियो — 6-ट्रैक एडवांस्ड एडिटर (Pro Architecture)
# ==============================================================
import os
import subprocess
import tempfile
import streamlit as st

# --------------------------------------------------------------
# 1) पेज कॉन्फ़िगरेशन और डिफ़ॉल्ट सेटिंग्स
# --------------------------------------------------------------
st.set_page_config(
    page_title="बाबा जनरेटिव वेब स्टूडियो Pro",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

from moviepy import VideoFileClip
from engine import compile_cinematic_video

# डॉक्यूमेंट एक्सट्रैक्शन सपोर्ट
try:
    from pypdf import PdfReader
    PDF_SUPPORT = True
except Exception:
    PDF_SUPPORT = False

try:
    import docx as docx_lib
    DOCX_SUPPORT = True
except Exception:
    DOCX_SUPPORT = False

try:
    import requests
    REQUESTS_SUPPORT = True
except Exception:
    REQUESTS_SUPPORT = False

# --------------------------------------------------------------
# 2) प्रीमियम प्रो-स्टूडियो UI (Neon Dark Theme & Track Aesthetics)
# --------------------------------------------------------------
def apply_pro_studio_theme():
    st.markdown(
        """
        <style>
        .stApp {
            background: #090a0f;
            color: #e2e8f0;
        }
        .pro-header {
            text-align: center;
            font-size: 38px;
            font-weight: 900;
            background: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 5px;
        }
        .pro-sub {
            text-align: center;
            color: #94a3b8;
            font-size: 15px;
            margin-bottom: 25px;
        }
        .track-box {
            background: #111827;
            border: 1px solid #1f2937;
            border-left: 5px solid #00f2fe;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        }
        .track-title {
            color: #38bdf8;
            font-size: 20px;
            font-weight: 800;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
        }
        .slot-card {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 10px;
        }
        .badge-sfx {
            background: #7c3aed;
            color: #fff;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }
        .badge-music {
            background: #059669;
            color: #fff;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }
        div.stButton > button:first-child {
            background: linear-gradient(90deg, #2563eb, #3b82f6);
            color: white;
            font-weight: 700;
            border-radius: 8px;
            border: none;
            padding: 10px;
            transition: all 0.3s;
        }
        div.stButton > button:first-child:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
        }
        </style>
        """,
        unsafe_allow_html=True
    )

# Session State Initialization
def init_state():
    defaults = {
        "story_script_text": "",
        "ticker_text_value": "",
        "visual_clips": [],
        "visual_key": 0,
        "video_timeline": [],
        "video_slot_count": 0,
        "audio_pool": [],
        "audio_pool_key": 0,
        "music_timeline": [],
        "music_slot_count": 0,
        "master_music_vol": 0.8,
        "sfx_files": [],
        "sfx_events": [],
        "sfx_key": 0,
        "sub_font_size": 60,
        "sub_color": "पीला (Gold)",
        "video_format": "📱 9:16 Shorts",
        "draft_path": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()
apply_pro_studio_theme()

# Header Section
st.markdown('<div class="pro-header">🎬 बाबा जनरेटिव स्टूडियो — 6-ट्रैक टाइमलाइन कंसोल</div>', unsafe_allow_html=True)
st.markdown('<div class="pro-sub">मल्टी-ट्रैक लेयरिंग • विजुअल सिंक्रोनाइज़ेशन • एडवांस्ड SFX • स्क्रिप्ट ऑटो-इंजेशन</div>', unsafe_allow_html=True)

# --------------------------------------------------------------
#  TRACK 1: VISUAL POOL (कच्चा माल गोदाम)
# --------------------------------------------------------------
st.markdown('<div class="track-box"><div class="track-title">📸 ट्रैक 1: विज़ुअल पूल (Images & Raw Footage)</div>', unsafe_allow_html=True)
visual_uploads = st.file_uploader(
    "इमेजेस (JPG/PNG) या बैकग्राउंड फुटेज अपलोड करें",
    type=["jpg", "jpeg", "png", "mp4", "mov"],
    accept_multiple_files=True,
    key=f"visual_up_{st.session_state['visual_key']}"
)

if visual_uploads:
    existing = {x["file"].name for x in st.session_state["visual_clips"]}
    added = 0
    for f in visual_uploads:
        if f.name not in existing:
            is_img = f.type.startswith("image") if f.type else True
            st.session_state["visual_clips"].append({
                "file": f, "is_image": is_img, "start": 0.0, "end": 5.0 if is_img else 0.0
            })
            added += 1
    if added > 0:
        st.session_state["visual_key"] += 1
        st.rerun()

if st.session_state["visual_clips"]:
    cols = st.columns(6)
    for idx, item in enumerate(st.session_state["visual_clips"]):
        with cols[idx % 6]:
            st.markdown('<div class="slot-card">', unsafe_allow_html=True)
            if item["is_image"]:
                st.image(item["file"], use_container_width=True)
            else:
                st.write("🎞️ Video")
            st.caption(f"#{idx + 1} {item['file'].name[:10]}")
            if st.button("❌", key=f"del_vis_{idx}"):
                st.session_state["visual_clips"].pop(idx)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# --------------------------------------------------------------
# TRACK 2: VIDEO TIMELINE TRACK (समयबद्ध वीडियो स्लॉट्स)
# --------------------------------------------------------------
st.markdown('<div class="track-box"><div class="track-title">🎞️ ट्रैक 2: वीडियो क्लिप्स टाइमलाइन (Timed Layering)</div>', unsafe_allow_html=True)
if st.button("➕ नया वीडियो टाइमलाइन स्लॉट जोड़ें", key="add_vid_slot"):
    st.session_state["video_timeline"].append({
        "slot_id": st.session_state["video_slot_count"],
        "file": None, "start": 0.0, "end": 5.0
    })
    st.session_state["video_slot_count"] += 1
    st.rerun()

for idx, slot in enumerate(st.session_state["video_timeline"]):
    sid = slot["slot_id"]
    st.markdown('<div class="slot-card">', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([3, 1.5, 1.5, 0.5])
    with c1:
        slot["file"] = st.file_uploader(f"स्लॉट #{idx+1} वीडियो", type=["mp4", "mov"], key=f"vfile_{sid}")
    with c2:
        slot["start"] = st.number_input("प्रकट होने का समय (Sec)", min_value=0.0, value=slot["start"], key=f"vstart_{sid}")
    with c3:
        slot["end"] = st.number_input("हटने का समय (Sec)", min_value=0.0, value=slot["end"], key=f"vend_{sid}")
    with c4:
        st.write("")
        if st.button("❌", key=f"del_vslot_{sid}"):
            st.session_state["video_timeline"] = [s for s in st.session_state["video_timeline"] if s["slot_id"] != sid]
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# --------------------------------------------------------------
# TRACK 3 & 4: AUDIO POOL & MUSIC TIMELINE TRACK
# --------------------------------------------------------------
st.markdown('<div class="track-box"><div class="track-title">🎵 ट्रैक 3 & 4: संगीत गोदाम एवं टाइमलाइन (Background Score)</div>', unsafe_allow_html=True)
m_up = st.file_uploader("संगीत/भजन ऑडियो फाइल्स अपलोड करें", type=["mp3", "wav"], accept_multiple_files=True, key=f"aud_up_{st.session_state['audio_pool_key']}")
if m_up:
    existing_aud = {f.name for f in st.session_state["audio_pool"]}
    for f in m_up:
        if f.name not in existing_aud:
            st.session_state["audio_pool"].append(f)
    st.session_state["audio_pool_key"] += 1
    st.rerun()

st.slider("🎛️ मास्टर म्यूज़िक वॉल्यूम (Master Volume)", 0.0, 1.0, key="master_music_vol")

if st.button("➕ नया म्यूज़िक टाइमलाइन स्लॉट जोड़ें", key="add_mus_slot"):
    st.session_state["music_timeline"].append({
        "slot_id": st.session_state["music_slot_count"],
        "file": None, "start": 0.0, "end": 10.0, "order": len(st.session_state["music_timeline"]) + 1
    })
    st.session_state["music_slot_count"] += 1
    st.rerun()

for idx, slot in enumerate(st.session_state["music_timeline"]):
    sid = slot["slot_id"]
    st.markdown('<div class="slot-card">', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([3, 1.5, 1.5, 0.5])
    with c1:
        slot["file"] = st.file_uploader(f"म्यूज़िक क्लिप #{idx+1}", type=["mp3", "wav"], key=f"mfile_{sid}")
    with c2:
        slot["start"] = st.number_input("स्टार्ट (Sec)", min_value=0.0, value=slot["start"], key=f"mstart_{sid}")
    with c3:
        slot["end"] = st.number_input("एंड (Sec)", min_value=0.0, value=slot["end"], key=f"mend_{sid}")
    with c4:
        st.write("")
        if st.button("❌", key=f"del_mslot_{sid}"):
            st.session_state["music_timeline"] = [s for s in st.session_state["music_timeline"] if s["slot_id"] != sid]
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# --------------------------------------------------------------
# TRACK 5: SFX SYNCHRONIZATION TRACK
# --------------------------------------------------------------
st.markdown('<div class="track-box"><div class="track-title">🔊 ट्रैक 5: साउंड इफेक्ट्स (SFX Timing & Overlay)</div>', unsafe_allow_html=True)
sfx_ups = st.file_uploader("कस्टम SFX ध्वनि अपलोड करें (शंख, डमरू आदि)", type=["mp3", "wav"], accept_multiple_files=True, key=f"sfx_up_{st.session_state['sfx_key']}")
if sfx_ups:
    ex_sfx = {f.name for f in st.session_state["sfx_files"]}
    for f in sfx_ups:
        if f.name not in ex_sfx:
            st.session_state["sfx_files"].append(f)
    st.session_state["sfx_key"] += 1
    st.rerun()

avail_sfx = [f.name for f in st.session_state["sfx_files"]] or ["मंदिर घंटी 🔔", "शंख ध्वनि 🐚", "डमरू बीट 🥁"]
c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 0.5])
with c1:
    sfx_name = st.selectbox("ध्वनि चुनें", options=avail_sfx, key="new_sfx_n")
with c2:
    sfx_st = st.number_input("स्टार्ट टाइम", min_value=0.0, key="new_sfx_st")
with c3:
    sfx_et = st.number_input("एंड टाइम", min_value=0.5, value=2.0, key="new_sfx_et")
with c4:
    sfx_vol = st.slider("वॉल्यूम", 0.0, 1.0, 0.8, key="new_sfx_vl")
with c5:
    st.write("")
    if st.button("➕", key="add_sfx_evt"):
        st.session_state["sfx_events"].append({"sfx_name": sfx_name, "start": sfx_st, "end": sfx_et, "volume": sfx_vol})
        st.rerun()

for idx, evt in enumerate(st.session_state["sfx_events"]):
    st.caption(f"🎯 SFX #{idx+1}: {evt['sfx_name']} | Time: {evt['start']}s - {evt['end']}s | Vol: {evt['volume']}")
st.markdown('</div>', unsafe_allow_html=True)

# --------------------------------------------------------------
# TRACK 6: SCRIPT INGESTION & SUBTITLE FORMATTING
# --------------------------------------------------------------
st.markdown('<div class="track-box"><div class="track-title">📄 ट्रैक 6: कथा ग्रन्थ इंजेशन एवं सबटाइटल स्टाइलिंग</div>', unsafe_allow_html=True)
doc_file = st.file_uploader("PDF या DOCX कथा अपलोड करें", type=["pdf", "docx"], key="doc_ingest")
if doc_file:
    ext = os.path.splitext(doc_file.name)[1].lower()
    text = ""
    if ext == ".pdf" and PDF_SUPPORT:
        reader = PdfReader(doc_file)
        text = "\n".join([p.extract_text() or "" for p in reader.pages])
    elif ext == ".docx" and DOCX_SUPPORT:
        doc = docx_lib.Document(doc_file)
        text = "\n".join([p.text for p in doc.paragraphs])
    if text:
        st.session_state["story_script_text"] = text
        st.session_state["ticker_text_value"] = text[:150]
        st.success("✅ दस्तावेज़ का टेक्स्ट सफलतापूर्वक इंजस्ट कर लिया गया है!")

st.text_area("कहानी / स्क्रिप्ट पाठ", height=140, key="story_script_text")
st.text_input("न्यूज़ पट्टी / आउट्रो पाठ", key="ticker_text_value")

col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    st.selectbox("सबटाइटल रंग", ["पीला (Gold)", "सफ़ेद (White)"], key="sub_color")
with col_f2:
    st.slider("फॉन्ट साइज़", 40, 90, key="sub_font_size")
with col_f3:
    st.radio("वीडियो स्वरूप", ["📱 9:16 Shorts", "🖥️ 16:9 Long Video"], key="video_format", horizontal=True)
st.markdown('</div>', unsafe_allow_html=True)

# --------------------------------------------------------------
# ACTION BUTTONS & RENDER LOGIC
# --------------------------------------------------------------
st.divider()
if st.button("🚀 GENERATE COMPLETE CINEMATIC VIDEO", use_container_width=True):
    if not st.session_state["visual_clips"] and not st.session_state["story_script_text"].strip():
        st.error("❌ कृपया कम से कम एक विजुअल अपलोड करें और स्क्रिप्ट दर्ज करें।")
    else:
        st.info("⚙️ वीडियो रेंडरिंग प्रक्रिया शुरू की जा रही है... (इंजन प्रोसेस)")
