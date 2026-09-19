"""
live_app.py
Streamlit UI for the Live Broadcast Studio, restructured into the 5
sections from the product spec (see live_engine.py's module docstring
for the architecture note on why video compositing stays Python-side
while audio mixing uses a real FFmpeg `amix` filter_complex).

    Section 1 - Combined Background Media Canvas
    Section 2 - Universal Audio Hub
    Section 4 - Mantra Flash Hub
    Section 5 - Story / Document Hub
    Section 3 - Live Ticker (rendered last, per spec: "the final section")

Call render_live_studio_ui() from app.py to display this whole UI.
"""

import os
import json
import tempfile
from datetime import datetime

import streamlit as st

import live_engine
from live_engine import Destination, StreamConfig, MediaItem


UPLOAD_ROOT = os.path.join(tempfile.gettempdir(), "live_studio_uploads")
os.makedirs(UPLOAD_ROOT, exist_ok=True)

PLATFORM_RTMP_PREFIXES = {
    "YouTube": "rtmp://a.rtmp.youtube.com/live2/",
    "Facebook": "rtmps://live-api-s.facebook.com:443/rtmp/",
    "Instagram": "rtmps://live-upload.instagram.com:443/rtmp/",
    "Custom RTMP": "",
}
PLATFORM_OPTIONS = list(PLATFORM_RTMP_PREFIXES.keys())

AUDIO_MODE_OPTIONS = {
    "सामान्य गाना (Song Mode)": live_engine.AUDIO_MODE_SONG,
    "केवल इंस्ट्रूमेंटल (Instrumental Only)": live_engine.AUDIO_MODE_INSTRUMENTAL,
    "हल्की आवाज़ (Background Music Mode)": live_engine.AUDIO_MODE_BACKGROUND,
}

AI_VOICE_OPTIONS = {
    "hi-IN-MadhurNeural (पुरुष आवाज़)": "hi-IN-MadhurNeural",
    "hi-IN-SwaraNeural (महिला आवाज़)": "hi-IN-SwaraNeural",
}

LIVE_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".live_studio_data")
os.makedirs(LIVE_CONFIG_DIR, exist_ok=True)
DESTINATIONS_STORE_PATH = os.path.join(LIVE_CONFIG_DIR, "destinations.json")


