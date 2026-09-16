"""
Baba Web Studio - 7-Track Video Editing Streamlit App
Production-ready app.py

Requires a sibling module `engine.py` exposing:
    engine.master_render_pipeline(payload: dict) -> str  # returns output file path

--------------------------------------------------------------------------
DEVANAGARI / HINDI TEXT RENDERING — IMPORTANT NOTE FOR `engine.py`
--------------------------------------------------------------------------
This app collects Hindi/Devanagari text (climax_text, ticker_text, subtitles)
as plain Python strings. Streamlit itself handles UTF-8 natively, so no
special handling is needed on the UI side. The risk is entirely on the
RENDER side (MoviePy / PIL), where Devanagari commonly breaks:

  - PIL's default ImageFont/ImageDraw text renderer does NOT shape
    conjuncts/matras correctly unless compiled with RAQM support
    (libraqm). Without RAQM, Hindi text renders as disconnected or
    broken glyph boxes (e.g. "क्ष", "ज्ञ", "स्तु" get mangled).
  - Windows' bundled fonts: use "Nirmala.ttf" (C:\\Windows\\Fonts\\Nirmala.ttf)
    or "Mangal.ttf" as the font file — NOT a generic sans-serif font,
    which usually has no Devanagari glyphs at all (renders as empty boxes).
  - RECOMMENDED FIX (most reliable): render all text (subtitles, ticker,
    climax card) as HTML/CSS via headless Chromium (Playwright) to a PNG
    with a transparent background, then composite that PNG onto the video
    frame with MoviePy. Chromium's text shaping engine handles Devanagari
    correctly out of the box, unlike PIL+RAQM on Windows.
  - If PIL must be used directly, ensure Pillow is installed with RAQM
    (`pip install pillow --break-system-packages` on a build with
    libraqm/harfbuzz present) and always pass `language="hi"` to
    ImageFont.getbbox / draw.text where supported.

`engine.py` should implement ONE of the two strategies above for every
Hindi string field in the payload (`track7.ticker_text`, `climax_text`,
and any Devanagari subtitle content from `track5.subtitle_path`).
--------------------------------------------------------------------------
"""

import os
import shutil
import tempfile
import traceback
from datetime import datetime

import streamlit as st

# --------------------------------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Baba Web Studio",
    page_icon="🎬",
    layout="wide",
)

# --------------------------------------------------------------------------
# CONSTANTS
# --------------------------------------------------------------------------
UPLOAD_ROOT = os.path.join(tempfile.gettempdir(), "baba_web_studio_uploads")
OUTPUT_ROOT = os.path.join(tempfile.gettempdir(), "baba_web_studio_outputs")
os.makedirs(UPLOAD_ROOT, exist_ok=True)
os.makedirs(OUTPUT_ROOT, exist_ok=True)

IMAGE_EXTS = (".jpg", ".jpeg", ".png")
VIDEO_EXTS = (".mp4",)

# --------------------------------------------------------------------------
# SESSION STATE DEFAULTS
# --------------------------------------------------------------------------
DURATION_PRESETS = {
    "30 Sec (Shorts Default)": 30,
    "5 Min": 300,
    "10 Min": 600,
    "30 Min": 1800,
    "Custom": None,
}

# Font configuration for Devanagari-safe text rendering. Passed straight
# into the payload so engine.py has a single source of truth instead of
# hardcoding font paths itself.
DEVANAGARI_FONT_CONFIG = {
    "language": "hi",
    "preferred_fonts": ["Nirmala.ttf", "Mangal.ttf", "NotoSansDevanagari-Regular.ttf"],
    "windows_font_dir": "C:\\Windows\\Fonts",
    "linux_font_candidates": [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    ],
    "render_method": "chromium_html",  # preferred: render text via headless Chromium (Playwright) to transparent PNG, then composite with MoviePy
    "pil_raqm_required": True,         # if falling back to PIL, Pillow MUST be built with libraqm or Devanagari conjuncts/matras will break
}

