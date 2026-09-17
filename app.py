# -*- coding: utf-8 -*-
"""
Baba Web Studio - Multi-Track Video Editing Streamlit App
Production-ready app.py

Requires a sibling module `engine.py` exposing:
    engine.master_render_pipeline(payload: dict) -> str  # returns output file path

Optionally, engine.py hands off the last 10-15 sec to `climax.py`
(fireworks / balloons / confetti / Like & Subscribe CTA / channel
watermark / Hindi AI voiceover) as described in the product plan.

--------------------------------------------------------------------------
DEVANAGARI / HINDI TEXT RENDERING — IMPORTANT NOTE FOR `engine.py`
--------------------------------------------------------------------------
This app collects Hindi/Devanagari text (script, ticker, climax text,
subtitles) as plain Python strings. Streamlit itself handles UTF-8
natively — no special handling needed on the UI side. The risk is
entirely on the RENDER side (MoviePy / PIL):

  - PIL's default ImageFont/ImageDraw does NOT shape Devanagari
    conjuncts/matras correctly without libraqm support — text renders
    as broken/disconnected glyphs.
  - Use "Nirmala.ttf" or "Mangal.ttf" (Windows) / "NotoSansDevanagari"
    (Linux) — a generic sans-serif font has NO Devanagari glyphs at all
    and will render empty boxes.
  - RECOMMENDED: render Hindi text as HTML/CSS via headless Chromium
    (Playwright) to a transparent PNG, then composite onto the video
    frame with MoviePy. Chromium shapes Devanagari correctly by default.

`engine.py` must apply this to every Hindi string in the payload:
`track5.script_text`, `track5.ticker_text`, `climax_text`, and any
Devanagari subtitle content.
--------------------------------------------------------------------------
"""

import os
import tempfile
import traceback
from datetime import datetime

import streamlit as st

# --------------------------------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------------------------------
st.set_page_config(page_title="Baba Web Studio", page_icon="🎬", layout="wide")

# --------------------------------------------------------------------------
# CONSTANTS
# --------------------------------------------------------------------------
UPLOAD_ROOT = os.path.join(tempfile.gettempdir(), "baba_web_studio_uploads")
os.makedirs(UPLOAD_ROOT, exist_ok=True)

IMAGE_EXTS = (".jpg", ".jpeg", ".png")
VIDEO_EXTS = (".mp4",)

DURATION_PRESETS = {
    "30 Sec (Shorts Default)": 30,
    "5 Min": 300,
    "10 Min": 600,
    "30 Min": 1800,
    "Custom": None,
}

MUSIC_MODES = ["🎵 Song", "🎻 Instrument", "🍃 Background Music"]

AI_VOICE_OPTIONS = [
    "hi-IN-MadhurNeural (पुरुष आवाज़)",
    "hi-IN-SwaraNeural (महिला आवाज़)",
    "hi-IN-AaravNeural (पुरुष आवाज़)",
    "hi-IN-AnanyaNeural (महिला आवाज़)",
]

BUILTIN_SFX_LIBRARY = ["शंख (Shankh)", "डमरू (Damru)", "घंटी (Ghanti)", "सीटी (Whistle)", "तालियां (Applause)"]

DEVANAGARI_FONT_CONFIG = {
    "language": "hi",
    "preferred_fonts": ["Nirmala.ttf", "Mangal.ttf", "NotoSansDevanagari-Regular.ttf"],
    "windows_font_dir": "C:\\Windows\\Fonts",
    "linux_font_candidates": [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    ],
    "render_method": "chromium_html",
    "pil_raqm_required": True,
}

# --------------------------------------------------------------------------
# SESSION STATE DEFAULTS
# --------------------------------------------------------------------------
DEFAULTS = {
    # Master Setup
    "ratio": "Shorts (9:16)",
    "duration_preset": "30 Sec (Shorts Default)",
    "custom_minutes": 0,
    "custom_seconds": 30,
    "video_duration": 30,
    "final_quality": "1080p",
    "enable_climax": True,
    "climax_duration": 10,
    "climax_text": "धन्यवाद! लाइक और सब्सक्राइब करें",
    "climax_watermark_path": None,
    # Track 1 - mandatory visuals
    "track1_files": [],   # {name, path, type, order, start_sec, end_sec, image_duration}
    "t1_def_dur": 5,
    "t1_ken_burns": True,
    # Track 2 - optional video clips timeline
    "track2_clips": [],   # {name, path, order, start_sec, end_sec}
    # Track 3 - mandatory audio/music
    "track3_audio": [],   # {name, path, order, start_sec, end_sec, mode}
    # Track 4 - optional music clips (tied to track 2 clips)
    "track4_music_clips": [],  # {name, path, order, start_sec, end_sec, mode}
    "track4_master_volume": 0.80,
    # Track 5 - script & voice
    "track5_script_text": "",
    "track5_script_file_path": None,
    "track5_voice_source": "AI Voice (Edge-TTS)",
    "track5_ai_voice": AI_VOICE_OPTIONS[0],
    "track5_manual_voice_path": None,
    "track5_subtitle_font_color": "#FFFFFF",
    "track5_subtitle_font_size": 40,
    "track5_ticker_text": "बाबा वेब स्टूडियो — प्रोफेशनल वीडियो एडिटिंग के लिए संपर्क करें",
    "track5_ticker_speed": "Medium",
    "track5_ticker_bg_color": "#000000",
    # Track 6 - optional SFX timeline
    "track6_sfx": [],   # {source_type, name, path, builtin_name, start_sec, end_sec, volume}
    # Track 7 - live preview / transitions
    "track7_transition_mode": "Auto-Magic",
    "track7_manual_transition": "Zoom",
    # Execution
    "is_rendering": False,
    "last_output_path": None,
}

