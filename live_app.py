"""
live_app.py
Standalone Streamlit UI module for a Live Broadcast Studio.

This module is isolated from app.py and exposes a single entry point,
render_live_studio_ui(), which can be imported and called from app.py:

    from live_app import render_live_studio_ui
    render_live_studio_ui()

All configuration inputs are persisted in st.session_state under the
"live_studio" namespace so state survives Streamlit reruns.

--------------------------------------------------------------------------
WHAT CHANGED IN THIS VERSION (found while reviewing the original file)
--------------------------------------------------------------------------
(1) THE START/STOP BUTTONS DID NOTHING REAL - they only flipped a local
    session-state flag. They now build a real live_engine.StreamConfig
    from everything configured on screen and call
    live_engine.start_stream() / stop_stream(); the ticker box now also
    calls live_engine.update_live_ticker() live while broadcasting.

(2) ONLY ONE PLATFORM COULD EVER BE CONFIGURED - live_engine.py has
    always supported pushing to multiple RTMP destinations at once, but
    the UI only exposed a single platform+key pair. There is now a
    destinations list (like Track 2/6 in the video-generator side of
    this project) so YouTube + Facebook + a Custom RTMP can all be
    enabled simultaneously.

(3) UPLOADED FILES NEVER REACHED THE ENGINE - live_engine works with
    filesystem paths, but the UI was handing it raw Streamlit
    UploadedFile objects (custom_bg_image, media_loop_file), which
    live_engine can't open. _save_uploaded_file() now persists them to
    disk and only the path is stored/used from then on.

(4) NO WAY TO SEND REAL AUDIO - added a background-audio-loop uploader
    (e.g. a bhajan/music track for audio-only broadcasts) and a
    "Include Mic Audio" toggle, both wired to the new
    background_audio_path / mic_enabled fields on StreamConfig.

(5) NO PRE-FLIGHT / LIVE STATUS CHECK - added an ffmpeg-availability
    check shown up front, and the Live Controls section now reflects
    live_engine.get_stream_status() instead of trusting the local
    session flag blindly (so a crashed engine doesn't keep showing
    "LIVE" forever).
--------------------------------------------------------------------------
"""

import os
import tempfile
from datetime import datetime

import streamlit as st

import live_engine
from live_engine import Destination, StreamConfig


UPLOAD_ROOT = os.path.join(tempfile.gettempdir(), "live_studio_uploads")
os.makedirs(UPLOAD_ROOT, exist_ok=True)

PLATFORM_RTMP_HINTS = {
    "YouTube": "rtmp://a.rtmp.youtube.com/live2/YOUR-STREAM-KEY",
    "Facebook": "rtmps://live-api-s.facebook.com:443/rtmp/YOUR-STREAM-KEY",
    "Instagram": "rtmps://live-upload.instagram.com:443/rtmp/YOUR-STREAM-KEY",
    "Custom RTMP": "rtmp://your-server/app/YOUR-STREAM-KEY",
}
PLATFORM_OPTIONS = list(PLATFORM_RTMP_HINTS.keys())


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

DEFAULT_STATE = {
    # Track 1 - Destinations (multi-platform, replaces the old single platform+key pair)
    "destinations": [],  # [{platform, rtmp_url, enabled}]
    # Camera / audio
    "webcam_on": True,
    "bg_removal": "None",
    "custom_bg_image_path": None,
    "custom_bg_image_name": None,
    "mic_enabled": False,
    # Media & overlay
    "media_loop_path": None,       # looping background VIDEO (webcam-off mode)
    "media_loop_name": None,
    "bg_audio_loop_path": None,    # looping background AUDIO/music (e.g. bhajan)
    "bg_audio_loop_name": None,
    "ticker_text": "",
    "pip_position": "Bottom-Right",
    # Live state
    "is_live": False,
    "chat_messages": [],
}

_POSITION_UI_TO_ENGINE = {
    "Bottom-Right": "bottom-right",
    "Bottom-Left": "bottom-left",
    "Top-Right": "top-right",
}
_BG_MODE_UI_TO_ENGINE = {
    "None": "none",
    "Blur": "blur",
    "Virtual Newsroom": "virtual",
    "Custom Image Upload": "virtual",
    "Green Screen": "green_screen",
}


def _init_session_state():
    """Ensure every config key exists in st.session_state before first use."""
    if "live_studio" not in st.session_state:
        st.session_state["live_studio"] = {k: (v.copy() if isinstance(v, list) else v) for k, v in DEFAULT_STATE.items()}
    else:
        for key, default_value in DEFAULT_STATE.items():
            st.session_state["live_studio"].setdefault(key, default_value)


def _set(key, value):
    st.session_state["live_studio"][key] = value