DEFAULTS = {
    "ratio": "Shorts (9:16)",
    "duration_preset": "30 Sec (Shorts Default)",
    "custom_minutes": 0,
    "custom_seconds": 30,
    "video_duration": 30,         # computed total seconds, always kept in sync
    "enable_climax": True,
    "climax_duration": 10,
    "climax_text": "धन्यवाद! लाइक और सब्सक्राइब करें",
    "track1_files": [],          # list[dict]: {name, path, type, order, start_sec, end_sec}
    "t1_def_dur": 5,
    "t1_ken_burns": True,
    "track2_audio_path": None,
    "track2_volume": 100,
    "track3_bgm_path": None,
    "track3_volume": 20,
    "track3_loop": True,
    "track4_sfx": [],            # list[dict]: {name, path, trigger_sec}
    "track5_subtitle_path": None,
    "track5_font_color": "#FFFFFF",
    "track5_font_size": 40,
    "track6_watermark_path": None,
    "track6_position": "Bottom Right",
    "ticker_text": "बाबा वेब स्टूडियो — प्रोफेशनल वीडियो एडिटिंग के लिए संपर्क करें",
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


def clear_uploads():
    """Wipe the temp upload dir (called on full reset)."""
    shutil.rmtree(UPLOAD_ROOT, ignore_errors=True)
    os.makedirs(UPLOAD_ROOT, exist_ok=True)


def sync_track1_files(uploaded_files):
    """
    Reconcile newly uploaded files with existing track1_files state,
    preserving per-file sequence/trim settings already entered by the user.
    """
    if not uploaded_files:
        return

    existing_names = {f["name"] for f in st.session_state.track1_files}
    next_order = len(st.session_state.track1_files) + 1

    for uf in uploaded_files:
        if uf.name in existing_names:
            continue  # already tracked, don't duplicate or reset its settings
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
            }
        )
        next_order += 1


# --------------------------------------------------------------------------
# HEADER
# --------------------------------------------------------------------------
st.title("🎬 Baba Web Studio")
st.caption("7-Track Video Editor")

header_col1, header_col2 = st.columns(2)
with header_col1:
    st.session_state.ratio = st.selectbox(
        "Video Ratio",
        options=["Shorts (9:16)", "Long (16:9)"],
        index=["Shorts (9:16)", "Long (16:9)"].index(st.session_state.ratio),
    )

with header_col2:
    st.session_state.duration_preset = st.selectbox(
        "Target Duration",
        options=list(DURATION_PRESETS.keys()),
        index=list(DURATION_PRESETS.keys()).index(st.session_state.duration_preset),
        key="duration_preset_select",
    )

if st.session_state.duration_preset == "Custom":
    custom_col1, custom_col2 = st.columns(2)
    with custom_col1:
        st.session_state.custom_minutes = st.number_input(
            "Minutes",
            min_value=0,
            value=int(st.session_state.custom_minutes),
            step=1,
            key="custom_minutes_input",
        )
    with custom_col2:
        st.session_state.custom_seconds = st.number_input(
            "Seconds",
            min_value=0,
            max_value=59,
            value=int(st.session_state.custom_seconds),
            step=1,
            key="custom_seconds_input",
        )
    st.session_state.video_duration = (
        int(st.session_state.custom_minutes) * 60 + int(st.session_state.custom_seconds)
    )
else:
    st.session_state.video_duration = DURATION_PRESETS[st.session_state.duration_preset]

st.caption(f"Total target duration: **{st.session_state.video_duration} sec**")

st.markdown("**Climax / Outro Settings**")
climax_col1, climax_col2 = st.columns([1, 2])
with climax_col1:
    st.session_state.enable_climax = st.checkbox(
        "Append Climax / Outro Card",
        value=st.session_state.enable_climax,
        key="climax_toggle",
    )
with climax_col2:
    if st.session_state.enable_climax:
        st.session_state.climax_duration = st.number_input(
            "Climax Card Duration (sec)",
            min_value=1,
            value=int(st.session_state.climax_duration),
            step=1,
            key="climax_duration_input",
        )

if st.session_state.enable_climax:
    st.session_state.climax_text = st.text_input(
        "Climax Text",
        value=st.session_state.climax_text,
        key="climax_text_input",
    )

st.divider()

# --------------------------------------------------------------------------
# TRACK 1 - MANDATORY VISUALS LAYER
# --------------------------------------------------------------------------
st.subheader("Track 1 — Visuals Layer (Mandatory)")

uploaded_track1 = st.file_uploader(
    "Upload Images / Videos",
    type=["jpg", "jpeg", "png", "mp4"],
    accept_multiple_files=True,
    key="t1_uploader",
)
sync_track1_files(uploaded_track1)

t1_col1, t1_col2 = st.columns(2)
with t1_col1:
    st.session_state.t1_def_dur = st.number_input(
        "Default Image Duration (sec)",
        min_value=1,
        value=int(st.session_state.t1_def_dur),
        step=1,
        key="t1_def_dur_input",
    )
