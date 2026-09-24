# -*- coding: utf-8 -*-
"""
music_studio.py - Baba Web Studio | Music Production Module (UI)
=========================================================================
Streamlit UI jo music_engine.py ke upar baitha hai. Isse app.py ke
sidebar mode-selector mein ek chauthe option ki tarah jod sakte hain:

    app_mode = st.sidebar.radio(
        "Select Mode",
        ["🎬 Video Generator", "🔴 Live Broadcast Studio",
         "📊 Business Dashboard", "🎼 Music Studio"],   # <-- naya
    )
    ...
    elif app_mode == "🎼 Music Studio":
        render_music_studio_ui()

Yeh app.py ke password-gate ke ANDAR hi chalega (jaisa baaki modes chalte
hain), isliye yahan alag se password check nahi hai.

TABS
-----------------------------------------------------------------------
1. ✍️ Compose (script likhna / example load karna / render karna)
2. 👁️ MIDI Viewer (per-track piano-roll, taaki dekh sakein kya set hua)
3. 📤 Export (WAV audio + .mid file download, aur render karke seedha
   Baba Web Studio ke Track 3/Track 5 mein use karne ka pointer)
"""

import os
import io
import tempfile
import traceback
from datetime import datetime

import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

import music_engine as me


UPLOAD_ROOT = os.path.join(tempfile.gettempdir(), "music_studio_renders")
os.makedirs(UPLOAD_ROOT, exist_ok=True)

EXAMPLE_SCRIPT = """taal: dadra
tempo: 80
cycles: 4

track: tabla
pattern: dadra

track: bansuri
notes: sa re ga ma pa | pa ma ga re sa
octave: middle

track: guitar_pad
chord: C, C, Am, Am | F, F, G, G

track: harmonium
notes: sa ga ma pa ni sa'
"""

MANTRA_EXAMPLE_SCRIPT = """taal: kaharwa
tempo: 65
cycles: 4

track: tabla
pattern: kaharwa

track: harmonium
notes: sa , ni , sa re | ga ma ga re sa , ni ,

track: bansuri
notes: sa re ga ma | pa ma ga re
octave: middle
"""

TRACK_COLORS = {
    "tabla": "#c0392b",
    "bansuri": "#27ae60",
    "flute": "#27ae60",
    "harmonium": "#e67e22",
    "guitar_pad": "#2980b9",
    "guitar": "#2980b9",
    "sitar": "#8e44ad",
}

DEFAULTS = {
    "music_script_text": EXAMPLE_SCRIPT,
    "music_composition": None,
    "music_audio": None,
    "music_wav_path": None,
    "music_midi_path": None,
    "music_parse_error": None,
    "music_last_rendered_script": None,
}