def _get(key):
    return st.session_state["live_studio"].get(key, DEFAULT_STATE.get(key))


def _save_uploaded_file(uploaded_file, subfolder: str) -> str:
    """Persist an in-memory UploadedFile to disk and return its path.
    live_engine works with filesystem paths, not UploadedFile objects."""
    target_dir = os.path.join(UPLOAD_ROOT, subfolder)
    os.makedirs(target_dir, exist_ok=True)
    safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{uploaded_file.name}"
    target_path = os.path.join(target_dir, safe_name)
    with open(target_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return target_path


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_stream_setup():
    st.subheader("🎥 Stream Setup — Destinations")
    st.caption(
        "एक से ज़्यादा platform एक साथ चुन सकते हैं — सबको एक ही स्ट्रीम एक साथ भेजी जाएगी "
        "(single-encode, multi-destination push)।"
    )

    if not live_engine.check_ffmpeg_available():
        st.error("⚠️ `ffmpeg` इस सिस्टम के PATH में नहीं मिला — Live जाने से पहले इसे इंस्टॉल करें।")

    if st.button("➕ नया Destination जोड़ें", key="live_add_dest_btn"):
        st.session_state["live_studio"]["destinations"].append(
            {"platform": PLATFORM_OPTIONS[0], "rtmp_url": "", "enabled": True}
        )
        st.rerun()

    if not _get("destinations"):
        st.caption("ℹ️ अभी कोई destination नहीं जोड़ा गया — ऊपर बटन से एक जोड़ें (YouTube/Facebook/Instagram/Custom RTMP)।")
    else:
        for idx, dest in enumerate(_get("destinations")):
            d_col1, d_col2, d_col3, d_col4 = st.columns([1.2, 3, 0.6, 0.6])
            dest["platform"] = d_col1.selectbox(
                "Platform", options=PLATFORM_OPTIONS, index=PLATFORM_OPTIONS.index(dest.get("platform", PLATFORM_OPTIONS[0])),
                key=f"live_dest_platform_{idx}", label_visibility="collapsed",
            )
            dest["rtmp_url"] = d_col2.text_input(
                "RTMP URL", value=dest.get("rtmp_url", ""), type="password",
                placeholder=PLATFORM_RTMP_HINTS.get(dest["platform"], "rtmp://..."),
                key=f"live_dest_url_{idx}", label_visibility="collapsed",
            )
            dest["enabled"] = d_col3.checkbox("On", value=dest.get("enabled", True), key=f"live_dest_enabled_{idx}")
            if d_col4.button("🗑️", key=f"live_dest_remove_{idx}"):
                st.session_state["live_studio"]["destinations"].pop(idx)
                st.rerun()

        enabled_count = sum(1 for d in _get("destinations") if d.get("enabled") and (d.get("rtmp_url") or "").strip())
        if enabled_count == 0:
            st.warning("⚠️ कम से कम एक destination को enable करें और उसका RTMP URL/key भरें।")
        else:
            st.success(f"✅ {enabled_count} destination(s) live जाने के लिए तैयार हैं।")


def _render_camera_audio_controls():
    st.subheader("📷 Camera & Audio")
    col1, col2 = st.columns(2)

    with col1:
        webcam_on = st.toggle(
            "Webcam",
            value=_get("webcam_on"),
            key="live_studio_webcam_toggle",
            help="When OFF, the stream goes audio-only with background visuals.",
        )
        _set("webcam_on", webcam_on)
        st.caption("🟢 Webcam ON — camera feed active" if webcam_on else "⚪ Webcam OFF — audio-only mode")

        mic_enabled = st.toggle(
            "🎙️ माइक ऑडियो शामिल करें (Include Mic Audio)",
            value=_get("mic_enabled"),
            key="live_studio_mic_toggle",
            help="असली माइक्रोफ़ोन ऑडियो कैप्चर करके स्ट्रीम में भेजेगा (sounddevice library चाहिए)।",
        )
        _set("mic_enabled", mic_enabled)
        if mic_enabled and _get("bg_audio_loop_path"):
            st.caption("ℹ️ Mic aur background music दोनों सेट हैं — फ़िलहाल background music को प्राथमिकता मिलेगी (नीचे देखें)।")

    with col2:
        bg_removal = st.selectbox(
            "AI Background Removal",
            options=["None", "Blur", "Virtual Newsroom", "Custom Image Upload", "Green Screen"],
            index=["None", "Blur", "Virtual Newsroom", "Custom Image Upload", "Green Screen"].index(_get("bg_removal")),
            key="live_studio_bg_removal_select",
            disabled=not webcam_on,
        )
        _set("bg_removal", bg_removal)

        if bg_removal == "Custom Image Upload" and webcam_on:
            custom_bg = st.file_uploader(
                "Upload custom background image",
                type=["png", "jpg", "jpeg"],
                key="live_studio_custom_bg_uploader",
            )
            if custom_bg is not None:
                path = _save_uploaded_file(custom_bg, "bg_image")
                _set("custom_bg_image_path", path)
                _set("custom_bg_image_name", custom_bg.name)
            if _get("custom_bg_image_name"):
                st.caption(f"✅ बैकग्राउंड सेट है: {_get('custom_bg_image_name')}")


def _render_media_overlay_settings():
    st.subheader("🖼️ Media & Overlay Settings")

    st.markdown("**🎬 बैकग्राउंड वीडियो लूप (Webcam OFF होने पर इस्तेमाल होगा)**")
    media_loop_file = st.file_uploader(
        "Background Video Loop (MP4)",
        type=["mp4", "mov"],
        key="live_studio_media_loop_uploader",
        help="Webcam OFF होने पर यह वीडियो लगातार Loop होकर बैकग्राउंड की तरह चलेगा।",
    )
    if media_loop_file is not None:
        path = _save_uploaded_file(media_loop_file, "media_loop")
        _set("media_loop_path", path)
        _set("media_loop_name", media_loop_file.name)
    if _get("media_loop_name"):
        st.caption(f"✅ बैकग्राउंड वीडियो लूप सेट है: {_get('media_loop_name')}")

    st.markdown("**🎵 बैकग्राउंड म्यूज़िक/भजन लूप (असली ऑडियो के लिए)**")
    st.caption(
        "यह अपलोड की गई म्यूज़िक फ़ाइल लगातार Loop होकर स्ट्रीम के ऑडियो में जाएगी — बिना pre-processing के, "
        "FFmpeg खुद इसे loop करता है। Mic ऑडियो के साथ अभी एक समय पर सिर्फ़ एक ही ऑडियो स्रोत active रहता है — "
        "अगर यह सेट है तो Mic टॉगल अनदेखा हो जाएगा।"
    )
    bg_audio_file = st.file_uploader(
        "Background Music/Bhajan Loop (MP3/WAV)",
        type=["mp3", "wav", "m4a"],
        key="live_studio_bg_audio_uploader",
    )
    if bg_audio_file is not None:
        path = _save_uploaded_file(bg_audio_file, "bg_audio")
        _set("bg_audio_loop_path", path)
        _set("bg_audio_loop_name", bg_audio_file.name)
    if _get("bg_audio_loop_name"):
        bc1, bc2 = st.columns([3, 1])
        bc1.success(f"✅ बैकग्राउंड म्यूज़िक लूप सेट है: {_get('bg_audio_loop_name')}")
        if bc2.button("हटाएं", key="live_bg_audio_remove_btn"):
            _set("bg_audio_loop_path", None)
            _set("bg_audio_loop_name", None)
            st.rerun()

    st.markdown("**📜 Live Ticker Text**")
    ticker_text = st.text_input(
        "Live Ticker Text",
        value=_get("ticker_text"),
        placeholder="Breaking news scrolls across the bottom of the screen...",
        key="live_studio_ticker_input",
    )
    _set("ticker_text", ticker_text)
    if ticker_text != st.session_state["live_studio"].get("_last_pushed_ticker") and live_engine.is_streaming():
        live_engine.update_live_ticker(ticker_text)
        st.session_state["live_studio"]["_last_pushed_ticker"] = ticker_text
        st.caption("🔄 Ticker live अपडेट हो गया।")

    pip_position = st.selectbox(
        "PIP Position (Picture-in-Picture for camera feed)",
        options=["Bottom-Right", "Bottom-Left", "Top-Right"],
        index=["Bottom-Right", "Bottom-Left", "Top-Right"].index(_get("pip_position")),
        key="live_studio_pip_position_select",
        disabled=not _get("webcam_on"),
    )
    _set("pip_position", pip_position)
    if live_engine.is_streaming():
        live_engine.update_live_background(_BG_MODE_UI_TO_ENGINE.get(_get("bg_removal"), "none"), _get("custom_bg_image_path"))


def _build_stream_config() -> StreamConfig:
    destinations = [
        Destination(platform=d["platform"], rtmp_url=d["rtmp_url"], enabled=d["enabled"])
        for d in _get("destinations")
    ]
    return StreamConfig(
        destinations=destinations,
        webcam_on=_get("webcam_on"),
        background_mode=_BG_MODE_UI_TO_ENGINE.get(_get("bg_removal"), "none"),
        virtual_bg_path=_get("custom_bg_image_path"),
        background_media_path=_get("media_loop_path") if not _get("webcam_on") else None,
        background_audio_path=_get("bg_audio_loop_path"),
        mic_enabled=_get("mic_enabled") and not _get("bg_audio_loop_path"),
        ticker_text=_get("ticker_text"),
        pip_position=_POSITION_UI_TO_ENGINE.get(_get("pip_position"), "bottom-right"),
    )


def _render_control_buttons():
    st.subheader("🎬 Live Controls")

    # Trust the real engine status over the local flag, so a crashed
    # engine doesn't keep showing "LIVE" forever.
    engine_status = live_engine.get_stream_status()
    actually_live = live_engine.is_streaming() and bool(engine_status and engine_status.get("publisher_alive"))
    if _get("is_live") != actually_live:
        _set("is_live", actually_live)

    enabled_dest_count = sum(1 for d in _get("destinations") if d.get("enabled") and (d.get("rtmp_url") or "").strip())
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        start_disabled = _get("is_live") or enabled_dest_count == 0 or not live_engine.check_ffmpeg_available()
        if st.button("🔴 START LIVE BROADCAST", type="primary", disabled=start_disabled, use_container_width=True):
            config = _build_stream_config()
            started = live_engine.start_stream(config)
            if started:
                _set("is_live", True)
                st.session_state["live_studio"]["_last_pushed_ticker"] = _get("ticker_text")
                st.session_state["live_studio"]["chat_messages"].append("System: Broadcast started.")
            else:
                st.session_state["live_studio"]["chat_messages"].append(
                    "System: ⚠️ Broadcast start नहीं हो पाया — logs देखें (ffmpeg / destinations चेक करें)."
                )
            st.rerun()

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
            st.success(f"🟢 LIVE — Broadcasting now ({uptime:.0f}s, {frames} frames)")
        else:
            st.info("⚪ Offline — not currently streaming")

    if not _get("is_live"):
        if enabled_dest_count == 0:
            st.caption("⚠️ ऊपर कम से कम एक destination enable करें और RTMP URL भरें।")
        elif not live_engine.check_ffmpeg_available():
            st.caption("⚠️ ffmpeg इंस्टॉल नहीं है — Start बटन तब तक बंद रहेगा।")


def _render_live_chat_feed():
    st.subheader("💬 Live Chat Feed")
    st.caption(
        "ℹ️ यह अभी एक लोकल डेमो चैट है (आपके अपने भेजे मैसेज दिखाती है)। असली YouTube/Facebook लाइव कमेंट्स "
        "दिखाने के लिए उन प्लेटफ़ॉर्म के अपने API/OAuth से जोड़ना होगा — वह इस मॉड्यूल के दायरे से बाहर है।"
    )
    chat_container = st.container(height=250, border=True)

    with chat_container:
        messages = st.session_state["live_studio"]["chat_messages"]
        if not messages:
            st.caption("No messages yet. Chat will appear here once you go live.")
        else:
            for msg in messages:
                st.write(msg)

    with st.form(key="live_studio_chat_form", clear_on_submit=True):
        new_message = st.text_input("Send a message to chat", key="live_studio_chat_input")
        submitted = st.form_submit_button("Send")
        if submitted and new_message:
            st.session_state["live_studio"]["chat_messages"].append(f"You: {new_message}")
            st.rerun()


def _render_config_summary():
    with st.expander("🔧 Current Configuration (session state)"):
        state_copy = dict(st.session_state["live_studio"])
        # Don't dump raw RTMP keys/secrets into the UI.
        safe_destinations = []
        for d in state_copy.get("destinations", []):
            safe_destinations.append({
                "platform": d.get("platform"),
                "rtmp_url": ("•" * 10) if d.get("rtmp_url") else "",
                "enabled": d.get("enabled"),
            })
        state_copy["destinations"] = safe_destinations
        st.json(state_copy)

        status = live_engine.get_stream_status()
        if status:
            st.caption("Engine status:")
            st.json(status)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_live_studio_ui():
    """
    Render the full Live Broadcast Studio UI.

    Call this from app.py (or run this file directly with `streamlit run`)
    to display the stream setup, camera/audio controls, media & overlay
    settings, live control buttons, and chat feed.
    """
    _init_session_state()

    st.title("📡 Live Broadcast Studio")
    st.caption("Configure and control your live stream — independent of the main app.")

    st.divider()
    _render_stream_setup()

    st.divider()
    _render_camera_audio_controls()

    st.divider()
    _render_media_overlay_settings()

    st.divider()
    _render_control_buttons()

    st.divider()
    _render_live_chat_feed()

    st.divider()
    _render_config_summary()


# ---------------------------------------------------------------------------
# Allow standalone execution: `streamlit run live_app.py`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    st.set_page_config(page_title="Live Broadcast Studio", page_icon="📡", layout="wide")
    render_live_studio_ui()