def _load_saved_destinations():
    try:
        if os.path.exists(DESTINATIONS_STORE_PATH):
            with open(DESTINATIONS_STORE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _save_destinations(destinations):
    try:
        with open(DESTINATIONS_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(destinations, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _effective_rtmp_url(dest: dict) -> str:
    platform = dest.get("platform", "")
    if platform == "Custom RTMP":
        return (dest.get("custom_full_url") or "").strip()
    prefix = PLATFORM_RTMP_PREFIXES.get(platform, "")
    key = (dest.get("stream_key") or "").strip()
    return (prefix + key) if key else ""


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

DEFAULT_STATE = {
    "destinations": [],
    "remember_destinations": True,

    # Section 1 - Combined Background Media Canvas
    "media_items": [],  # [{path, name, media_type, order}]
    "canvas_mode": None,  # auto-detected: "shorts" | "long"

    # Section 2 - Universal Audio Hub
    "audio_source_path": None,
    "audio_source_name": None,
    "audio_mode_label": list(AUDIO_MODE_OPTIONS.keys())[0],

    # Webcam / mic (kept, optional)
    "webcam_on": False,
    "bg_removal": "None",
    "custom_bg_image_path": None,
    "custom_bg_image_name": None,
    "mic_enabled": False,

    # Section 4 - Mantra Flash Hub
    "mantra_clip_path": None,
    "mantra_clip_name": None,
    "mantra_text": "",
    "mantra_style": live_engine.MANTRA_TEXT_STYLES[0],

    # Section 5 - Story / Document Hub
    "story_doc_path": None,
    "story_doc_name": None,
    "story_script_text": "",
    "story_voice_mode": "कोई आवाज़ नहीं (सिर्फ़ टेक्स्ट दिखेगा)",
    "story_ai_voice_label": list(AI_VOICE_OPTIONS.keys())[0],
    "story_voiceover_path": None,
    "story_voiceover_name": None,
    "story_generated_voice_path": None,

    # Section 3 - Live Ticker (final section)
    "ticker_text": "",
    "ticker_font_size": 32,
    "ticker_bg_color": "#141414",

    # Live state
    "is_live": False,
    "chat_messages": [],
    "_last_start_error": None,
    "_last_pushed_ticker": None,
    "_last_pushed_mantra": None,
    "_last_pushed_story": None,
}


def _init_session_state():
    if "live_studio" not in st.session_state:
        state = {k: (v.copy() if isinstance(v, list) else v) for k, v in DEFAULT_STATE.items()}
        state["destinations"] = _load_saved_destinations()
        st.session_state["live_studio"] = state
    else:
        for key, default_value in DEFAULT_STATE.items():
            st.session_state["live_studio"].setdefault(key, default_value)


def _set(key, value):
    st.session_state["live_studio"][key] = value


def _get(key):
    return st.session_state["live_studio"].get(key, DEFAULT_STATE.get(key))


def _save_uploaded_file(uploaded_file, subfolder: str) -> str:
    target_dir = os.path.join(UPLOAD_ROOT, subfolder)
    os.makedirs(target_dir, exist_ok=True)
    safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{uploaded_file.name}"
    target_path = os.path.join(target_dir, safe_name)
    with open(target_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return target_path


# ---------------------------------------------------------------------------
# Section 1 — Combined Background Media Canvas
# ---------------------------------------------------------------------------
def _render_section1_media_canvas():
    st.subheader("📦 सेक्शन 1: कंबाइंड बैकग्राउंड मीडिया लॉन्चर")
    st.caption(
        "यह आपकी लाइव स्ट्रीम की सबसे निचली मुख्य परत (Base Layer) है। एक ही जगह से वीडियो (MP4) और "
        "इमेज (JPG/PNG) दोनों अपलोड करें, फिर उनका क्रम तय करें।"
    )

    uploaded = st.file_uploader(
        "वीडियो या इमेज अपलोड करें (एक साथ कई फ़ाइलें चुन सकते हैं)",
        type=["mp4", "mov", "jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key="s1_media_uploader",
    )
    if uploaded:
        existing_names = {m["name"] for m in _get("media_items")}
        next_order = len(_get("media_items")) + 1
        for uf in uploaded:
            if uf.name in existing_names:
                continue
            ext = os.path.splitext(uf.name)[1].lower()
            media_type = "video" if ext in (".mp4", ".mov") else "image"
            path = _save_uploaded_file(uf, "s1_media")
            st.session_state["live_studio"]["media_items"].append(
                {"path": path, "name": uf.name, "media_type": media_type, "order": next_order}
            )
            next_order += 1
            if _get("canvas_mode") is None:
                orientation = live_engine.MediaCanvas.detect_orientation(path)
                _set("canvas_mode", orientation)

    if not _get("media_items"):
        st.caption(
            "ℹ️ अभी कोई फ़ाइल अपलोड नहीं हुई — इस हालत में एक अपने-आप बना हुआ सुंदर बैकग्राउंड इस्तेमाल होगा "
            "(देखें सेक्शन 5 का 'ऑटो-स्क्रीन जनरेटर')।"
        )
    else:
        st.markdown("**क्रम व्यवस्था (Sequence)**")
        for idx, item in enumerate(_get("media_items")):
            c1, c2, c3 = st.columns([3, 1, 0.6])
            c1.write(f"{item['name']} `({item['media_type']})`")
            item["order"] = c2.number_input(
                "क्रम", min_value=1, value=int(item["order"]), step=1,
                key=f"s1_order_{idx}", label_visibility="collapsed",
            )
            if c3.button("🗑️", key=f"s1_remove_{idx}"):
                st.session_state["live_studio"]["media_items"].pop(idx)
                if not st.session_state["live_studio"]["media_items"]:
                    _set("canvas_mode", None)
                st.rerun()

        if len(_get("media_items")) == 1 and _get("media_items")[0]["media_type"] == "image":
            st.info("📌 सिर्फ़ एक इमेज है — यह अपने-आप एक **अनंत लूप कैनवास** बन जाएगी, बाकी सारे "
                    "सेक्शन (मंत्र फ़्लैश, कहानी, टिकर) इसी के ऊपर लगातार चलते रहेंगे।")

        mode_label = "Shorts (9:16)" if _get("canvas_mode") == "shorts" else "Long (16:9)"
        st.success(f"🖥️ स्मार्ट मोड डिटेक्शन: कैनवास **{mode_label}** पर सेट है (पहली फ़ाइल के हिसाब से)।")


def _get_media_item_objects() -> list:
    return [
        MediaItem(path=m["path"], media_type=m["media_type"], order=int(m["order"]))
        for m in _get("media_items")
    ]


def _get_canvas_size():
    if _get("canvas_mode") == "long":
        return (1280, 720)
    return (720, 1280)


# ---------------------------------------------------------------------------
# Section 2 — Universal Audio Hub
# ---------------------------------------------------------------------------
def _render_section2_audio_hub():
    st.subheader("📦 सेक्शन 2: यूनिवर्सल ऑडियो/म्यूज़िक हब")
    st.caption(
        "यह लाइव स्ट्रीम के बैकग्राउंड साउंड को नियंत्रित करता है — पूरी तरह वैकल्पिक। MP4 दिया तो सिर्फ़ "
        "उसका म्यूज़िक इस्तेमाल होगा।"
    )

    audio_file = st.file_uploader(
        "म्यूज़िक (MP3) या वीडियो (MP4 — सिर्फ़ music निकाला जाएगा) अपलोड करें",
        type=["mp3", "wav", "m4a", "mp4"], key="s2_audio_uploader",
    )
    if audio_file is not None:
        path = _save_uploaded_file(audio_file, "s2_audio")
        _set("audio_source_path", path)
        _set("audio_source_name", audio_file.name)

    if _get("audio_source_path"):
        ac1, ac2 = st.columns([3, 1])
        ac1.success(f"✅ ऑडियो सेट है: {_get('audio_source_name')}")
        if ac2.button("हटाएं", key="s2_audio_remove_btn"):
            _set("audio_source_path", None)
            _set("audio_source_name", None)
            st.rerun()

        _set("audio_mode_label", st.selectbox(
            "ऑडियो प्रोसेसिंग मोड", options=list(AUDIO_MODE_OPTIONS.keys()),
            index=list(AUDIO_MODE_OPTIONS.keys()).index(_get("audio_mode_label")),
            key="s2_audio_mode_select",
        ))
        if AUDIO_MODE_OPTIONS[_get("audio_mode_label")] == live_engine.AUDIO_MODE_INSTRUMENTAL:
            st.caption("ℹ️ FFmpeg का center-channel cancellation filter गायक की आवाज़ को कम करेगा (सटीक AI stem-separation नहीं)।")
        elif AUDIO_MODE_OPTIONS[_get("audio_mode_label")] == live_engine.AUDIO_MODE_BACKGROUND:
            st.caption("ℹ️ Volume अपने आप 0.2x पर आ जाएगा ताकि मुख्य आवाज़ (mic/story voice) साफ़ सुनाई दे।")
    else:
        st.caption("ℹ️ अभी कोई ऑडियो अपलोड नहीं हुआ (वैकल्पिक)।")


# ---------------------------------------------------------------------------
# Section 4 — Mantra Flash Hub
# ---------------------------------------------------------------------------
def _render_section4_mantra_flash():
    st.subheader("📦 सेक्शन 4: मंत्र फ़्लैशिंग और विजुअल ड्रामा")
    st.caption(
        "मुख्य कैनवास के ऊपर चलने वाली एक Picture-in-Picture (PiP) परत। अगर सेक्शन 1 में कोई मुख्य "
        "वीडियो/इमेज चल रही है, तो यह पूरा मंत्र ड्रामा उसके ऊपर छोटी स्क्रीन में दिखाई देगा।"
    )

    st.markdown("**बॉक्स A — छोटी मंत्र क्लिप (4-5 सेकंड, Loop होगी)**")
    clip_file = st.file_uploader("मंत्र क्लिप अपलोड करें (वीडियो)", type=["mp4", "mov"], key="s4_clip_uploader")
    if clip_file is not None:
        path = _save_uploaded_file(clip_file, "s4_clip")
        _set("mantra_clip_path", path)
        _set("mantra_clip_name", clip_file.name)
    if _get("mantra_clip_name"):
        mc1, mc2 = st.columns([3, 1])
        mc1.success(f"✅ मंत्र क्लिप सेट है: {_get('mantra_clip_name')}")
        if mc2.button("हटाएं", key="s4_clip_remove_btn"):
            _set("mantra_clip_path", None)
            _set("mantra_clip_name", None)
            st.rerun()

    st.markdown("**बॉक्स B — मंत्र टेक्स्ट (Symbols के साथ लिख सकते हैं, जैसे 🙏 ॐ 📿)**")
    _set("mantra_text", st.text_input(
        "मंत्र टेक्स्ट", value=_get("mantra_text"), placeholder="ॐ नमः शिवाय 🙏",
        key="s4_mantra_text_input",
    ))
    _set("mantra_style", st.selectbox(
        "विजुअल इफ़ेक्ट स्टाइल", options=live_engine.MANTRA_TEXT_STYLES,
        index=live_engine.MANTRA_TEXT_STYLES.index(_get("mantra_style")),
        key="s4_mantra_style_select",
    ))
    style_hints = {
        "Flash Pop": "टेक्स्ट बार-बार दिखता-छिपता है (flash)।",
        "Rainbow Cycle": "टेक्स्ट का रंग लगातार बदलता रहता है।",
        "Neon Glow": "टेक्स्ट के चारों ओर pulsing glow effect।",
        "Bounce Scale": "टेक्स्ट का साइज़ धड़कते हुए बड़ा-छोटा होता है।",
    }
    st.caption(f"ℹ️ {style_hints.get(_get('mantra_style'), '')}")

    if live_engine.is_streaming() and _get("mantra_text") != st.session_state["live_studio"].get("_last_pushed_mantra"):
        live_engine.update_live_mantra_text(_get("mantra_text"))
        live_engine.update_live_mantra_style(_get("mantra_style"))
        st.session_state["live_studio"]["_last_pushed_mantra"] = _get("mantra_text")
        st.caption("🔄 Mantra live अपडेट हो गया।")


# ---------------------------------------------------------------------------
# Section 5 — Story / Document Hub
# ---------------------------------------------------------------------------
def _render_section5_story_hub():
    st.subheader("📦 सेक्शन 5: कहानी और दस्तावेज़ मोड")
    st.caption("टेक्स्ट आधारित लाइव स्ट्रीमिंग के लिए — दो में से कोई एक तरीका चुनें।")

    st.markdown("**विकल्प A — दस्तावेज़ अपलोड करें (PDF/Word)**")
    doc_file = st.file_uploader("कहानी की फ़ाइल", type=["pdf", "docx"], key="s5_doc_uploader")
    if doc_file is not None:
        path = _save_uploaded_file(doc_file, "s5_doc")
        _set("story_doc_path", path)
        _set("story_doc_name", doc_file.name)
    if _get("story_doc_name"):
        st.caption(f"✅ फ़ाइल सेट है: {_get('story_doc_name')}")

    st.markdown("**विकल्प B — सीधे लिखें (Script/Story/Mantra/संदेश)**")
    _set("story_script_text", st.text_area(
        "स्क्रिप्ट टेक्स्ट", value=_get("story_script_text"), height=150,
        placeholder="अपनी कहानी, स्क्रिप्ट या संदेश यहाँ लिखें — विशेष चिन्हों के साथ भी 🌺📿",
        key="s5_script_text_area",
    ))

    resolved_preview = live_engine.resolve_story_text(_get("story_script_text"), _get("story_doc_path"))
    if resolved_preview:
        st.info(f"📌 स्क्रीन पर दिखेगा (पहले 200 अक्षर): {resolved_preview[:200]}{'…' if len(resolved_preview) > 200 else ''}")

    st.markdown("**ऑडियो रीडिंग**")
    voice_options = ["कोई आवाज़ नहीं (सिर्फ़ टेक्स्ट दिखेगा)", "AI आवाज़ (Text-to-Speech)", "अपनी वॉइस-ओवर अपलोड करें"]
    _set("story_voice_mode", st.radio("आवाज़ कहाँ से आएगी?", options=voice_options,
                                       index=voice_options.index(_get("story_voice_mode")) if _get("story_voice_mode") in voice_options else 0,
                                       key="s5_voice_mode_radio"))

    if _get("story_voice_mode") == "AI आवाज़ (Text-to-Speech)":
        _set("story_ai_voice_label", st.selectbox(
            "AI आवाज़ चुनें", options=list(AI_VOICE_OPTIONS.keys()),
            index=list(AI_VOICE_OPTIONS.keys()).index(_get("story_ai_voice_label")),
            key="s5_ai_voice_select",
        ))
        st.caption("ℹ️ यह आवाज़ एक बार जनरेट होकर Loop होती रहेगी (टेक्स्ट बदलने पर दोबारा 'आवाज़ बनाएं' दबाएं — यह असली-समय में हर सेकंड नहीं बदलती)।")
        if st.button("🎙️ आवाज़ बनाएं (Generate TTS)", key="s5_generate_tts_btn"):
            text_for_tts = live_engine.resolve_story_text(_get("story_script_text"), _get("story_doc_path"))
            if not text_for_tts:
                st.warning("⚠️ पहले टेक्स्ट लिखें या फ़ाइल अपलोड करें।")
            else:
                with st.spinner("आवाज़ बन रही है..."):
                    voice_path = live_engine.generate_story_tts(text_for_tts, AI_VOICE_OPTIONS[_get("story_ai_voice_label")])
                if voice_path:
                    _set("story_generated_voice_path", voice_path)
                    st.success("✅ आवाज़ तैयार है।")
                    st.audio(voice_path)
                else:
                    st.error(f"आवाज़ नहीं बन पाई: {live_engine.get_last_error()}")

    elif _get("story_voice_mode") == "अपनी वॉइस-ओवर अपलोड करें":
        vo_file = st.file_uploader("वॉइस-ओवर (MP3/WAV)", type=["mp3", "wav", "m4a"], key="s5_voiceover_uploader")
        if vo_file is not None:
            path = _save_uploaded_file(vo_file, "s5_voiceover")
            _set("story_voiceover_path", path)
            _set("story_voiceover_name", vo_file.name)
        if _get("story_voiceover_name"):
            st.caption(f"✅ वॉइस-ओवर सेट है: {_get('story_voiceover_name')}")

    if not _get("media_items"):
        st.info("📌 ऑटो-स्क्रीन जनरेटर: सेक्शन 1 में कोई मीडिया नहीं है, इसलिए एक सुंदर डिफ़ॉल्ट बैकग्राउंड "
                "अपने-आप बन जाएगा, जिसके ऊपर यह कहानी टेक्स्ट दिखेगा।")

    if live_engine.is_streaming() and resolved_preview != st.session_state["live_studio"].get("_last_pushed_story"):
        live_engine.update_live_story_text(resolved_preview)
        st.session_state["live_studio"]["_last_pushed_story"] = resolved_preview
        st.caption("🔄 Story टेक्स्ट live अपडेट हो गया।")


def _get_story_voice_path():
    mode = _get("story_voice_mode")
    if mode == "अपनी वॉइस-ओवर अपलोड करें":
        return _get("story_voiceover_path")
    if mode == "AI आवाज़ (Text-to-Speech)":
        return _get("story_generated_voice_path")
    return None


# ---------------------------------------------------------------------------
# Section 3 — Live Ticker (rendered LAST, per spec)
# ---------------------------------------------------------------------------
def _render_section3_ticker():
    st.subheader("📦 सेक्शन 3: लाइव समाचार पट्टी (अंतिम सेक्शन)")
    st.caption("लाइव स्क्रीन के सबसे नीचे दिखने वाली आख़िरी परत।")

    _set("ticker_text", st.text_area(
        "टिकर टेक्स्ट (बड़ा बॉक्स — लंबा टेक्स्ट और सिम्बॉल्स आराम से लिखें 🌺📿)",
        value=_get("ticker_text"), height=100,
        placeholder="यहाँ अपना स्क्रॉलिंग संदेश लिखें...",
        key="s3_ticker_text_area",
    ))

    tc1, tc2 = st.columns(2)
    with tc1:
        _set("ticker_font_size", st.slider(
            "फ़ॉन्ट साइज़", min_value=18, max_value=64, value=int(_get("ticker_font_size")),
            key="s3_ticker_font_size_slider",
        ))
    with tc2:
        _set("ticker_bg_color", st.color_picker(
            "टिकर बैकग्राउंड रंग", value=_get("ticker_bg_color"), key="s3_ticker_bg_color_picker",
        ))

    st.caption("🛠️ Devanagari (Noto Sans Devanagari) और रंगीन इमोजी (Noto Color Emoji) फ़ॉन्ट hardcoded हैं ताकि हिंदी/सिम्बॉल्स डिब्बे बनकर न दिखें (सर्वर पर ये फ़ॉन्ट install होने चाहिए)।")

    if live_engine.is_streaming() and _get("ticker_text") != st.session_state["live_studio"].get("_last_pushed_ticker"):
        live_engine.update_live_ticker(_get("ticker_text"))
        live_engine.update_live_ticker_font_size(_get("ticker_font_size"))
        st.session_state["live_studio"]["_last_pushed_ticker"] = _get("ticker_text")
        st.caption("🔄 Ticker live अपडेट हो गया।")


# ---------------------------------------------------------------------------
# Stream Setup (destinations) + Camera/Mic (kept from before)
# ---------------------------------------------------------------------------
def _render_stream_setup():
    st.subheader("🎥 Stream Setup — Destinations")
    st.caption("एक से ज़्यादा platform एक साथ चुन सकते हैं — prefix अपने आप जुड़ता है, सिर्फ़ Stream Key पेस्ट करें।")

    if not live_engine.check_ffmpeg_available():
        st.error("⚠️ `ffmpeg` इस सिस्टम के PATH में नहीं मिला।")

    st.session_state["live_studio"]["remember_destinations"] = st.checkbox(
        "💾 Destinations याद रखें (refresh के बाद भी)", value=_get("remember_destinations"),
        key="live_remember_dest_checkbox",
    )
    st.caption(f"⚠️ Keys plain text में save होती हैं: `{DESTINATIONS_STORE_PATH}` — `.gitignore` में जोड़ें।")

    if st.button("➕ नया Destination जोड़ें", key="live_add_dest_btn"):
        st.session_state["live_studio"]["destinations"].append(
            {"platform": PLATFORM_OPTIONS[0], "stream_key": "", "custom_full_url": "", "enabled": True}
        )
        st.rerun()

    if not _get("destinations"):
        st.caption("ℹ️ अभी कोई destination नहीं जोड़ा गया।")
    else:
        for idx, dest in enumerate(_get("destinations")):
            with st.container(border=True):
                top1, top2, top3 = st.columns([2, 0.7, 0.7])
                dest["platform"] = top1.selectbox(
                    "Platform", options=PLATFORM_OPTIONS,
                    index=PLATFORM_OPTIONS.index(dest.get("platform", PLATFORM_OPTIONS[0])),
                    key=f"live_dest_platform_{idx}",
                )
                dest["enabled"] = top2.checkbox("On", value=dest.get("enabled", True), key=f"live_dest_enabled_{idx}")
                if top3.button("🗑️ हटाएं", key=f"live_dest_remove_{idx}"):
                    st.session_state["live_studio"]["destinations"].pop(idx)
                    _save_destinations(st.session_state["live_studio"]["destinations"])
                    st.rerun()

                if dest["platform"] == "Custom RTMP":
                    dest["custom_full_url"] = st.text_input(
                        "पूरा RTMP URL", value=dest.get("custom_full_url", ""), type="password",
                        placeholder="rtmp://your-server/app/KEY", key=f"live_dest_url_{idx}",
                    )
                else:
                    prefix = PLATFORM_RTMP_PREFIXES[dest["platform"]]
                    st.caption(f"Prefix (अपने आप जुड़ेगा): `{prefix}`")
                    dest["stream_key"] = st.text_input(
                        "सिर्फ़ Stream Key यहाँ पेस्ट करें", value=dest.get("stream_key", ""), type="password",
                        placeholder="xxxx-xxxx-xxxx-xxxx", key=f"live_dest_key_{idx}",
                    )

        if _get("remember_destinations"):
            _save_destinations(st.session_state["live_studio"]["destinations"])
        else:
            _save_destinations([])

    enabled_count = sum(1 for d in _get("destinations") if d.get("enabled") and _effective_rtmp_url(d))
    if enabled_count == 0:
        st.warning("⚠️ कम से कम एक destination को enable करें और उसकी key भरें।")
    else:
        st.success(f"✅ {enabled_count} destination(s) तैयार हैं।")

    st.info(
        "☁️ **Cloud पर चला रहे हैं?** Webcam बंद रखें — Section 1 (media canvas) + Section 2 (audio) "
        "किसी hardware camera/mic की ज़रूरत के बिना काम करते हैं। Webcam/Mic सिर्फ़ local machine पर चलेगा।"
    )


def _render_camera_controls():
    st.subheader("📷 Camera (वैकल्पिक)")
    col1, col2 = st.columns(2)
    with col1:
        _set("webcam_on", st.toggle("Webcam शामिल करें", value=_get("webcam_on"), key="live_webcam_toggle"))
        _set("mic_enabled", st.toggle("🎙️ Mic Audio शामिल करें", value=_get("mic_enabled"), key="live_mic_toggle"))
    with col2:
        if _get("webcam_on"):
            bg_options = ["None", "Blur", "Virtual Newsroom", "Custom Image Upload", "Green Screen"]
            _set("bg_removal", st.selectbox("AI Background Removal", options=bg_options,
                                             index=bg_options.index(_get("bg_removal")), key="live_bg_removal_select"))
            if _get("bg_removal") == "Custom Image Upload":
                bg_file = st.file_uploader("Background Image", type=["png", "jpg", "jpeg"], key="live_bg_image_uploader")
                if bg_file is not None:
                    path = _save_uploaded_file(bg_file, "bg_image")
                    _set("custom_bg_image_path", path)
                    _set("custom_bg_image_name", bg_file.name)


# ---------------------------------------------------------------------------
# Build StreamConfig + Controls + Chat + Summary
# ---------------------------------------------------------------------------
_BG_MODE_UI_TO_ENGINE = {
    "None": "none", "Blur": "blur", "Virtual Newsroom": "virtual",
    "Custom Image Upload": "virtual", "Green Screen": "green_screen",
}


def _build_stream_config() -> StreamConfig:
    destinations = [
        Destination(platform=d["platform"], rtmp_url=_effective_rtmp_url(d), enabled=d["enabled"])
        for d in _get("destinations")
    ]
    width, height = _get_canvas_size()
    return StreamConfig(
        destinations=destinations,
        webcam_on=_get("webcam_on"),
        background_mode=_BG_MODE_UI_TO_ENGINE.get(_get("bg_removal"), "none"),
        virtual_bg_path=_get("custom_bg_image_path"),
        mic_enabled=_get("mic_enabled"),
        media_items=_get_media_item_objects(),
        background_audio_path=_get("audio_source_path"),
        audio_mode=AUDIO_MODE_OPTIONS.get(_get("audio_mode_label"), live_engine.AUDIO_MODE_SONG),
        ticker_text=_get("ticker_text"),
        ticker_font_size=int(_get("ticker_font_size")),
        ticker_bg_color=_get("ticker_bg_color"),
        mantra_clip_path=_get("mantra_clip_path"),
        mantra_text=_get("mantra_text"),
        mantra_text_style=_get("mantra_style"),
        story_text=live_engine.resolve_story_text(_get("story_script_text"), _get("story_doc_path")),
        story_voice_path=_get_story_voice_path(),
        width=width, height=height,
    )


def _render_control_buttons():
    st.subheader("🎬 Live Controls")
    engine_status = live_engine.get_stream_status()
    actually_live = live_engine.is_streaming() and bool(engine_status and engine_status.get("publisher_alive"))
    if _get("is_live") != actually_live:
        _set("is_live", actually_live)

    enabled_dest_count = sum(1 for d in _get("destinations") if d.get("enabled") and _effective_rtmp_url(d))
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        start_disabled = _get("is_live") or enabled_dest_count == 0 or not live_engine.check_ffmpeg_available()
        if st.button("🔴 START LIVE BROADCAST", type="primary", disabled=start_disabled, use_container_width=True):
            config = _build_stream_config()
            started = live_engine.start_stream(config)
            if started:
                _set("is_live", True)
                _set("_last_start_error", None)
                st.session_state["live_studio"]["_last_pushed_ticker"] = _get("ticker_text")
                st.session_state["live_studio"]["_last_pushed_mantra"] = _get("mantra_text")
                st.session_state["live_studio"]["_last_pushed_story"] = config.story_text
                st.session_state["live_studio"]["chat_messages"].append("System: Broadcast started.")
            else:
                reason = live_engine.get_last_error() or "अज्ञात वजह - logs देखें।"
                _set("_last_start_error", reason)
                st.session_state["live_studio"]["chat_messages"].append(f"System: ⚠️ Start नहीं हो पाया — {reason}")
            st.rerun()

    if _get("_last_start_error"):
        st.error(f"❌ पिछली शुरुआत यहाँ फेल हुई:\n\n{_get('_last_start_error')}")

    with col2:
        if st.button("⏹️ STOP STREAM", disabled=not _get("is_live"), use_container_width=True):
            live_engine.stop_stream()
            _set("is_live", False)
            st.session_state["live_studio"]["chat_messages"].append("System: Broadcast stopped.")
            st.rerun()

    with col3:
        if _get("is_live"):
            uptime = engine_status.get("uptime_sec", 0) if engine_status else 0
            frames = engine_status.get("frames_pushed", 0) if engine_status else 0
            st.success(f"🟢 LIVE — {uptime:.0f}s, {frames} frames")
        else:
            st.info("⚪ Offline")

    if not _get("is_live") and enabled_dest_count == 0:
        st.caption("⚠️ ऊपर कम से कम एक destination enable करें।")


def _render_live_chat_feed():
    st.subheader("💬 Live Chat Feed")
    st.caption("ℹ️ यह एक लोकल डेमो चैट है — असली YouTube/Facebook कमेंट्स के लिए उन platforms के API/OAuth चाहिए (इस scope से बाहर)।")
    chat_container = st.container(height=200, border=True)
    with chat_container:
        messages = st.session_state["live_studio"]["chat_messages"]
        if not messages:
            st.caption("No messages yet.")
        else:
            for msg in messages:
                st.write(msg)
    with st.form(key="live_chat_form", clear_on_submit=True):
        new_message = st.text_input("Send a message", key="live_chat_input")
        if st.form_submit_button("Send") and new_message:
            st.session_state["live_studio"]["chat_messages"].append(f"You: {new_message}")
            st.rerun()


def _render_config_summary():
    with st.expander("🔧 Current Configuration"):
        state_copy = dict(st.session_state["live_studio"])
        state_copy["destinations"] = [
            {"platform": d.get("platform"), "key_set": bool(_effective_rtmp_url(d)), "enabled": d.get("enabled")}
            for d in state_copy.get("destinations", [])
        ]
        st.json(state_copy)
        status = live_engine.get_stream_status()
        if status:
            st.caption("Engine status:")
            st.json(status)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def render_live_studio_ui():
    _init_session_state()

    st.title("📡 Live Broadcast Studio")
    st.caption("5-Section Architecture — Media Canvas / Audio Hub / Mantra Flash / Story Hub / Ticker")

    st.divider()
    _render_stream_setup()

    st.divider()
    _render_section1_media_canvas()

    st.divider()
    _render_section2_audio_hub()

    st.divider()
    _render_camera_controls()

    st.divider()
    _render_section4_mantra_flash()

    st.divider()
    _render_section5_story_hub()

    st.divider()
    _render_section3_ticker()

    st.divider()
    _render_control_buttons()

    st.divider()
    _render_live_chat_feed()

    st.divider()
    _render_config_summary()


if __name__ == "__main__":
    st.set_page_config(page_title="Live Broadcast Studio", page_icon="📡", layout="wide")
    render_live_studio_ui()
