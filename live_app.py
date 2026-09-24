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
import shutil
import subprocess
import uuid
import tempfile
from datetime import datetime, date, time as dtime
from zoneinfo import ZoneInfo
from typing import Optional

import streamlit as st

import live_engine
from live_engine import Destination, StreamConfig, MediaItem
import live_chat_bridge


# Streamlit Cloud जैसे hosting पर सर्वर अक्सर UTC टाइमज़ोन में चलता है,
# भारत के समय (IST) में नहीं। Schedule के सभी समय (date/time picker,
# countdown, असली epoch calculation) यहाँ पक्के तौर पर Asia/Kolkata माने
# जाते हैं - चाहे सर्वर की अपनी टाइमज़ोन कुछ भी हो - ताकि आपने जो समय
# भारतीय समय के हिसाब से डाला, live ठीक उसी असली समय पर शुरू/बंद हो।
IST = ZoneInfo("Asia/Kolkata")

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
APP_URL_STORE_PATH = os.path.join(LIVE_CONFIG_DIR, "app_url.json")


def _load_app_url() -> str:
    try:
        if os.path.exists(APP_URL_STORE_PATH):
            with open(APP_URL_STORE_PATH, "r", encoding="utf-8") as f:
                return json.load(f).get("app_url", "")
    except Exception:
        pass
    return ""