with t1_col2:
    st.session_state.t1_ken_burns = st.toggle(
        "Ken Burns Effect (Images)",
        value=st.session_state.t1_ken_burns,
        key="t1_ken_burns_toggle",
    )

if st.session_state.track1_files:
    st.markdown("**Sequence & Trim**")
    for idx, item in enumerate(st.session_state.track1_files):
        cols = st.columns([3, 1, 1, 1, 1])
        cols[0].write(f"{item['name']}  `({item['type']})`")
        item["order"] = cols[1].number_input(
            "Order",
            min_value=1,
            value=int(item["order"]),
            step=1,
            key=f"t1_order_{idx}",
            label_visibility="collapsed",
        )
        if item["type"] == "video":
            item["start_sec"] = cols[2].number_input(
                "Start Sec",
                min_value=0.0,
                value=float(item["start_sec"]),
                step=0.5,
                key=f"t1_start_{idx}",
                label_visibility="collapsed",
            )
            item["end_sec"] = cols[3].number_input(
                "End Sec",
                min_value=0.0,
                value=float(item["end_sec"]),
                step=0.5,
                key=f"t1_end_{idx}",
                label_visibility="collapsed",
            )
        else:
            cols[2].write("—")
            cols[3].write("—")
        if cols[4].button("Remove", key=f"t1_remove_{idx}"):
            st.session_state.track1_files.pop(idx)
            st.rerun()

    # keep list sorted by user-defined order for payload construction
    st.session_state.track1_files.sort(key=lambda f: f["order"])
else:
    st.info("Track 1 mein kam se kam ek file upload karna zaroori hai.")

st.divider()

# --------------------------------------------------------------------------
# TRACK 2 - VOICEOVER / AUDIO
# --------------------------------------------------------------------------
with st.expander("Track 2 — Voiceover / Audio"):
    t2_file = st.file_uploader(
        "Upload Voiceover Audio", type=["mp3", "wav", "m4a"], key="t2_uploader"
    )
    if t2_file is not None:
        st.session_state.track2_audio_path = save_uploaded_file(t2_file, "track2")
    st.session_state.track2_volume = st.slider(
        "Voiceover Volume (%)", 0, 100, int(st.session_state.track2_volume), key="t2_vol"
    )

# --------------------------------------------------------------------------
# TRACK 3 - BACKGROUND MUSIC
# --------------------------------------------------------------------------
with st.expander("Track 3 — Background Music"):
    t3_file = st.file_uploader(
        "Upload BGM", type=["mp3", "wav", "m4a"], key="t3_uploader"
    )
    if t3_file is not None:
        st.session_state.track3_bgm_path = save_uploaded_file(t3_file, "track3")
    t3_col1, t3_col2 = st.columns(2)
    with t3_col1:
        st.session_state.track3_volume = st.slider(
            "BGM Volume (%)", 0, 100, int(st.session_state.track3_volume), key="t3_vol"
        )
    with t3_col2:
        st.session_state.track3_loop = st.checkbox(
            "Loop BGM", value=st.session_state.track3_loop, key="t3_loop"
        )

# --------------------------------------------------------------------------
# TRACK 4 - SOUND EFFECTS
# --------------------------------------------------------------------------
with st.expander("Track 4 — Sound Effects"):
    t4_files = st.file_uploader(
        "Upload SFX (multiple allowed)",
        type=["mp3", "wav"],
        accept_multiple_files=True,
        key="t4_uploader",
    )
    if t4_files:
        existing_sfx_names = {s["name"] for s in st.session_state.track4_sfx}
        for sf in t4_files:
            if sf.name not in existing_sfx_names:
                st.session_state.track4_sfx.append(
                    {"name": sf.name, "path": save_uploaded_file(sf, "track4"), "trigger_sec": 0.0}
                )

    for idx, sfx in enumerate(st.session_state.track4_sfx):
        cols = st.columns([3, 2, 1])
        cols[0].write(sfx["name"])
        sfx["trigger_sec"] = cols[1].number_input(
            "Trigger at (sec)",
            min_value=0.0,
            value=float(sfx["trigger_sec"]),
            step=0.5,
            key=f"t4_trigger_{idx}",
            label_visibility="collapsed",
        )
        if cols[2].button("Remove", key=f"t4_remove_{idx}"):
            st.session_state.track4_sfx.pop(idx)
            st.rerun()