for key, default_val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default_val


# --------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------
def save_uploaded_file(uploaded_file, subfolder: str) -> str:
    """Persist an in-memory UploadedFile to disk and return its path."""
    target_dir = os.path.join(UPLOAD_ROOT, subfolder)
    os.makedirs(target_dir, exist_ok=True)
    safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{uploaded_file.name}"
    target_path = os.path.join(target_dir, safe_name)
    with open(target_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return target_path


def sync_track1_files(uploaded_files):
    if not uploaded_files:
        return
    existing_names = {f["name"] for f in st.session_state.track1_files}
    next_order = len(st.session_state.track1_files) + 1
    for uf in uploaded_files:
        if uf.name in existing_names:
            continue
        ext = os.path.splitext(uf.name)[1].lower()
        saved_path = save_uploaded_file(uf, "track1")
        file_type = "video" if ext in VIDEO_EXTS else "image"
        st.session_state.track1_files.append(
            {
                "name": uf.name,
                "path": saved_path,
                "type": file_type,
                "order": next_order,
                "start_sec": 0.0,
                "end_sec": 5.0,
                "image_duration": int(st.session_state.t1_def_dur),
            }
        )
        next_order += 1


def compute_total_visual_time() -> float:
    total = 0.0
    for f in st.session_state.track1_files:
        if f["type"] == "video":
            dur = max(0.0, float(f["end_sec"]) - float(f["start_sec"]))
            total += dur if dur > 0 else float(st.session_state.t1_def_dur)
        else:
            total += float(f.get("image_duration", st.session_state.t1_def_dur))
    return total


# --------------------------------------------------------------------------
# HEADER / MASTER SETUP (Step 0)
# --------------------------------------------------------------------------
st.title("🎬 Baba Web Studio")
st.caption("Multi-Track Video Editor")

st.markdown("### ⚙️ Master Setup")

m_col1, m_col2, m_col3 = st.columns(3)
with m_col1:
    st.session_state.ratio = st.selectbox(
        "वीडियो फॉर्मेट (Video Format)",
        options=["Shorts (9:16)", "Long (16:9)"],
        index=["Shorts (9:16)", "Long (16:9)"].index(st.session_state.ratio),
    )
with m_col2:
    st.session_state.duration_preset = st.selectbox(
        "ड्यूरेशन (Duration)",
        options=list(DURATION_PRESETS.keys()),
        index=list(DURATION_PRESETS.keys()).index(st.session_state.duration_preset),
        key="duration_preset_select",
    )
with m_col3:
    st.session_state.final_quality = st.selectbox(
        "क्वालिटी (Final Render Quality)",
        options=["720p", "1080p"],
        index=["720p", "1080p"].index(st.session_state.final_quality),
        key="final_quality_select",
    )

if st.session_state.duration_preset == "Custom":
    c_col1, c_col2 = st.columns(2)
    with c_col1:
        st.session_state.custom_minutes = st.number_input(
            "मिनट (Minutes)", min_value=0, value=int(st.session_state.custom_minutes), step=1, key="custom_min_in"
        )
    with c_col2:
        st.session_state.custom_seconds = st.number_input(
            "सेकंड (Seconds)", min_value=0, max_value=59, value=int(st.session_state.custom_seconds), step=1, key="custom_sec_in"
        )
    st.session_state.video_duration = int(st.session_state.custom_minutes) * 60 + int(st.session_state.custom_seconds)
else:
    st.session_state.video_duration = DURATION_PRESETS[st.session_state.duration_preset]

st.caption(f"कुल टारगेट ड्यूरेशन (Base Duration): **{st.session_state.video_duration} सेकंड**")

with st.expander("🎆 क्लाइमैक्स / आउटरो सेटिंग्स (Climax Settings)", expanded=False):
    st.info("नोट: वीडियो के अंत में 'Like & Subscribe' बूस्टर सेगमेंट (आतिशबाज़ी, गुब्बारे, कन्फेटी) अपने आप जुड़ जाएगा।")
    cl_col1, cl_col2 = st.columns([1, 2])
    with cl_col1:
        st.session_state.enable_climax = st.checkbox(
            "क्लाइमैक्स जोड़ें", value=st.session_state.enable_climax, key="climax_toggle"
        )
    with cl_col2:
        if st.session_state.enable_climax:
            st.session_state.climax_duration = st.number_input(
                "क्लाइमैक्स ड्यूरेशन (सेकंड)",
                min_value=1, value=int(st.session_state.climax_duration), step=1, key="climax_dur_in",
            )
            if int(st.session_state.climax_duration) < 10:
                st.caption("💡 टिप: अगर क्लाइमैक्स 10 सेकंड से कम है, तो एनीमेशन और टेक्स्ट उसी समय में फ़िट कर दिए जाएँगे।")

    if st.session_state.enable_climax:
        st.markdown("**क्लाइमैक्स संदेश प्रकार (Climax CTA Type)**")
        st.session_state.climax_cta_type = st.radio(
            "CTA प्रकार चुनें",
            options=["Default CTA", "Custom CTA"],
            index=["Default CTA", "Custom CTA"].index(st.session_state.get("climax_cta_type", "Default CTA")),
            key="climax_cta_type_radio",
            horizontal=True
        )
        
        if st.session_state.climax_cta_type == "Custom CTA":
            st.session_state.climax_custom_text = st.text_area(
                "अपना कस्टम क्लाइमैक्स संदेश लिखें",
                value=st.session_state.get("climax_custom_text", ""),
                key="climax_custom_text_in",
                height=80
            )
        else:
            st.caption("ℹ️ डिफ़ॉल्ट संदेश दिखाया जाएगा: ✨ धन्यवाद! 👍 लाइक व सब्सक्राइब करें। 🔔")

        cl_logo = st.file_uploader("चैनल लोगो / वॉटरमार्क (PNG) — क्लाइमैक्स सेगमेंट में दिखेगा", type=["png"], key="climax_logo_uploader")
        if cl_logo is not None:
            st.session_state.climax_watermark_path = save_uploaded_file(cl_logo, "climax")

total_target_duration = int(st.session_state.video_duration) + (
    int(st.session_state.climax_duration) if st.session_state.enable_climax else 0
)
st.success(f"📐 कुल वीडियो लंबाई (Master Timeline) = {st.session_state.video_duration} सेकंड + "
           f"{'क्लाइमैक्स ' + str(st.session_state.climax_duration) + ' सेकंड' if st.session_state.enable_climax else '0 सेकंड क्लाइमैक्स'} "
           f"= **{total_target_duration} सेकंड**")

st.divider()
# --------------------------------------------------------------------------
# TRACK 1 - VIDEO CREATION FOLDER (MANDATORY)
# --------------------------------------------------------------------------
with st.expander("🎬 ट्रैक 1: वीडियो क्रिएशन फोल्डर — ज़रूरी (Mandatory)", expanded=True):
    st.info(
        "नोट: यहाँ अपनी सभी इमेज (JPG/PNG) या वीडियो (MP4) फाइलें अपलोड करें और उनका क्रम (Sequence) सेट करें। "
        "यह ट्रैक अनिवार्य है — बिना इसके वीडियो नहीं बनेगा।"
    )
    if st.session_state.ratio == "Shorts (9:16)":
        st.caption("📏 गाइडलाइन (Shorts): न्यूनतम 2-3 फाइलें, अधिकतम 8-10 फाइलें (60 सेकंड सीमा के भीतर रहने के लिए)।")
    else:
        st.caption("📏 गाइडलाइन (Long Video): न्यूनतम 3 फाइलें, आवश्यकतानुसार अधिक फाइलें जोड़ी जा सकती हैं।")

    uploaded_track1 = st.file_uploader(
        "इमेज / वीडियो अपलोड करें (Bulk Upload)",
        type=["jpg", "jpeg", "png", "mp4"],
        accept_multiple_files=True,
        key="t1_uploader",
    )
    sync_track1_files(uploaded_track1)

    if not st.session_state.track1_files:
        st.warning("📂 कृपया वीडियो शुरू करने के लिए अपनी इमेज या वीडियो फाइलें यहाँ अपलोड करें।")
    else:
        t1_col1, t1_col2 = st.columns(2)
        with t1_col1:
            st.session_state.t1_def_dur = st.number_input(
                "डिफ़ॉल्ट इमेज ड्यूरेशन (सेकंड)", min_value=1, value=int(st.session_state.t1_def_dur), step=1, key="t1_def_dur_in"
            )
        with t1_col2:
            st.session_state.t1_ken_burns = st.toggle(
                "Ken Burns इफ़ेक्ट (ज़ूम/मोशन)", value=st.session_state.t1_ken_burns, key="t1_kb_toggle"
            )

        st.markdown("**क्रम एवं ट्रिम (Sequence & Trim)**")
        for idx, item in enumerate(st.session_state.track1_files):
            cols = st.columns([3, 1, 1.2, 1.2, 1])
            cols[0].write(f"{item['name']}  `({item['type']})`")
            item["order"] = cols[1].number_input(
                "क्रम", min_value=1, value=int(item["order"]), step=1, key=f"t1_order_{idx}", label_visibility="collapsed"
            )
            if item["type"] == "video":
                item["start_sec"] = cols[2].number_input(
                    "Start Sec", min_value=0.0, value=float(item["start_sec"]), step=0.5, key=f"t1_start_{idx}", label_visibility="collapsed"
                )
                item["end_sec"] = cols[3].number_input(
                    "End Sec", min_value=0.0, value=float(item["end_sec"]), step=0.5, key=f"t1_end_{idx}", label_visibility="collapsed"
                )
            else:
                item["image_duration"] = cols[2].number_input(
                    "Duration Sec", min_value=1, value=int(item.get("image_duration", st.session_state.t1_def_dur)), step=1, key=f"t1_imgdur_{idx}", label_visibility="collapsed"
                )
                cols[3].write("—")
            if cols[4].button("हटाएं", key=f"t1_remove_{idx}"):
                st.session_state.track1_files.pop(idx)
                st.rerun()

        if st.button("🔄 Update Sequence", key="t1_update_seq_btn"):
            st.session_state.track1_files.sort(key=lambda f: f["order"])
            st.success("क्रम अपडेट हो गया ✅")

        st.session_state.track1_files.sort(key=lambda f: f["order"])
        total_visual_time = compute_total_visual_time()
        st.info(f"⏱️ कुल विज़ुअल समय (Total Visual Time): **{total_visual_time:.1f} सेकंड**")

        file_count = len(st.session_state.track1_files)
        if st.session_state.ratio == "Shorts (9:16)" and not (2 <= file_count <= 10):
            st.warning("⚠️ Shorts के लिए 2 से 10 फाइलों के बीच रखना बेहतर है।")
        elif st.session_state.ratio == "Long (16:9)" and file_count < 3:
            st.warning("⚠️ Long Video के लिए कम से कम 3 फाइलें अपलोड करने की सलाह दी जाती है।")

st.divider()

# --------------------------------------------------------------------------
# TRACK 2 - VIDEO CLIPS TIMELINE (OPTIONAL)
# --------------------------------------------------------------------------
with st.expander("🎞️ ट्रैक 2: वीडियो क्लिप्स टाइमलाइन — वैकल्पिक (Optional)", expanded=False):
    st.info("नोट: इस ट्रैक का उपयोग मुख्य वीडियो में अलग से वीडियो क्लिप्स (मीम्स, इंट्रो, साइड क्लिप्स) जोड़ने और उनका समय तय करने के लिए करें।")
    if st.session_state.ratio == "Shorts (9:16)":
        st.caption("📏 गाइडलाइन (Shorts): 1 या 2 छोटे क्लिप्स जोड़ना बेहतर रहता है।")
    else:
        st.caption("📏 गाइडलाइन (Long Video): आवश्यकतानुसार एकाधिक वीडियो क्लिप्स जोड़े जा सकते हैं।")

    if st.button("➕ नया वीडियो क्लिप टाइमलाइन पर जोड़ें", key="t2_add_clip_btn"):
        st.session_state.track2_clips.append(
            {"name": None, "path": None, "order": len(st.session_state.track2_clips) + 1, "start_sec": 0.0, "end_sec": 5.0}
        )
        st.rerun()

    if not st.session_state.track2_clips:
        st.caption("ℹ️ अभी कोई वीडियो-क्लिप टाइमलाइन स्लॉट नहीं जोड़ा गया।")
    else:
        for idx, clip in enumerate(st.session_state.track2_clips):
            st.markdown(f"**क्लिप {idx + 1}**")
            cc1, cc2 = st.columns([3, 1])
            clip_file = cc1.file_uploader("वीडियो क्लिप फ़ाइल", type=["mp4"], key=f"t2_file_{idx}")
            if clip_file is not None:
                clip["name"] = clip_file.name
                clip["path"] = save_uploaded_file(clip_file, "track2")
            if cc2.button("हटाएं", key=f"t2_remove_{idx}"):
                st.session_state.track2_clips.pop(idx)
                st.rerun()
            cc3, cc4, cc5 = st.columns(3)
            clip["order"] = cc3.number_input("क्रम", min_value=1, value=int(clip["order"]), step=1, key=f"t2_order_{idx}")
            clip["start_sec"] = cc4.number_input("Start Sec", min_value=0.0, value=float(clip["start_sec"]), step=0.5, key=f"t2_start_{idx}")
            clip["end_sec"] = cc5.number_input("End Sec", min_value=0.0, value=float(clip["end_sec"]), step=0.5, key=f"t2_end_{idx}")
            st.markdown("---")

st.divider()

# --------------------------------------------------------------------------
# TRACK 3 - AUDIO / MUSIC CREATION TRACK (MANDATORY)
# --------------------------------------------------------------------------
with st.expander("🎵 ट्रैक 3: ऑडियो/म्यूज़िक क्रिएशन ट्रैक — ज़रूरी (Mandatory)", expanded=True):
    st.info("नोट: वीडियो के बैकग्राउंड में चलने वाले गाने, भजन या म्यूज़िक यहाँ अपलोड करें और उनका क्रम तय करें। सायलेंट वीडियो नहीं बनेगा, इसलिए कम से कम एक फाइल ज़रूरी है।")
    if st.session_state.ratio == "Shorts (9:16)":
        st.caption("📏 छोटा म्यूज़िक अपलोड करने पर सिस्टम उसे Loop करके पूरी ड्यूरेशन तक चला देगा।")
    else:
        st.caption("📏 एकाधिक ऑडियो ट्रैक क्रम से जोड़े जा सकते हैं; कम लंबाई होने पर Loop अपने आप चलेगा।")

    t3_uploaded = st.file_uploader(
        "म्यूज़िक/भजन अपलोड करें (Bulk Upload)", type=["mp3", "wav", "m4a"], accept_multiple_files=True, key="t3_uploader"
    )
    if t3_uploaded:
        existing_t3_names = {a["name"] for a in st.session_state.track3_audio}
        next_order = len(st.session_state.track3_audio) + 1
        for af in t3_uploaded:
            if af.name not in existing_t3_names:
                st.session_state.track3_audio.append(
                    {
                        "name": af.name,
                        "path": save_uploaded_file(af, "track3"),
                        "order": next_order,
                        "start_sec": 0.0,
                        "end_sec": 0.0,
                        "mode": MUSIC_MODES[0],
                    }
                )
                next_order += 1

    if not st.session_state.track3_audio:
        st.warning("🎵 कृपया कम से कम एक गाना या म्यूज़िक फ़ाइल अपलोड करें (अनिवार्य)।")
    else:
        for idx, audio in enumerate(st.session_state.track3_audio):
            st.markdown(f"**{audio['name']}**")
            ac1, ac2, ac3, ac4 = st.columns(4)
            audio["order"] = ac1.number_input("क्रम", min_value=1, value=int(audio["order"]), step=1, key=f"t3_order_{idx}")
            audio["start_sec"] = ac2.number_input("Start Sec", min_value=0.0, value=float(audio["start_sec"]), step=0.5, key=f"t3_start_{idx}")
            audio["end_sec"] = ac3.number_input("End Sec (0 = पूरा गाना)", min_value=0.0, value=float(audio["end_sec"]), step=0.5, key=f"t3_end_{idx}")
            audio["mode"] = ac4.selectbox("मोड", options=MUSIC_MODES, index=MUSIC_MODES.index(audio["mode"]), key=f"t3_mode_{idx}")
            if st.button("हटाएं", key=f"t3_remove_{idx}"):
                st.session_state.track3_audio.pop(idx)
                st.rerun()
            st.markdown("---")

st.divider()

# --------------------------------------------------------------------------
# TRACK 4 - MUSIC CLIPS TIMELINE (OPTIONAL, TIED TO TRACK 2)
# --------------------------------------------------------------------------
with st.expander("🎼 ट्रैक 4: म्यूज़िक क्लिप्स टाइमलाइन — वैकल्पिक (Optional)", expanded=False):
    st.info("नोट: ट्रैक 2 में जोड़े गए वीडियो क्लिप्स के साथ कौन सा म्यूज़िक/ऑडियो चलना चाहिए, वह यहाँ सेट करें।")

    if st.button("➕ नया म्यूज़िक क्लिप टाइमलाइन पर जोड़ें", key="t4_add_clip_btn"):
        st.session_state.track4_music_clips.append(
            {"name": None, "path": None, "order": len(st.session_state.track4_music_clips) + 1, "start_sec": 0.0, "end_sec": 5.0, "mode": MUSIC_MODES[0]}
        )
        st.rerun()

    if not st.session_state.track4_music_clips:
        st.caption("ℹ️ अभी कोई म्यूज़िक-क्लिप टाइमलाइन स्लॉट नहीं जोड़ा गया है।")
    else:
        for idx, mclip in enumerate(st.session_state.track4_music_clips):
            st.markdown(f"**म्यूज़िक क्लिप {idx + 1}**")
            mc1, mc2 = st.columns([3, 1])
            mfile = mc1.file_uploader("ऑडियो फ़ाइल", type=["mp3", "wav", "m4a"], key=f"t4_file_{idx}")
            if mfile is not None:
                mclip["name"] = mfile.name
                mclip["path"] = save_uploaded_file(mfile, "track4")
            if mc2.button("हटाएं", key=f"t4_remove_{idx}"):
                st.session_state.track4_music_clips.pop(idx)
                st.rerun()
            mc3, mc4, mc5, mc6 = st.columns(4)
            mclip["order"] = mc3.number_input("क्रम", min_value=1, value=int(mclip["order"]), step=1, key=f"t4_order_{idx}")
            mclip["start_sec"] = mc4.number_input("Start Sec", min_value=0.0, value=float(mclip["start_sec"]), step=0.5, key=f"t4_start_{idx}")
            mclip["end_sec"] = mc5.number_input("End Sec", min_value=0.0, value=float(mclip["end_sec"]), step=0.5, key=f"t4_end_{idx}")
            mclip["mode"] = mc6.selectbox("मोड", options=MUSIC_MODES, index=MUSIC_MODES.index(mclip["mode"]), key=f"t4_mode_{idx}")
            st.markdown("---")

    st.session_state.track4_master_volume = st.slider(
        "🔊 मास्टर म्यूज़िक वॉल्यूम (Master Music Volume)", 0.0, 1.0, float(st.session_state.track4_master_volume), step=0.05, key="t4_master_vol"
    )

st.divider()

# --------------------------------------------------------------------------
# TRACK 5 - SCRIPT & VOICE (OPTIONAL)
# --------------------------------------------------------------------------
with st.expander("🎙️ ट्रैक 5: स्क्रिप्ट और आवाज़ — वैकल्पिक (Optional)", expanded=False):
    st.info("नोट: वीडियो की स्क्रिप्ट टाइप करें या PDF/DOCX अपलोड करें, AI आवाज़ चुनें, सबटाइटल स्टाइल और नीचे स्क्रॉल होने वाला टिकर टेक्स्ट सेट करें।")

    st.session_state.track5_script_text = st.text_area(
        "स्क्रिप्ट टेक्स्ट (Script)", value=st.session_state.track5_script_text, key="t5_script_text_in", height=120
    )
    t5_script_file = st.file_uploader("या स्क्रिप्ट फ़ाइल अपलोड करें (PDF/DOCX)", type=["pdf", "docx"], key="t5_script_file_uploader")
    if t5_script_file is not None:
        st.session_state.track5_script_file_path = save_uploaded_file(t5_script_file, "track5_script")

    st.markdown("**आवाज़ का स्रोत (Voice Source)**")
    st.session_state.track5_voice_source = st.radio(
        "आवाज़ कहाँ से आएगी?",
        options=["AI Voice (Edge-TTS)", "अपनी खुद की वॉइसओवर अपलोड करें"],
        index=["AI Voice (Edge-TTS)", "अपनी खुद की वॉइसओवर अपलोड करें"].index(st.session_state.track5_voice_source),
        key="t5_voice_source_radio",
    )
    if st.session_state.track5_voice_source == "AI Voice (Edge-TTS)":
        st.session_state.track5_ai_voice = st.selectbox(
            "AI आवाज़ चुनें", options=AI_VOICE_OPTIONS, index=AI_VOICE_OPTIONS.index(st.session_state.track5_ai_voice), key="t5_ai_voice_select"
        )
    else:
        t5_voice_file = st.file_uploader("वॉइसओवर ऑडियो अपलोड करें (MP3/WAV)", type=["mp3", "wav", "m4a"], key="t5_manual_voice_uploader")
        if t5_voice_file is not None:
            st.session_state.track5_manual_voice_path = save_uploaded_file(t5_voice_file, "track5_voice")
        st.caption("💡 नोट (Mantra Mode): अगर आप 10-15 सेकंड की आवाज़/मंत्र अपलोड करके लंबी वीडियो ड्यूरेशन चुनते हैं, तो यह आवाज़ पूरे वीडियो में लूप (Loop) होकर चलेगी।")

    st.markdown("**सबटाइटल स्टाइल (Subtitle Style)**")
    s_col1, s_col2 = st.columns(2)
    with s_col1:
        st.session_state.track5_subtitle_font_color = st.color_picker(
            "फॉन्ट रंग", value=st.session_state.track5_subtitle_font_color, key="t5_sub_color"
        )
    with s_col2:
        st.session_state.track5_subtitle_font_size = st.number_input(
            "फॉन्ट साइज़", min_value=10, value=int(st.session_state.track5_subtitle_font_size), step=2, key="t5_sub_size"
        )

    # --- SMART TICKER LOGIC (NO CONFLICT CHECK) ---
    has_script_or_voice = bool(
        st.session_state.track5_script_text or 
        st.session_state.track5_script_file_path or 
        st.session_state.track5_manual_voice_path
    )

    st.markdown("**नीचे स्क्रॉल होने वाला टिकर (Bottom Ticker)**")
    if has_script_or_voice:
        st.warning("⚠️ स्क्रिप्ट/वॉयसओवर सक्रिय होने के कारण टिकर पट्टी लॉक (Disabled) है, ताकि ऑन-स्क्रीन टेक्स्ट टकराएं नहीं। यह केवल Background Music मोड में चलेगा।")

    st.session_state.track5_ticker_text = st.text_input(
        "टिकर टेक्स्ट", 
        value=st.session_state.track5_ticker_text, 
        key="t5_ticker_text_in",
        disabled=has_script_or_voice
    )
    t_col1, t_col2 = st.columns(2)
    with t_col1:
        st.session_state.track5_ticker_speed = st.selectbox(
            "टिकर स्पीड", 
            options=["Slow", "Medium", "Fast"], 
            index=["Slow", "Medium", "Fast"].index(st.session_state.track5_ticker_speed), 
            key="t5_ticker_speed_sel",
            disabled=has_script_or_voice
        )
    with t_col2:
        st.session_state.track5_ticker_bg_color = st.color_picker(
            "टिकर बैकग्राउंड रंग", 
            value=st.session_state.track5_ticker_bg_color, 
            key="t5_ticker_bg_color_pick",
            disabled=has_script_or_voice
        )

st.divider()

# --------------------------------------------------------------------------
# TRACK 6 - SFX TIMELINE (OPTIONAL)
# --------------------------------------------------------------------------
with st.expander("🔊 ट्रैक 6: साउंड इफ़ेक्ट्स (SFX) टाइमलाइन — वैकल्पिक (Optional)", expanded=False):
    st.info("नोट: वीडियो के खास दृश्यों (शंख, डमरू, घंटी, सीटी आदि) पर मनचाहे साउंड इफ़ेक्ट्स को सटीक समय के साथ यहाँ सेट करें।")

    if st.button("➕ नया साउंड इफ़ेक्ट (SFX) इवेंट जोड़ें", key="t6_add_sfx_btn"):
        st.session_state.track6_sfx.append(
            {"source_type": "builtin", "name": BUILTIN_SFX_LIBRARY[0], "path": None, "builtin_name": BUILTIN_SFX_LIBRARY[0], "start_sec": 0.0, "end_sec": 2.0, "volume": 100}
        )
        st.rerun()

    if not st.session_state.track6_sfx:
        st.caption("ℹ️ अभी कोई साउंड इफ़ेक्ट नहीं जोड़ा गया है।")
    else:
        for idx, sfx in enumerate(st.session_state.track6_sfx):
            st.markdown(f"**SFX इवेंट {idx + 1}**")
            sf_col1, sf_col2 = st.columns([1, 1])
            src_choice = sf_col1.radio(
                "स्रोत", options=["इन-बिल्ट लाइब्रेरी", "कस्टम अपलोड"],
                index=0 if sfx["source_type"] == "builtin" else 1,
                key=f"t6_src_{idx}", horizontal=True,
            )
            if src_choice == "इन-बिल्ट लाइब्रेरी":
                sfx["source_type"] = "builtin"
                sfx["builtin_name"] = sf_col2.selectbox(
                    "इफ़ेक्ट चुनें", options=BUILTIN_SFX_LIBRARY,
                    index=BUILTIN_SFX_LIBRARY.index(sfx.get("builtin_name", BUILTIN_SFX_LIBRARY[0])),
                    key=f"t6_builtin_{idx}",
                )
                sfx["name"] = sfx["builtin_name"]
                sfx["path"] = None
            else:
                sfx["source_type"] = "custom"
                sfx_file = sf_col2.file_uploader("SFX फ़ाइल (MP3/WAV)", type=["mp3", "wav"], key=f"t6_custom_file_{idx}")
                if sfx_file is not None:
                    sfx["name"] = sfx_file.name
                    sfx["path"] = save_uploaded_file(sfx_file, "track6")

            sf_col3, sf_col4, sf_col5 = st.columns(3)
            sfx["start_sec"] = sf_col3.number_input("Start Sec", min_value=0.0, value=float(sfx["start_sec"]), step=0.5, key=f"t6_start_{idx}")
            sfx["end_sec"] = sf_col4.number_input("End Sec", min_value=0.0, value=float(sfx["end_sec"]), step=0.5, key=f"t6_end_{idx}")
            sfx["volume"] = sf_col5.slider("वॉल्यूम (%)", 0, 200, int(sfx["volume"]), key=f"t6_vol_{idx}")

            if st.button("हटाएं", key=f"t6_remove_{idx}"):
                st.session_state.track6_sfx.pop(idx)
                st.rerun()
            st.markdown("---")

st.divider()

# --------------------------------------------------------------------------
# TRACK 7 - LIVE PREVIEW BOARD / MASTER TIMELINE & CLIMAX HANDOFF
# --------------------------------------------------------------------------
with st.expander("⏱️ ट्रैक 7: लाइव प्रीव्यू और टाइमिंग बोर्ड (Timeline & Climax Handoff)", expanded=False):
    st.info("नोट: यह ट्रैक सिर्फ जानकारी दिखाता है — यहाँ कोई अपलोड नहीं होता। ट्रैक 1 और ट्रैक 2 के डेटा से यह अपने आप टाइम-मैपिंग टेबल बना देता है।")

    st.markdown("**🖼️ मुख्य विज़ुअल क्रम (Track 1 Auto-Time Mapping)**")
    if not st.session_state.track1_files:
        st.caption("Track 1 में फाइलें अपलोड करने के बाद यहाँ टाइमिंग टेबल दिखेगी।")
    else:
        cursor = 0.0
        rows = []
        for f in sorted(st.session_state.track1_files, key=lambda x: x["order"]):
            dur = (
                max(0.0, float(f["end_sec"]) - float(f["start_sec"])) or float(st.session_state.t1_def_dur)
                if f["type"] == "video"
                else float(f.get("image_duration", st.session_state.t1_def_dur))
            )
            rows.append({"समय (Time)": f"{cursor:.1f}s → {cursor + dur:.1f}s", "कंटेंट": f["name"], "प्रकार": f["type"]})
            cursor += dur
        st.dataframe(rows, use_container_width=True, hide_index=True)

    if st.session_state.track2_clips:
        st.markdown("**🎞️ वीडियो क्लिप्स (Track 2)**")
        rows2 = [
            {"समय (Time)": f"{c['start_sec']:.1f}s → {c['end_sec']:.1f}s", "क्लिप": c["name"] or "(फ़ाइल पेंडिंग)"}
            for c in sorted(st.session_state.track2_clips, key=lambda x: x["order"])
        ]
        st.dataframe(rows2, use_container_width=True, hide_index=True)

    st.markdown("**🎨 इफ़ेक्ट / ट्रांज़िशन मोड**")
    tr_col1, tr_col2 = st.columns(2)
    with tr_col1:
        st.session_state.track7_transition_mode = st.selectbox(
            "मोड", options=["Auto-Magic", "Manual"], index=["Auto-Magic", "Manual"].index(st.session_state.track7_transition_mode), key="t7_trans_mode"
        )
    with tr_col2:
        if st.session_state.track7_transition_mode == "Manual":
            st.session_state.track7_manual_transition = st.selectbox(
                "ट्रांज़िशन स्टाइल",
                options=["Zoom", "Pan", "Slide", "Glass Shatter", "Glow Flash"],
                index=["Zoom", "Pan", "Slide", "Glass Shatter", "Glow Flash"].index(st.session_state.track7_manual_transition),
                key="t7_manual_trans_select",
            )

    st.markdown("**📐 मास्टर टाइमलाइन सारांश (Master Timeline Summary)**")
    st.write(
        {
            "Base Duration (sec)": int(st.session_state.video_duration),
            "Climax Duration (sec)": int(st.session_state.climax_duration) if st.session_state.enable_climax else 0,
            "Total Duration (sec)": total_target_duration,
        }
    )

st.divider()

# --------------------------------------------------------------------------
# PAYLOAD CONSTRUCTION
# --------------------------------------------------------------------------
def build_payload(is_draft: bool) -> dict:
    t1_files_list = [
        {
            "path": f["path"],
            "type": f["type"],
            "order": int(f["order"]),
            "start_sec": float(f["start_sec"]),
            "end_sec": float(f["end_sec"]),
            "image_duration": int(f.get("image_duration", st.session_state.t1_def_dur)),
        }
        for f in sorted(st.session_state.track1_files, key=lambda x: x["order"])
    ] if st.session_state.track1_files else []

    t2_clips_list = [
        {"path": c["path"], "order": int(c["order"]), "start_sec": float(c["start_sec"]), "end_sec": float(c["end_sec"])}
        for c in sorted(st.session_state.track2_clips, key=lambda x: x["order"])
        if c["path"]
    ] if st.session_state.track2_clips else []

    t3_audio_list = [
        {
            "path": a["path"], "order": int(a["order"]), "start_sec": float(a["start_sec"]),
            "end_sec": float(a["end_sec"]), "mode": a["mode"],
        }
        for a in sorted(st.session_state.track3_audio, key=lambda x: x["order"])
    ] if st.session_state.track3_audio else []

    t4_clips_list = [
        {
            "path": m["path"], "order": int(m["order"]), "start_sec": float(m["start_sec"]),
            "end_sec": float(m["end_sec"]), "mode": m["mode"],
        }
        for m in sorted(st.session_state.track4_music_clips, key=lambda x: x["order"])
        if m["path"]
    ] if st.session_state.track4_music_clips else []

    t6_sfx_list = [
        {
            "source_type": s["source_type"],
            "path": s["path"],
            "builtin_name": s.get("builtin_name"),
            "start_sec": float(s["start_sec"]),
            "end_sec": float(s["end_sec"]),
            "volume": int(s["volume"]),
        }
        for s in st.session_state.track6_sfx
    ] if st.session_state.track6_sfx else []

    # --- SMART TICKER CHECK ---
    has_script_or_voice = bool(
        st.session_state.track5_script_text or 
        st.session_state.track5_script_file_path or 
        st.session_state.track5_manual_voice_path
    )
    ticker_enabled = not has_script_or_voice

    payload = {
        "ratio": st.session_state.ratio,
        "is_shorts": st.session_state.ratio == "Shorts (9:16)",
        "duration": int(st.session_state.video_duration),
        "is_draft": bool(is_draft),
        "output_quality": "360p" if is_draft else st.session_state.final_quality,
        "enable_climax": bool(st.session_state.enable_climax),
        "climax_duration": int(st.session_state.climax_duration) if st.session_state.enable_climax else 0,
        "climax_text": st.session_state.get("climax_text", ""),
        "climax_cta_type": st.session_state.get("climax_cta_type", "Default CTA"),
        "climax_custom_text": st.session_state.get("climax_custom_text", ""),
        "climax_watermark_path": st.session_state.climax_watermark_path,
        "font_config": DEVANAGARI_FONT_CONFIG,
        "track1": {
            "files": t1_files_list,   # never None
            "default_image_duration": int(st.session_state.t1_def_dur),
            "ken_burns": bool(st.session_state.t1_ken_burns),
        },
        "track2": {"clips": t2_clips_list},
        "track3": {"audio": t3_audio_list},
        "track4": {"clips": t4_clips_list, "master_volume": float(st.session_state.track4_master_volume)},
        "track5": {
            "script_text": st.session_state.track5_script_text or "",
            "script_file_path": st.session_state.track5_script_file_path,
            "voice_source": st.session_state.track5_voice_source,
            "ai_voice": st.session_state.track5_ai_voice if st.session_state.track5_voice_source == "AI Voice (Edge-TTS)" else None,
            "manual_voice_path": st.session_state.track5_manual_voice_path if st.session_state.track5_voice_source != "AI Voice (Edge-TTS)" else None,
            "subtitle_font_color": st.session_state.track5_subtitle_font_color,
            "subtitle_font_size": int(st.session_state.track5_subtitle_font_size),
            "ticker_enabled": ticker_enabled,
            "ticker_text": st.session_state.track5_ticker_text or "",
            "ticker_speed": st.session_state.track5_ticker_speed,
            "ticker_bg_color": st.session_state.track5_ticker_bg_color,
        },
        "track6": {"sfx": t6_sfx_list},
        "track7": {
            "transition_mode": st.session_state.track7_transition_mode,
            "manual_transition": st.session_state.track7_manual_transition if st.session_state.track7_transition_mode == "Manual" else None,
        },
    }
    return payload


def run_render(is_draft: bool):
    if not st.session_state.track1_files:
        st.error("Render se pehle Track 1 mein kam se kam ek image ya video upload karein (अनिवार्य)।")
        return
    if not st.session_state.track3_audio:
        st.error("Render se pehle Track 3 mein kam se kam ek music/audio file upload karein (अनिवार्य)।")
        return

    payload = build_payload(is_draft)
    st.session_state.is_rendering = True

    try:
        with st.spinner(
            "Quick Draft render ho raha hai..." if is_draft else "वीडियो तैयार हो रहा है, कृपया प्रतीक्षा करें..."
        ):
            import importlib
            import engine  # noqa: F401  (dynamic import, sibling module)
            importlib.reload(engine)
            output_file = engine.master_render_pipeline(payload)

        if output_file and os.path.exists(output_file):
            st.session_state.last_output_path = output_file
            st.success("Render complete!")
        else:
            st.error("Engine ne valid output file path return nahi kiya.")

    except ModuleNotFoundError:
        st.error(
            "`engine.py` nahi mila. Isse `app.py` ke same folder mein rakhein aur "
            "`master_render_pipeline(payload)` function define karein."
        )
    except Exception as e:
        st.error(f"Render fail hua: {e}")
        with st.expander("Error Details"):
            st.code(traceback.format_exc())
    finally:
        st.session_state.is_rendering = False

# --------------------------------------------------------------------------
# EXECUTION BUTTONS
# --------------------------------------------------------------------------
btn_col1, btn_col2 = st.columns(2)
with btn_col1:
    if st.button("⚡ Quick Draft Render (360p)", use_container_width=True, disabled=st.session_state.is_rendering):
        run_render(is_draft=True)
with btn_col2:
    if st.button(f"🎬 Final Video Render ({st.session_state.final_quality})", use_container_width=True, type="primary", disabled=st.session_state.is_rendering):
        run_render(is_draft=False)

# --------------------------------------------------------------------------
# OUTPUT PLAYER + DOWNLOAD
# --------------------------------------------------------------------------
if st.session_state.last_output_path and os.path.exists(st.session_state.last_output_path):
    st.divider()
    st.subheader("Output")
    st.video(st.session_state.last_output_path)
    with open(st.session_state.last_output_path, "rb") as f:
        st.download_button(
            "⬇️ Download Video",
            data=f,
            file_name=os.path.basename(st.session_state.last_output_path),
            mime="video/mp4",
        )