def _save_app_url(url: str):
    try:
        with open(APP_URL_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump({"app_url": url}, f)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Destination persistence - अब Secrets/env से भी स्थायी रूप से load होता है
#
# WHY: Streamlit Cloud पर filesystem ephemeral होता है - restart/redeploy/
# sleep पर local file (destinations.json) मिट जाती है, इसलिए YouTube
# Stream Key बार-बार डालनी पड़ती थी। अब पहले environment variable, फिर
# Streamlit Secrets [youtube_live_destination] देखा जाता है - वहाँ मिल
# जाए तो local file खाली होने पर भी वही destination अपने आप वापस आ जाता
# है, दोबारा हाथ से डालने की ज़रूरत नहीं रहती।
# ---------------------------------------------------------------------------
def _load_secret_destination():
    env_key = os.environ.get("YOUTUBE_LIVE_STREAM_KEY")
    if env_key:
        return {
            "platform": os.environ.get("YOUTUBE_LIVE_PLATFORM", "YouTube"),
            "stream_key": env_key, "custom_full_url": "", "enabled": True, "_source": "env",
        }
    try:
        if "youtube_live_destination" in st.secrets:
            s = st.secrets["youtube_live_destination"]
            stream_key = s.get("stream_key", "")
            if stream_key:
                return {
                    "platform": s.get("platform", "YouTube"),
                    "stream_key": stream_key, "custom_full_url": "", "enabled": True, "_source": "secrets",
                }
    except Exception:
        pass
    return None


def _load_saved_destinations():
    try:
        if os.path.exists(DESTINATIONS_STORE_PATH):
            with open(DESTINATIONS_STORE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data
    except Exception:
        pass
    # Local file खाली/absent है (जैसा restart के बाद Streamlit Cloud पर
    # होता है) - Secrets/env से एक स्थायी default destination मिल जाए तो
    # वही लौटाएं, ताकि Stream Key दोबारा न डालनी पड़े।
    secret_dest = _load_secret_destination()
    return [secret_dest] if secret_dest else []


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
# समय को साफ़-साफ़ पढ़ने लायक बनाना (AM/PM + दिन का हिस्सा)
#
# WHY THIS EXISTS: st.time_input डिफ़ॉल्ट रूप से 24-घंटे फॉर्मेट में दिखाता
# है (जैसे "21:00") बिना किसी AM/PM संकेत के - इससे यह पता नहीं चलता कि
# चुना गया समय रात का है या दिन का। यह हर बार चुने गए समय के नीचे 12-घंटे
# वाला AM/PM फॉर्मेट + हिंदी में दिन का हिस्सा (सुबह/दोपहर/शाम/रात) दिखाता है।
# ---------------------------------------------------------------------------
_HINDI_TIME_PERIODS = [
    (0, 5, "आधी रात/रात"),
    (5, 12, "सुबह"),
    (12, 17, "दोपहर"),
    (17, 20, "शाम"),
    (20, 24, "रात"),
]


def _format_time_readable(t: dtime) -> str:
    period_label = "रात"
    for start_h, end_h, label in _HINDI_TIME_PERIODS:
        if start_h <= t.hour < end_h:
            period_label = label
            break
    time_12h = datetime.combine(date.today(), t).strftime("%I:%M %p")
    return f"{time_12h} ({period_label})"


def _time_picker_ampm(label: str, key_prefix: str, default_time: dtime) -> dtime:
    """छोटे-छोटे 3 बॉक्स — घंटा, मिनट, AM/PM — st.time_input के भारी बॉक्स
    की जगह, ताकि AM/PM साफ़ अलग से चुना जा सके, अंदाज़ा न लगाना पड़े।"""
    default_hour_12 = default_time.hour % 12
    if default_hour_12 == 0:
        default_hour_12 = 12
    default_period = "AM" if default_time.hour < 12 else "PM"

    st.markdown(f"**{label}**")
    c1, c2, c3 = st.columns([1, 1, 1.2])
    with c1:
        hour_12 = st.selectbox(
            "घंटा", options=list(range(1, 13)), index=default_hour_12 - 1,
            key=f"{key_prefix}_hour",
        )
    with c2:
        minute = st.selectbox(
            "मिनट", options=[f"{m:02d}" for m in range(60)], index=default_time.minute,
            key=f"{key_prefix}_minute",
        )
    with c3:
        period = st.selectbox(
            "AM/PM", options=["AM (सुबह/रात)", "PM (दोपहर/शाम)"],
            index=0 if default_period == "AM" else 1,
            key=f"{key_prefix}_period",
        )

    hour_24 = hour_12 % 12
    if period.startswith("PM"):
        hour_24 += 12
    result_time = dtime(hour=hour_24, minute=int(minute))
    st.caption(f"🕐 यह समय है: **{_format_time_readable(result_time)}**")
    return result_time


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

DEFAULT_STATE = {
    "destinations": [],
    "remember_destinations": True,

    # Section 1 - Combined Background Media Canvas
    "media_items": [],  # [{path, name, media_type, order}]
    "canvas_mode": None,  # auto-detected: "shorts" | "long"

    # Section 2 - Universal Audio Hub (multi-upload playlist, like Section 1)
    "audio_items": [],  # [{path, name, order}]
    "audio_mode_label": list(AUDIO_MODE_OPTIONS.keys())[0],
    "_audio_playlist_resolved_path": None,   # cached concatenated-playlist file
    "_audio_playlist_resolved_signature": None,  # to know when to rebuild it

    # Webcam / mic (kept, optional)
    "webcam_on": False,
    "bg_removal": "None",
    "custom_bg_image_path": None,
    "custom_bg_image_name": None,
    "mic_enabled": False,

    # Live Handover - keep the SAME RTMP connection open, switch source
    "enable_handover": False,

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

    # Schedule (auto start/stop, independent of browser being open)
    "schedule_enabled": False,
    "schedule_start_date": None,
    "schedule_start_time": None,
    "schedule_has_stop": False,
    "schedule_stop_date": None,
    "schedule_stop_time": None,

    # Live Chat Bridge (real YouTube chat, first-time-commenter auto-welcome)
    "chat_welcome_template": live_chat_bridge.DEFAULT_WELCOME_TEMPLATE,
    "chat_auto_welcome_enabled": True,
    "chat_translate_to_hindi": True,
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
                {"path": path, "name": uf.name, "media_type": media_type, "order": next_order, "use_own_audio": True}
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
        st.caption(
            "🎵 अगर किसी वीडियो में उसका अपना गाना/music है, तो नीचे उसका टॉगल **ON रखें** (डिफ़ॉल्ट ON है) — "
            "वह music अपने आप live स्ट्रीम में बजेगा, Section 2 में अलग से दोबारा अपलोड करने की ज़रूरत नहीं।"
        )
        for idx, item in enumerate(_get("media_items")):
            c1, c2, c3, c4 = st.columns([2.6, 0.8, 1.2, 0.6])
            c1.write(f"{item['name']} `({item['media_type']})`")
            item["order"] = c2.number_input(
                "क्रम", min_value=1, value=int(item["order"]), step=1,
                key=f"s1_order_{idx}", label_visibility="collapsed",
            )
            if item["media_type"] == "video":
                item["use_own_audio"] = c3.checkbox(
                    "🎵 अपना Music बजे", value=item.get("use_own_audio", True),
                    key=f"s1_own_audio_{idx}",
                )
            else:
                c3.caption("—")
            if c4.button("🗑️", key=f"s1_remove_{idx}"):
                st.session_state["live_studio"]["media_items"].pop(idx)
                if not st.session_state["live_studio"]["media_items"]:
                    _set("canvas_mode", None)
                st.rerun()

        if len(_get("media_items")) == 1 and _get("media_items")[0]["media_type"] == "image":
            st.info("📌 सिर्फ़ एक इमेज है — यह अपने-आप एक **अनंत लूप कैनवास** बन जाएगी, बाकी सारे "
                    "सेक्शन (मंत्र फ़्लैश, कहानी, टिकर) इसी के ऊपर लगातार चलते रहेंगे।")

        video_count_with_audio = sum(1 for m in _get("media_items") if m["media_type"] == "video" and m.get("use_own_audio", True))
        if video_count_with_audio > 1:
            st.caption(
                f"⚠️ {video_count_with_audio} वीडियो का 'अपना Music' ON है — ये सभी एक साथ मिक्स होकर बजेंगे "
                "(जिस वीडियो का visual अभी चल रहा है, ज़रूरी नहीं कि सिर्फ़ उसी का music सुनाई दे — यह एक "
                "known सीमा है; अगर सिर्फ़ एक का ही music चाहिए, तो बाकी का टॉगल OFF कर दें)।"
            )

        mode_label = "Shorts (9:16)" if _get("canvas_mode") == "shorts" else "Long (16:9)"
        st.success(f"🖥️ स्मार्ट मोड डिटेक्शन: कैनवास **{mode_label}** पर सेट है (पहली फ़ाइल के हिसाब से)।")


def _get_media_item_objects() -> list:
    return [
        MediaItem(
            path=m["path"], media_type=m["media_type"], order=int(m["order"]),
            use_own_audio=bool(m.get("use_own_audio", True)),
        )
        for m in _get("media_items")
    ]


def _get_canvas_size():
    if _get("canvas_mode") == "long":
        return (1280, 720)
    return (720, 1280)


# ---------------------------------------------------------------------------
# Section 2 — Universal Audio Hub (multi-upload playlist, like Section 1)
# ---------------------------------------------------------------------------
def _render_section2_audio_hub():
    st.subheader("📦 सेक्शन 2: यूनिवर्सल ऑडियो/म्यूज़िक हब")
    st.caption(
        "यह लाइव स्ट्रीम के बैकग्राउंड साउंड को नियंत्रित करता है — पूरी तरह वैकल्पिक। एक से ज़्यादा ट्रैक "
        "अपलोड करके उनका क्रम तय करें (Section 1 जैसा ही) — सब मिलकर एक playlist की तरह क्रम से बजेंगे, "
        "फिर से शुरू से loop होंगे। MP4 दिया तो सिर्फ़ उसका music इस्तेमाल होगा।"
    )

    audio_files = st.file_uploader(
        "म्यूज़िक (MP3/WAV) या वीडियो (MP4 — सिर्फ़ music निकाला जाएगा) अपलोड करें (एक साथ कई फ़ाइलें चुन सकते हैं)",
        type=["mp3", "wav", "m4a", "mp4"], accept_multiple_files=True, key="s2_audio_uploader",
    )
    if audio_files:
        existing_names = {a["name"] for a in _get("audio_items")}
        next_order = len(_get("audio_items")) + 1
        for af in audio_files:
            if af.name in existing_names:
                continue
            path = _save_uploaded_file(af, "s2_audio")
            st.session_state["live_studio"]["audio_items"].append(
                {"path": path, "name": af.name, "order": next_order}
            )
            next_order += 1

    if not _get("audio_items"):
        st.caption("ℹ️ अभी कोई ऑडियो अपलोड नहीं हुआ (वैकल्पिक)।")
        return

    st.markdown("**क्रम व्यवस्था (Playlist Sequence)**")
    for idx, item in enumerate(_get("audio_items")):
        c1, c2, c3 = st.columns([3, 1, 0.6])
        c1.write(item["name"])
        item["order"] = c2.number_input(
            "क्रम", min_value=1, value=int(item["order"]), step=1,
            key=f"s2_order_{idx}", label_visibility="collapsed",
        )
        if c3.button("🗑️", key=f"s2_remove_{idx}"):
            st.session_state["live_studio"]["audio_items"].pop(idx)
            st.rerun()

    if len(_get("audio_items")) > 1:
        st.caption(
            f"📌 {len(_get('audio_items'))} ट्रैक — Start Live दबाते ही ये सब क्रम से एक साथ जोड़कर "
            "(concatenate) एक playlist बनाई जाएगी, फिर वह पूरी playlist loop होगी।"
        )

    _set("audio_mode_label", st.selectbox(
        "ऑडियो प्रोसेसिंग मोड (पूरी playlist पर लागू होगा)", options=list(AUDIO_MODE_OPTIONS.keys()),
        index=list(AUDIO_MODE_OPTIONS.keys()).index(_get("audio_mode_label")),
        key="s2_audio_mode_select",
    ))
    if AUDIO_MODE_OPTIONS[_get("audio_mode_label")] == live_engine.AUDIO_MODE_INSTRUMENTAL:
        st.caption("ℹ️ FFmpeg का center-channel cancellation filter गायक की आवाज़ को कम करेगा (सटीक AI stem-separation नहीं)।")
    elif AUDIO_MODE_OPTIONS[_get("audio_mode_label")] == live_engine.AUDIO_MODE_BACKGROUND:
        st.caption("ℹ️ Volume अपने आप 0.2x पर आ जाएगा ताकि मुख्य आवाज़ (mic/story voice) साफ़ सुनाई दे।")


def _resolve_section2_playlist_path() -> Optional[str]:
    """
    Section 2 supports multiple uploaded tracks (a playlist), but the
    underlying engine (like Section 5's story voice) just takes ONE
    looping audio file path. So when there's more than one track, they
    get concatenated (in order) into a single file via ffmpeg's concat
    demuxer ONCE here, and that combined file is what actually gets
    passed to StreamConfig.background_audio_path. Cached by a signature
    of (paths, orders) so repeated reruns don't re-run ffmpeg needlessly.
    """
    items = sorted(_get("audio_items"), key=lambda a: a["order"])
    if not items:
        return None
    if len(items) == 1:
        return items[0]["path"]

    signature = tuple((i["path"], i["order"]) for i in items)
    if _get("_audio_playlist_resolved_signature") == signature and _get("_audio_playlist_resolved_path"):
        cached = _get("_audio_playlist_resolved_path")
        if os.path.exists(cached):
            return cached

    if shutil.which("ffmpeg") is None:
        return items[0]["path"]  # fallback: just the first track

    concat_list_path = os.path.join(tempfile.gettempdir(), f"s2_concat_{uuid.uuid4().hex}.txt")
    try:
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for item in items:
                escaped = item["path"].replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        out_path = os.path.join(tempfile.gettempdir(), f"s2_playlist_{uuid.uuid4().hex}.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path,
             "-c:a", "libmp3lame", "-q:a", "4", out_path],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180,
        )
        _set("_audio_playlist_resolved_path", out_path)
        _set("_audio_playlist_resolved_signature", signature)
        return out_path
    except Exception:
        return items[0]["path"]  # fallback: just the first track
    finally:
        try:
            os.remove(concat_list_path)
        except OSError:
            pass


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

    if any(d.get("_source") in ("env", "secrets") for d in _get("destinations")):
        st.success(
            "✅ एक Destination environment variable/Streamlit Secrets से load हुआ है — यह restart/redeploy/"
            "sleep के बाद भी सुरक्षित रहेगा, Stream Key दोबारा डालने की ज़रूरत नहीं पड़ेगी।"
        )
    else:
        st.caption(
            "💡 स्थायी setup के लिए: Streamlit Cloud → Manage app → Settings → Secrets में "
            "`[youtube_live_destination]` के नीचे `stream_key = \"...\"` डालें — फिर Stream Key कभी नहीं मिटेगी।"
        )

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
                top1, top2, top3 = st.columns([2, 1.1, 0.7])
                dest["platform"] = top1.selectbox(
                    "Platform", options=PLATFORM_OPTIONS,
                    index=PLATFORM_OPTIONS.index(dest.get("platform", PLATFORM_OPTIONS[0])),
                    key=f"live_dest_platform_{idx}",
                )
                on_off_options = ["🟢 ON", "🔴 OFF"]
                current_choice = on_off_options[0] if dest.get("enabled", True) else on_off_options[1]
                chosen = top2.radio(
                    "स्थिति", options=on_off_options, index=on_off_options.index(current_choice),
                    key=f"live_dest_onoff_{idx}", horizontal=True, label_visibility="collapsed",
                )
                dest["enabled"] = (chosen == "🟢 ON")
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

                if dest.get("_source") in ("env", "secrets"):
                    st.caption(f"🔒 यह Stream Key {dest['_source']} से आई है — स्थायी है।")

                if not dest["enabled"]:
                    st.caption("🔴 यह destination पूरी तरह OFF है — बैकएंड इसे पूरी तरह इग्नोर करेगा, इससे कोई connection attempt भी नहीं होगी।")

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

    st.markdown("---")
    st.markdown("**🔁 Live Handover**")
    st.caption(
        "जब चालू करेंगे, तो Start Live पर ही camera को गर्म (warm-up) करके तैयार रखा जाएगा, ताकि Handover के "
        "समय कोई देरी न हो। यह सुविधा सिर्फ़ **इसी ऐप के अपने webcam/mic** के लिए काम करती है — OBS या YouTube "
        "Studio के अलग webcam को सीधे जोड़ना YouTube की तरफ़ से संभव नहीं है (देखें ऊपर की चेतावनी)।"
    )
    _set("enable_handover", st.checkbox(
        "🟢 Handover के लिए तैयार रखें (Enable Handover Standby)",
        value=_get("enable_handover"), key="live_enable_handover_checkbox",
        help="Cloud सर्वर पर physical camera नहीं होता — यह टॉगल तभी काम करेगा जब यह ऐप किसी ऐसी मशीन पर चल रहा हो जहाँ असली webcam/mic लगा हो।",
    ))

    if live_engine.is_streaming():
        handed_over = live_engine.is_handed_over()
        hc1, hc2, hc3 = st.columns([1.3, 1, 2])
        with hc1:
            if st.button("🎥 अभी Handover करें (Go to Webcam+Mic)", disabled=handed_over, key="live_handover_btn"):
                if live_engine.perform_live_handover():
                    st.session_state["live_studio"]["chat_messages"].append("System: 🎥 Handover हो गया — अब असली webcam/mic live है।")
                    st.success("✅ Handover सफल! RTMP connection वही पुराना चल रहा है, stream नहीं टूटी।")
                else:
                    st.error(f"❌ Handover नहीं हो पाया: {live_engine.get_last_error()}")
                st.rerun()
        with hc2:
            if st.button("↩️ वापस Media पर जाएँ", disabled=not handed_over, key="live_revert_handover_btn"):
                live_engine.revert_live_handover()
                st.session_state["live_studio"]["chat_messages"].append("System: ↩️ वापस media/bhajan पर आ गए।")
                st.rerun()
        with hc3:
            if handed_over:
                st.success("🎥 अभी LIVE HANDOVER मोड में है — असली webcam/mic चल रहा है।")
            else:
                st.info("⚪ अभी Media/Bhajan मोड में है।")


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
        enable_handover=_get("enable_handover"),
        media_items=_get_media_item_objects(),
        background_audio_path=_resolve_section2_playlist_path(),
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


# ---------------------------------------------------------------------------
# Schedule — sab kuch bharke, samay tay karke, browser band kar sakein
# ---------------------------------------------------------------------------
def _render_schedule_section():
    st.subheader("⏰ Schedule (तय समय पर अपने-आप Live शुरू/बंद)")
    st.caption(
        "ऊपर के सभी Section (Media, Audio, Mantra, Story, Ticker, Destinations) पहले भर दें, फिर यहाँ समय तय "
        "करके 'Schedule लगाएं' दबाएं — उसके बाद browser/laptop/mobile बंद कर सकते हैं, तय समय पर अपने आप "
        "live शुरू और बंद हो जाएगा।"
    )

    st.markdown("**🔁 Keep-Alive (एक बार सेट करें, फिर हमेशा अपने-आप चलेगा)**")
    st.caption(
        "अपने ऐप का पूरा public URL यहाँ एक बार डाल दें — Schedule लगाते ही (या Live शुरू करते ही) ऐप खुद "
        "हर 4 मिनट में अपने-आप को ping करता रहेगा, ताकि free hosting पर वह sleep में न जाए। किसी बाहरी "
        "service (UptimeRobot वगैरह) की अब ज़रूरत नहीं — बस नीचे URL डालकर Save करें, बाकी अपने-आप होगा।"
    )
    saved_url = _load_app_url()
    app_url = st.text_input(
        "आपके ऐप का पूरा URL", value=saved_url, key="schedule_app_url_input",
        placeholder="https://your-app.streamlit.app/",
    )
    if app_url != saved_url:
        _save_app_url(app_url)
    if app_url:
        if live_engine.is_keepalive_running():
            st.caption("🟢 Self-ping पहले से चल रहा है।")
        else:
            st.caption("⚪ Self-ping अभी बंद है — Schedule लगाते ही या Live शुरू करते ही अपने-आप चालू हो जाएगा।")
    else:
        st.caption(
            "⚠️ URL नहीं भरा है — बिना इसके free hosting पर लंबी unattended scheduling भरोसेमंद नहीं रहेगी, "
            "ऐप बीच में sleep हो सकता है और schedule कभी नहीं चलेगा।"
        )
    st.caption(
        "ℹ️ ईमानदारी से बता दूँ: यह best-effort तरीका है, 100% गारंटी नहीं — अगर ऐप पहले से पूरी तरह sleep हो "
        "चुका है तो कोई भी internal thread उसे खुद जगा नहीं सकता (वह process ही रुका हुआ है)। यह सिर्फ़ "
        "ऐप को sleep होने से **रोकता** है, नियमित रूप से खुद को active रखकर।"
    )

    schedule_status = live_engine.get_schedule_status()
    is_armed = bool(schedule_status and schedule_status.get("armed"))

    if is_armed:
        start_at = schedule_status.get("start_at")
        stop_at = schedule_status.get("stop_at")
        now_ts = datetime.now(IST).timestamp()

        if start_at:
            start_dt = datetime.fromtimestamp(start_at, IST)
            start_str = f"{start_dt.strftime('%d-%b')} {_format_time_readable(start_dt.time())}"
        else:
            start_str = "अभी"
        if stop_at:
            stop_dt = datetime.fromtimestamp(stop_at, IST)
            stop_str = f"{stop_dt.strftime('%d-%b')} {_format_time_readable(stop_dt.time())}"
        else:
            stop_str = "मैनुअल तक (कोई तय समय नहीं)"

        st.success(f"🟢 Schedule ARMED है — Start: **{start_str}**, Stop: **{stop_str}**")

        if start_at and start_at > now_ts and not schedule_status.get("fired_start"):
            remaining = int(start_at - now_ts)
            hours, remainder = divmod(remaining, 3600)
            minutes = remainder // 60
            st.info(f"⏳ ये हो प्रीती जी आपका Live अभी से **{hours} घंटे {minutes} मिनट** बाद शुरू होगा।")
        elif schedule_status.get("fired_start") and not schedule_status.get("fired_stop"):
            st.info("🔴 Live पहले से शुरू हो चुका है।")

        if start_at and stop_at:
            duration_sec = int(stop_at - start_at)
            d_hours, d_remainder = divmod(duration_sec, 3600)
            d_minutes = d_remainder // 60
            st.info(f"⏱️ यह Live कुल **{d_hours} घंटे {d_minutes} मिनट** तक चलेगा।")

        if st.button("❌ Schedule रद्द करें", key="schedule_cancel_btn"):
            live_engine.cancel_schedule()
            st.rerun()
        return

    now = datetime.now(IST)
    sc1, sc2 = st.columns(2)
    with sc1:
        start_date = st.date_input("शुरू होने की तारीख़", value=_get("schedule_start_date") or now.date(), key="sched_start_date")
        start_time_val = _time_picker_ampm(
            "शुरू होने का समय", "sched_start_time_picker",
            _get("schedule_start_time") or now.time().replace(second=0, microsecond=0),
        )
        _set("schedule_start_date", start_date)
        _set("schedule_start_time", start_time_val)

    with sc2:
        has_stop = st.checkbox("एक तय समय पर बंद भी हो जाए", value=_get("schedule_has_stop"), key="sched_has_stop")
        _set("schedule_has_stop", has_stop)
        if has_stop:
            stop_date = st.date_input("बंद होने की तारीख़", value=_get("schedule_stop_date") or now.date(), key="sched_stop_date")
            stop_time_val = _time_picker_ampm(
                "बंद होने का समय", "sched_stop_time_picker",
                _get("schedule_stop_time") or now.time().replace(second=0, microsecond=0),
            )
            _set("schedule_stop_date", stop_date)
            _set("schedule_stop_time", stop_time_val)
        else:
            st.caption("ℹ️ कोई stop समय नहीं — जब तक आप या YouTube Studio से मैनुअल बंद न करें, तब तक चलता रहेगा।")

    # -- शुरू होने में कितनी देर बाकी है + (अगर stop समय दिया हो तो) कुल कितनी देर चलेगा --
    start_dt_preview = datetime.combine(_get("schedule_start_date"), _get("schedule_start_time"), tzinfo=IST)
    delta_seconds = (start_dt_preview - now).total_seconds()
    if delta_seconds > 0:
        hours, remainder = divmod(int(delta_seconds), 3600)
        minutes = remainder // 60
        st.info(f"⏳ Schedule आपका Live अभी से **{hours} घंटे {minutes} मिनट** बाद शुरू होगा।")
    else:
        st.warning("⚠️ चुना गया शुरू होने का समय बीत चुका है — Schedule लगाते ही Live लगभग तुरंत शुरू हो जाएगा।")

    if _get("schedule_has_stop"):
        stop_dt_preview = datetime.combine(_get("schedule_stop_date"), _get("schedule_stop_time"), tzinfo=IST)
        duration_seconds = (stop_dt_preview - start_dt_preview).total_seconds()
        if duration_seconds > 0:
            d_hours, d_remainder = divmod(int(duration_seconds), 3600)
            d_minutes = d_remainder // 60
            st.info(f"⏱️ यह Live कुल **{d_hours} घंटे {d_minutes} मिनट** तक चलेगा।")

    enabled_dest_count = sum(1 for d in _get("destinations") if d.get("enabled") and _effective_rtmp_url(d))
    schedule_disabled = enabled_dest_count == 0 or _get("is_live") or not live_engine.check_ffmpeg_available()

    if st.button("📅 Schedule लगाएं", type="primary", disabled=schedule_disabled, key="schedule_set_btn"):
        start_dt = datetime.combine(_get("schedule_start_date"), _get("schedule_start_time"), tzinfo=IST)
        start_epoch = start_dt.timestamp()
        stop_epoch = None
        if _get("schedule_has_stop"):
            stop_dt = datetime.combine(_get("schedule_stop_date"), _get("schedule_stop_time"), tzinfo=IST)
            stop_epoch = stop_dt.timestamp()
            if stop_epoch <= start_epoch:
                st.error("❌ Stop समय, Start समय के बाद का होना चाहिए।")
                return

        with st.spinner("तैयारी हो रही है..."):
            config = _build_stream_config()
        if live_engine.schedule_stream(config, start_epoch, stop_epoch):
            if app_url:
                live_engine.start_keepalive(app_url)
            st.success("✅ Schedule लग गया! अब आप laptop/mobile बंद कर सकते हैं।")
            st.rerun()
        else:
            st.error(f"❌ Schedule नहीं लग पाया: {live_engine.get_last_error()}")

    if schedule_disabled and enabled_dest_count == 0:
        st.caption("⚠️ पहले ऊपर कम से कम एक destination enable करें और key भरें।")


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
            with st.spinner("तैयारी हो रही है (playlist जोड़ी जा रही है अगर ज़रूरत हो)..."):
                config = _build_stream_config()
            started = live_engine.start_stream(config)
            if started:
                _set("is_live", True)
                _set("_last_start_error", None)
                saved_app_url = _load_app_url()
                if saved_app_url:
                    live_engine.start_keepalive(saved_app_url)
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
            handover_tag = " · 🎥 Handover ON" if live_engine.is_handed_over() else " · 📺 Media मोड"
            st.success(f"🟢 LIVE — {uptime:.0f}s, {frames} frames{handover_tag}")
        else:
            st.info("⚪ Offline")

    if not _get("is_live") and enabled_dest_count == 0:
        st.caption("⚠️ ऊपर कम से कम एक destination enable करें।")


def _render_live_chat_feed():
    st.subheader("💬 Live Chat")
    st.caption(
        "यहाँ आप YouTube की असली Live Chat से जुड़ सकते हैं — पहली बार comment करने वालों को अपने-आप "
        "welcome-template भेजा जा सकता है, और चाहें तो comments इसी ऐप में Hindi में दिखेंगे।"
    )
    st.info(
        "💡 सिर्फ़ comments पढ़ने के लिए Hindi चाहिए (auto-welcome नहीं चाहिए) तो इसकी ज़रूरत नहीं — "
        "YouTube Studio का अपना Live Control Room खोलकर वहाँ account की भाषा Hindi रखें और "
        "'Automatic chat translation' ON करें, वह मुफ़्त में अपने-आप हो जाता है।"
    )

    if not live_chat_bridge.is_available():
        st.warning("⚠️ Terminal में चलाएँ: `pip install google-auth-oauthlib google-api-python-client deep-translator`")
        return

    if not live_chat_bridge.is_monitoring():
        youtube = live_chat_bridge.render_oauth_and_get_youtube_client(st)
        if youtube is None:
            return

        st.markdown("**पहली बार Comment करने वालों के लिए Welcome Template**")
        _set("chat_welcome_template", st.text_area(
            "Welcome Template (अपने मन से लिखें, symbols भी डाल सकते हैं 🙏🌺🔱)",
            value=_get("chat_welcome_template"), height=100, key="chat_welcome_template_input",
        ))
        cw1, cw2 = st.columns(2)
        with cw1:
            _set("chat_auto_welcome_enabled", st.checkbox(
                "🙏 पहली बार comment करने वालों को Auto-Welcome भेजें",
                value=_get("chat_auto_welcome_enabled"), key="chat_auto_welcome_checkbox",
            ))
        with cw2:
            _set("chat_translate_to_hindi", st.checkbox(
                "🇮🇳 Comments इसी ऐप में Hindi में दिखाएं (Auto-Translate)",
                value=_get("chat_translate_to_hindi"), key="chat_translate_checkbox",
            ))

        if st.button("🔌 Live Chat से जुड़ें", key="chat_connect_btn"):
            started = live_chat_bridge.start_chat_monitor(
                youtube, _get("chat_welcome_template"),
                _get("chat_auto_welcome_enabled"), _get("chat_translate_to_hindi"),
            )
            if started:
                st.success("✅ Live Chat से जुड़ गया!")
            else:
                st.error(f"❌ नहीं जुड़ पाया: {live_chat_bridge.get_monitor_error()}")
            st.rerun()
        return

    # -- connected: show live messages + controls --
    cc1, cc2, cc3 = st.columns([1, 1, 2])
    with cc1:
        if st.button("🔌 Disconnect", key="chat_disconnect_btn"):
            live_chat_bridge.stop_chat_monitor()
            st.rerun()
    with cc2:
        if st.button("♻️ 'पहली बार' याददाश्त रीसेट करें", key="chat_reset_seen_btn"):
            live_chat_bridge.reset_seen_commenters()
            st.success("✅ अब सबको फिर से 'पहली बार' माना जाएगा।")
    with cc3:
        st.success(f"🟢 Live Chat से जुड़ा है — अब तक {live_chat_bridge.get_welcomed_count()} लोगों को Welcome भेजा गया।")

    err = live_chat_bridge.get_monitor_error()
    if err:
        st.caption(f"⚠️ आख़िरी warning: {err}")

    chat_container = st.container(height=280, border=True)
    with chat_container:
        messages = live_chat_bridge.get_chat_messages()
        if not messages:
            st.caption("अभी कोई comment नहीं आया।")
        else:
            for msg in messages[-100:]:
                tag = " *(translated)*" if msg.get("translated") else ""
                st.write(f"**{msg['author']}:** {msg['text']}{tag}")

    with st.form(key="chat_manual_send_form", clear_on_submit=True):
        manual_text = st.text_input("Chat में मैनुअल मैसेज भेजें", key="chat_manual_send_input")
        if st.form_submit_button("भेजें") and manual_text:
            if live_chat_bridge.send_chat_message(manual_text):
                st.success("✅ भेज दिया।")
            else:
                st.error("❌ नहीं भेज पाया।")


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
    _render_schedule_section()

    st.divider()
    _render_control_buttons()

    st.divider()
    _render_live_chat_feed()

    st.divider()
    _render_config_summary()


if __name__ == "__main__":
    st.set_page_config(page_title="Live Broadcast Studio", page_icon="📡", layout="wide")
    render_live_studio_ui()