def _init_state():
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _render_compose_tab():
    st.subheader("✍️ Compose — taal/sargam text script")
    st.caption(
        "Har line ek setting ya ek track batati hai. Taal, tempo aur tracks ke beech "
        "khaali line (blank line) chhodein. Jitne chahein utne track likhein (tabla, "
        "bansuri, harmonium, guitar_pad, sitar) — na likhein to woh instrument nahi bajega."
    )

    ex_col1, ex_col2 = st.columns(2)
    with ex_col1:
        if st.button("📋 Dadra उदाहरण लोड करें", key="ms_load_example_btn", use_container_width=True):
            st.session_state["music_script_text"] = EXAMPLE_SCRIPT
            st.rerun()
    with ex_col2:
        if st.button("🕉️ मंत्र/भजन उदाहरण लोड करें", key="ms_load_mantra_example_btn", use_container_width=True):
            st.session_state["music_script_text"] = MANTRA_EXAMPLE_SCRIPT
            st.rerun()

    st.session_state["music_script_text"] = st.text_area(
        "Script", value=st.session_state["music_script_text"], height=280,
        key="ms_script_textarea",
    )

    with st.expander("📖 Script फॉर्मेट गाइड / रेफरेंस"):
        st.markdown(
            "**Global settings** (script के सबसे ऊपर, एक साथ):\n"
            "- `taal:` — " + ", ".join(sorted(me.TAAL_LIBRARY.keys())) + "\n"
            "- `tempo:` — beats per minute (जैसे 80)\n"
            "- `cycles:` — कितनी बार पूरा ताल-चक्र दोहराए (डिफ़ॉल्ट 4; अगर किसी "
            "track के notes/chord में ज़्यादा `|` bars हैं, तो वो अपने आप बड़ा number ले लेगा)\n\n"
            "**हर track block** एक blank line से अलग, और `track: <type>` से शुरू:\n"
            "- `track: tabla` + `pattern: <taal-name>` (अगर ना दें तो ऊपर वाला taal ही use होगा)\n"
            "- `track: bansuri` / `harmonium` / `sitar` / `flute` + `notes: sa re ga ma pa | ...` "
            "+ optional `octave: low/middle/high`\n"
            "- `track: guitar_pad` + `chord: C, Am, F, G | ...`\n\n"
            "**Sargam swar**: sa re ga ma pa dha ni · komal: kre kga tma kdha kni · "
            "octave ऊँचा = `'` जोड़ें (जैसे `sa'`), नीचा = `,` जोड़ें (जैसे `sa,`) · "
            "khali/rest ke liye `-` likhein.\n\n"
            "`|` से bars अलग होते हैं — एक bar = एक ताल-चक्र। कई bars लिखने का मतलब "
            "है वो पैटर्न बदल-बदल कर दोहराया जाएगा।"
        )

    render_col1, render_col2 = st.columns([1, 3])
    with render_col1:
        render_clicked = st.button("🎬 Render करें", type="primary", key="ms_render_btn", use_container_width=True)

    if render_clicked:
        script_text = st.session_state["music_script_text"]
        try:
            with st.spinner("Script parse ho raha hai aur audio ban raha hai..."):
                comp = me.parse_script(script_text)
                audio = me.render_audio(comp)

                ts = datetime.now().strftime("%Y%m%d%H%M%S")
                wav_path = os.path.join(UPLOAD_ROOT, f"composition_{ts}.wav")
                me.save_wav(audio, wav_path)

                midi_path = None
                try:
                    pm = me.composition_to_midi(comp)
                    midi_path = os.path.join(UPLOAD_ROOT, f"composition_{ts}.mid")
                    pm.write(midi_path)
                except RuntimeError as midi_err:
                    st.warning(f"⚠️ MIDI export skip हुआ: {midi_err}")

            st.session_state["music_composition"] = comp
            st.session_state["music_audio"] = audio
            st.session_state["music_wav_path"] = wav_path
            st.session_state["music_midi_path"] = midi_path
            st.session_state["music_parse_error"] = None
            st.session_state["music_last_rendered_script"] = script_text
            st.success(
                f"✅ Render तैयार! ताल: {comp.taal}, tempo: {comp.tempo_bpm} BPM, "
                f"{comp.cycles} cycles, कुल लंबाई: {comp.total_duration_sec:.1f} सेकंड।"
            )
        except me.ParseError as e:
            st.session_state["music_parse_error"] = str(e)
            st.error(f"❌ Script में गड़बड़ी: {e}")
        except Exception as e:
            st.session_state["music_parse_error"] = str(e)
            st.error(f"❌ Render fail हुआ: {e}")
            with st.expander("Error Details"):
                st.code(traceback.format_exc())

    if st.session_state.get("music_wav_path") and os.path.exists(st.session_state["music_wav_path"]):
        st.markdown("---")
        st.markdown("**🔊 Preview**")
        st.audio(st.session_state["music_wav_path"])