# --------------------------------------------------------------------------
# TRACK 5 - SCRIPT / SUBTITLES
# --------------------------------------------------------------------------
with st.expander("Track 5 — Script / Subtitles"):
    t5_file = st.file_uploader(
        "Upload SRT or Text File", type=["srt", "txt"], key="t5_uploader"
    )
    if t5_file is not None:
        st.session_state.track5_subtitle_path = save_uploaded_file(t5_file, "track5")
    t5_col1, t5_col2 = st.columns(2)
    with t5_col1:
        st.session_state.track5_font_color = st.color_picker(
            "Font Color", value=st.session_state.track5_font_color, key="t5_color"
        )
    with t5_col2:
        st.session_state.track5_font_size = st.number_input(
            "Font Size",
            min_value=10,
            value=int(st.session_state.track5_font_size),
            step=2,
            key="t5_size",
        )

# --------------------------------------------------------------------------
# TRACK 6 - OVERLAYS / WATERMARK
# --------------------------------------------------------------------------
with st.expander("Track 6 — Overlays / Watermark"):
    t6_file = st.file_uploader(
        "Upload Logo / Watermark (PNG)", type=["png"], key="t6_uploader"
    )
    if t6_file is not None:
        st.session_state.track6_watermark_path = save_uploaded_file(t6_file, "track6")
    st.session_state.track6_position = st.selectbox(
        "Position",
        options=["Top Left", "Top Right", "Bottom Left", "Bottom Right", "Center"],
        index=["Top Left", "Top Right", "Bottom Left", "Bottom Right", "Center"].index(
            st.session_state.track6_position
        ),
        key="t6_position_select",
    )

# --------------------------------------------------------------------------
# TRACK 7 - OUTRO / TICKER
# --------------------------------------------------------------------------
with st.expander("Track 7 — Outro / Ticker"):
    st.session_state.ticker_text = st.text_input(
        "Bottom Scrolling Ticker Text",
        value=st.session_state.ticker_text,
        key="t7_ticker_input",
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
        }
        for f in sorted(st.session_state.track1_files, key=lambda x: x["order"])
    ] if st.session_state.track1_files else []

    payload = {
        "ratio": st.session_state.ratio,
        "is_shorts": st.session_state.ratio == "Shorts (9:16)",
        "duration": int(st.session_state.video_duration),
        "is_draft": bool(is_draft),
        "enable_climax": bool(st.session_state.enable_climax),
        "climax_duration": int(st.session_state.climax_duration) if st.session_state.enable_climax else 0,
        "climax_text": st.session_state.climax_text if st.session_state.enable_climax else "",
        "font_config": DEVANAGARI_FONT_CONFIG,
        "track1": {
            "files": t1_files_list,          # never None
            "default_image_duration": int(st.session_state.t1_def_dur),
            "ken_burns": bool(st.session_state.t1_ken_burns),
        },
        "track2": {
            "audio_path": st.session_state.track2_audio_path,
            "volume": int(st.session_state.track2_volume),
        },
        "track3": {
            "bgm_path": st.session_state.track3_bgm_path,
            "volume": int(st.session_state.track3_volume),
            "loop": bool(st.session_state.track3_loop),
        },
        "track4": {
            "sfx": [
                {"path": s["path"], "trigger_sec": float(s["trigger_sec"])}
                for s in st.session_state.track4_sfx
            ] if st.session_state.track4_sfx else [],
        },
        "track5": {
            "subtitle_path": st.session_state.track5_subtitle_path,
            "font_color": st.session_state.track5_font_color,
            "font_size": int(st.session_state.track5_font_size),
        },
        "track6": {
            "watermark_path": st.session_state.track6_watermark_path,
            "position": st.session_state.track6_position,
        },
        "track7": {
            "ticker_text": st.session_state.ticker_text or "",
        },
    }
    return payload


def run_render(is_draft: bool):
    if not st.session_state.track1_files:
        st.error("Render se pehle Track 1 mein kam se kam ek image ya video upload karein.")
        return

    payload = build_payload(is_draft)
    st.session_state.is_rendering = True

    try:
        with st.spinner(
            "Quick Draft render ho raha hai..." if is_draft else "Final 1080p render ho raha hai... isme kuch samay lag sakta hai."
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
    if st.button("🎬 Final Video Render (1080p)", use_container_width=True, type="primary", disabled=st.session_state.is_rendering):
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