def _render_midi_viewer_tab():
    st.subheader("👁️ MIDI Viewer — हर ट्रैक की piano-roll")
    comp = st.session_state.get("music_composition")
    if comp is None:
        st.info("ℹ️ पहले 'Compose' टैब में एक script render करें, फिर यहाँ हर track का timing/notes दिखेगा।")
        return

    st.caption(
        f"ताल: **{comp.taal}** · tempo: **{comp.tempo_bpm} BPM** · cycles: **{comp.cycles}** · "
        f"कुल लंबाई: **{comp.total_duration_sec:.1f}s**"
    )

    fig, ax = plt.subplots(figsize=(11, max(3, 1.2 * len(comp.tracks))))
    row_height = 0.8
    yticks = []
    ylabels = []

    for row_i, track in enumerate(comp.tracks):
        color = TRACK_COLORS.get(track.instrument, "#7f8c8d")
        y_center = row_i * row_height
        if track.instrument == "tabla":
            for ev in track.events:
                strength = "heavy" if "sam" in ev.label or "tali" in ev.label else (
                    "khali" if "khali" in ev.label else "light")
                h = {"heavy": 0.6, "khali": 0.4, "light": 0.25}[strength]
                ax.add_patch(mpatches.Rectangle(
                    (ev.start_sec, y_center - h / 2), ev.duration_sec, h,
                    color=color, alpha=0.85,
                ))
        else:
            pitches = [ev.midi_pitch for ev in track.events if ev.midi_pitch is not None]
            if pitches:
                pmin, pmax = min(pitches), max(pitches)
                prange = max(1, pmax - pmin)
            else:
                pmin, prange = 60, 1
            for ev in track.events:
                if ev.midi_pitch is None:
                    continue
                norm = (ev.midi_pitch - pmin) / prange
                h = 0.75
                y = y_center - h / 2 + norm * 0.35
                ax.add_patch(mpatches.Rectangle(
                    (ev.start_sec, y), ev.duration_sec, h * 0.5,
                    color=color, alpha=0.85,
                ))
        yticks.append(y_center)
        ylabels.append(track.name)

    ax.set_xlim(0, comp.total_duration_sec)
    ax.set_ylim(-row_height, len(comp.tracks) * row_height)
    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels)
    ax.set_xlabel("समय (सेकंड)")
    ax.grid(True, axis="x", alpha=0.25)

    # cycle boundary lines
    sec_per_cycle = comp.total_duration_sec / comp.cycles if comp.cycles else comp.total_duration_sec
    for c in range(1, comp.cycles):
        ax.axvline(c * sec_per_cycle, color="#999999", linestyle="--", linewidth=0.7, alpha=0.5)

    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

    st.caption("हर पट्टी एक नोट/बीट है — जितनी लंबी पट्टी, उतनी देर वो बजेगा। धुंधली खड़ी लाइनें हर ताल-चक्र की शुरुआत दिखाती हैं।")

    with st.expander("📋 Raw event list (टेक्स्ट के रूप में देखने के लिए)"):
        for track in comp.tracks:
            st.markdown(f"**{track.name}** ({len(track.events)} events)")
            rows = [
                {"शुरुआत (s)": round(ev.start_sec, 2), "लंबाई (s)": round(ev.duration_sec, 2),
                 "नोट/बीट": ev.label, "MIDI pitch": ev.midi_pitch if ev.midi_pitch is not None else "—"}
                for ev in track.events
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_export_tab():
    st.subheader("📤 Export")
    wav_path = st.session_state.get("music_wav_path")
    midi_path = st.session_state.get("music_midi_path")

    if not wav_path or not os.path.exists(wav_path):
        st.info("ℹ️ पहले 'Compose' टैब में render करें, फिर यहाँ से files download कर सकते हैं।")
        return

    st.markdown("**🎧 Audio (WAV)**")
    st.audio(wav_path)
    with open(wav_path, "rb") as f:
        st.download_button(
            "⬇️ WAV डाउनलोड करें", data=f, file_name=os.path.basename(wav_path),
            mime="audio/wav", key="ms_download_wav_btn",
        )

    if midi_path and os.path.exists(midi_path):
        st.markdown("**🎼 MIDI (.mid — MuseScore या किसी भी DAW में खोल सकते हैं)**")
        with open(midi_path, "rb") as f:
            st.download_button(
                "⬇️ MIDI डाउनलोड करें", data=f, file_name=os.path.basename(midi_path),
                mime="audio/midi", key="ms_download_midi_btn",
            )
    else:
        st.caption("ℹ️ MIDI export उपलब्ध नहीं है (pretty_midi install नहीं है)।")

    st.markdown("---")
    st.info(
        "📌 इस WAV फ़ाइल को अभी मैन्युअली download करके **🎬 Video Generator** मोड के "
        "Track 3 (Audio/Music) या Track 5 (Mantra Audio Loop) में अपलोड करें। "
        "सीधा auto-handoff (बिना डाउनलोड किए) एक अगला कदम है।"
    )


def render_music_studio_ui():
    _init_state()
    st.title("🎼 Music Studio")
    st.caption("टेक्स्ट स्क्रिप्ट से ताल+सरगम कंपोज़ करें, मल्टी-इंस्ट्रूमेंट ऑडियो+MIDI बनाएं।")

    tab1, tab2, tab3 = st.tabs(["✍️ Compose", "👁️ MIDI Viewer", "📤 Export"])
    with tab1:
        _render_compose_tab()
    with tab2:
        _render_midi_viewer_tab()
    with tab3:
        _render_export_tab()


if __name__ == "__main__":
    st.set_page_config(page_title="Music Studio", page_icon="🎼", layout="wide")
    render_music_studio_ui()
