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
2. 🎙️ Vocal (record/upload, overdub-sync, DSP polish, dual-source crowd
   chorus, final mix)
3. 👁️ MIDI Viewer (per-track piano-roll, taaki dekh sakein kya set hua)
4. 📤 Export (WAV audio + .mid file download, aur render karke seedha
   Baba Web Studio ke Track 3/Track 5 mein use karne ka pointer)
"""

import os
import io
import time
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

DADRA_TEMPLATE_SCRIPT = """taal: dadra
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

BHAJAN_TEMPLATE_SCRIPT = """taal: kaharwa
tempo: 65
cycles: 4

track: tabla
pattern: kaharwa

track: temple_bell
pattern: kaharwa

track: harmonium
notes: sa , ni , sa re | ga ma ga re sa , ni ,

track: bansuri
notes: sa re ga ma | pa ma ga re
octave: middle
"""

# पुराने नामों को भी ज़िंदा रखा है (backward-compatibility के लिए, अगर
# कहीं और यह नाम इस्तेमाल हो रहा हो)
EXAMPLE_SCRIPT = DADRA_TEMPLATE_SCRIPT
MANTRA_EXAMPLE_SCRIPT = BHAJAN_TEMPLATE_SCRIPT

TRACK_COLORS = {
    "tabla": "#c0392b",
    "damru": "#d35400",
    "nagada": "#7f1d1d",
    "temple_bell": "#f1c40f",
    "shankha": "#16a085",
    "bansuri": "#27ae60",
    "flute": "#27ae60",
    "harmonium": "#e67e22",
    "guitar_pad": "#2980b9",
    "guitar": "#2980b9",
    "sitar": "#8e44ad",
    # -- Part 3: पारंपरिक/लोक वाद्य सुइट --
    "dafli": "#b8860b",
    "manjira": "#c9a227",
    "kartal": "#8b5a2b",
    "jhanjh": "#a67c00",
    "matka": "#a0522d",
    "payal": "#daa520",
    "ghungru": "#cd7f32",
}

DEFAULTS = {
    "music_script_text": DADRA_TEMPLATE_SCRIPT,
    "music_composition": None,
    "music_audio": None,
    "music_wav_path": None,
    "music_midi_path": None,
    "music_parse_error": None,
    "music_last_rendered_script": None,
    "ai_compose_keywords": "",
    "ai_compose_last_result": None,
    # -- Vocal section (main singer) --
    "vocal_input_mode": "🎤 लाइव रिकॉर्ड करें",
    "vocal_raw_path": None,
    "vocal_raw_name": None,
    "vocal_advanced_mode": False,
    "vocal_custom_values": dict(me.AUTO_PERFECT_PRESET),
    "vocal_active_params": None,      # params that produced the CURRENT processed file
    "vocal_active_mode_label": None,  # "auto" | "custom" - for the UI badge
    "vocal_processed_path": None,
    "vocal_error": None,
    "vocal_noise_reduction_pct": 60,
    # -- Dedicated chorus track (Part 2: dual-source crowd chorus) --
    "chorus_input_mode": "🎤 लाइव रिकॉर्ड करें",
    "chorus_raw_path": None,
    "chorus_raw_name": None,
    # -- Crowd chorus + final mix controls (Part 2) --
    "crowd_source_mode": "🤖 ऑटो-क्लोन (मेरी अपनी आवाज़ से)",
    "crowd_num_voices": 6,
    "crowd_intensity_pct": 45,
    "crowd_seed_lock": False,
    "crowd_last_seed": None,
    "mix_vocal_gain_db": 0.0,
    "mix_backing_gain_db": -4.0,
    "mix_crowd_gain_db": -7.0,
    "final_mix_path": None,
    "final_mix_error": None,
    # -- Part 3: Live MIDI Virtual Pad --
    "live_pad_recording": False,
    "live_pad_start_time": None,
    "live_pad_taps": {},
    "live_pad_steps": 16,
    "live_pad_last_preview_path": None,
    "live_pad_last_preview_label": None,
    "live_pad_last_finalize_msg": None,
    # -- Part 3: Video Generator handoff (core app ke Track 3/5 ke saath contract) --
    "bg_music_audio": None,
    "bg_music_audio_source": None,
}

# Live Pad panel mein dikhne wale label (emoji + Hindi naam) - order
# me.LIVE_PAD_INSTRUMENTS se aata hai, taaki engine aur UI hamesha sync rahein।
PAD_INSTRUMENT_LABELS = {
    "damru": "🪘 डमरू", "nagada": "🥁 नगाड़ा", "shankha": "🐚 शंख", "temple_bell": "🔔 घंटी",
    "dafli": "🪇 डफली", "manjira": "🎶 मंजीरा", "kartal": "🪵 खड़ताल", "jhanjh": "🥁 झांझ",
    "matka": "🏺 मटका", "payal": "👣 पायल", "ghungru": "💫 घूंघरू",
}


def _init_state():
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v


TAAL_GUIDE = {
    "dadra": {
        "beats": "6 मात्रा (3+3 में बंटी हुई)",
        "feel": "हल्की, झूमती हुई लय — जैसे झूला झूलना या हल्के मन से गुनगुनाना",
        "use": "प्रेम-भाव वाले भजन, हल्के-फुल्के गीत, रोमांटिक/सौम्य मूड के लिए सबसे अच्छा",
    },
    "kaharwa": {
        "beats": "8 मात्रा (4+4 में बंटी हुई)",
        "feel": "सबसे आम, सीधी-सादी थाप — फ़िल्मी गानों और भजनों में सबसे ज़्यादा सुनाई देती है",
        "use": "आरती, भजन, कथा-वाचन के पीछे बैकग्राउंड — कुछ भी समझ न आए तो यही ताल चुनें, कभी गलत नहीं जाती",
    },
    "rupak": {
        "beats": "7 मात्रा (3+2+2) — यह 'खाली' (हल्के बीट) से शुरू होती है, 'सम' (भारी बीट) से नहीं",
        "feel": "थोड़ी अनोखी, घुमावदार लय — सीधी-सपाट नहीं चलती, इसलिए ध्यान खींचती है",
        "use": "जब गाना ज़रा अलग/खास सुनवाना हो, पारंपरिक ठुमरी-अंदाज़ के लिए",
    },
    "teentaal": {
        "beats": "16 मात्रा (4+4+4+4) — शास्त्रीय संगीत की सबसे मशहूर ताल",
        "feel": "भारी, गंभीर, विस्तार से चलने वाली — जल्दबाज़ी नहीं, ठहराव वाली",
        "use": "शास्त्रीय अंदाज़ के भजन, कथा का गंभीर/भारी हिस्सा, बड़ी/लंबी रचनाओं के लिए",
    },
    "ektaal": {
        "beats": "12 मात्रा — पारंपरिक शास्त्रीय ताल",
        "feel": "मध्यम गति, संतुलित — न बहुत हल्की, न बहुत भारी",
        "use": "ऐसा भजन जिसमें थोड़ी गंभीरता भी हो और रवानी भी",
    },
}

TRACK_GUIDE = {
    "tabla": "🥁 लय/ताल बजाने वाला मुख्य साज़ — यही गाने की 'चाल' तय करता है। लगभग हर रचना में ज़रूरी।",
    "damru": "🪘 डमरू — शिव जी का छोटा हाथ का ढोल, दो-मार (double-strike) वाली ऊँची, चपल आवाज़। शिव-भजनों के लिए खास।",
    "nagada": "🥁 नगाड़ा — बड़ा, बहुत गहरा-भारी ढोल, उत्सव/जुलूस जैसा माहौल बनाता है।",
    "temple_bell": "🔔 मंदिर की घंटी — धातु जैसी खनकती आवाज़, आरती/पूजा में लय के साथ बजती है।",
    "shankha": "🐚 शंख — गहरी, लंबी, हवा जैसी फूँक। ताल से आज़ाद, हर चक्र की शुरुआत में एक बार बजता है।",
    "bansuri": "🎋 बांसुरी — मीठी, हल्की, हवा जैसी धुन। भक्ति और प्रेम-भाव में सबसे ज़्यादा इस्तेमाल होती है।",
    "flute": "🎋 बांसुरी जैसा ही (सिर्फ़ अंग्रेज़ी नाम)",
    "harmonium": "🎹 हारमोनियम — भजन/कीर्तन का पारंपरिक साज़, सुर को स्थिर और भरा-भरा रखता है।",
    "guitar_pad": "🎸 गिटार पैड — पृष्ठभूमि में नरम, फैला हुआ, तकिये जैसा नरम सुर देता है, गाने में गहराई/माहौल जोड़ता है।",
    "guitar": "🎸 गिटार पैड जैसा ही",
    "sitar": "🪕 सितार — शास्त्रीय, चमकदार तार वाला साज़, खास/भारी/गंभीर माहौल के लिए।",
    # -- Part 3: पारंपरिक/लोक वाद्य सुइट --
    "dafli": "🪇 डफली — तीखी, टाइट लकड़ी के फ्रेम वाली थाप। **खास बात**: अगर `notes:` दें तो यह सरगम के साथ मेलोडी में भी बज सकती है, वरना `pattern:`/`bols:` से सामान्य ताल में।",
    "manjira": "🎶 मंजीरा — छोटी धातु की प्लेटों की ऊँची, साफ़, चमकदार 'चिन-चिन' आवाज़, जल्दी खत्म होने वाली।",
    "kartal": "🪵 खड़ताल/करताल — लकड़ी की पट्टियों का घना 'खट-खट', साथ में हल्की पीतल की झनझनाहट। भजन-कीर्तन में बहुत आम।",
    "jhanjh": "🥁 झांझ — बड़ी धातु की प्लेटों का टकराव, चौड़ी और देर तक गूंजती आवाज़ — मंजीरे का बड़ा भाई।",
    "matka": "🏺 मटका/गगरी — मिट्टी के घड़े पर हाथ की सूखी, खोखली (hollow) थाप, लोक-संगीत जैसा मिट्टी से जुड़ा एहसास।",
    "payal": "👣 पायल — पैर की पायल के घुंघरुओं का नरम, चमकदार 'छम-छम' — हल्का, सजावटी माहौल जोड़ती है।",
    "ghungru": "💫 घूंघरू — पायल जैसा ही परिवार, पर ज़्यादा घना और तेज़ 'छम-छम' — नृत्य/उत्सव जैसा भाव लाता है।",
}

# AI ऑटो-कंपोज़ में कौन-कौन से keyword समझे जाते हैं - सिर्फ़ UI में
# उदाहरण दिखाने के लिए (असली logic music_engine.KEYWORD_MAP में है)
AI_COMPOSE_EXAMPLE_KEYWORDS = [
    "शिव", "महादेव", "सुबह", "आरती", "कीर्तन", "भजन", "शाम", "भक्ति",
    "ध्यान", "शांति", "कृष्ण", "राम", "हनुमान", "देवी", "दुर्गा", "गणेश", "पूजा",
]


def _finalize_live_pad_recording():
    """
    '⏹️ रोकें और Script में जोड़ें' दबाने पर चलता है — जितने भी instruments
    par tap hua tha, un sabki timing ko `me.build_bols_lines_from_taps()`
    se ek valid 'bols:' grammar mein badalkar, naye 'track: <naam>' block
    ki tarah seedha music_script_text ke end mein jod deta hai। Yeh function
    hamesha _render_compose_tab() ke text_area widget se PEHLE call hoti
    hai (aur turant st.rerun() hota hai), isliye session_state["music_script_text"]
    ko direct badalna safe hai - text_area widget ka apna purana key-value
    is naye text ko agli run mein khud utha lega।
    """
    taps = st.session_state.get("live_pad_taps", {})
    start_time = st.session_state.get("live_pad_start_time")
    st.session_state["live_pad_recording"] = False

    if not taps or start_time is None:
        st.session_state["live_pad_start_time"] = None
        st.warning("⚠️ रिकॉर्डिंग में कोई पैड-टैप दर्ज नहीं हुआ — कुछ भी Script में नहीं जोड़ा गया।")
        return

    total_duration = max(0.5, time.time() - start_time)
    steps = st.session_state.get("live_pad_steps", 16)
    bols_lines = me.build_bols_lines_from_taps(taps, total_duration, steps=steps, bar_size=8)
    st.session_state["live_pad_start_time"] = None
    st.session_state["live_pad_taps"] = {}

    if not bols_lines:
        st.warning("⚠️ रिकॉर्डिंग में कोई पैड-टैप दर्ज नहीं हुआ — कुछ भी Script में नहीं जोड़ा गया।")
        return

    blocks = []
    for inst_key, bols_str in bols_lines.items():
        blocks.append(f"track: {inst_key}\nbols: {bols_str}")

    existing = st.session_state["music_script_text"].rstrip("\n")
    new_text = existing + "\n\n" + "\n\n".join(blocks) + "\n"
    st.session_state["music_script_text"] = new_text
    added_names = ", ".join(PAD_INSTRUMENT_LABELS.get(k, k) for k in bols_lines.keys())
    st.session_state["live_pad_last_finalize_msg"] = (
        f"✅ आपकी लाइव रिकॉर्डिंग ({total_duration:.1f} सेकंड) से {added_names} के लिए नए track ब्लॉक "
        f"Script के अंत में जोड़ दिए गए हैं — नीचे scroll करके देखें, चाहें तो हाथ से भी एडिट कर सकते हैं।"
    )


def _render_live_pad_panel():
    """
    🎹 Live MIDI Virtual Pad — Compose tab ke andar ek chhota interactive
    panel jahan user seedha screen par tap karke sabhi 11 taal-vaadya
    (damru/nagada/shankha/temple_bell/dafli/manjira/kartal/jhanjh/matka/
    payal/ghungru) baja sakta hai, aur chahe to us live performance ko
    record karke seedha script mein 'track:'/'bols:' block ki tarah
    convert kara sakta hai।
    """
    st.markdown("#### 🎹 लाइव पैड — टैप करके बजाएं और चाहें तो रिकॉर्ड करें")
    st.caption(
        "नीचे किसी भी पैड पर टैप करें — तुरंत उस वाद्य की आवाज़ सुनाई देगी। "
        "'⏺️ रिकॉर्ड करें' दबाकर अपनी खुद की एक छोटी लय बजाएं — रोकने पर वह अपने-आप "
        "नीचे Script बॉक्स में एक नए track के रूप में जुड़ जाएगी।"
    )
    with st.expander("ℹ️ यह ठीक से कैसे काम करता है?"):
        st.markdown(
            "- हर टैप पर उस वाद्य की एक छोटी 'one-shot' आवाज़ नीचे प्ले होने लगती है (ब्राउज़र में सीधे auto-play "
            "नहीं होता — नीचे वाला 🔊 प्लेयर खुद दबाकर सुनें)।\n"
            "- रिकॉर्डिंग के दौरान, आपकी हर टैप का ठीक-ठीक समय दर्ज होता है। रोकने पर पूरी रिकॉर्डिंग की लंबाई को "
            "एक बराबर हिस्सों वाली 'ग्रिड' में बाँटकर, जिस-जिस हिस्से में आपने टैप किया वहाँ बोल जोड़ दिया जाता है।\n"
            "- **ग्रिड रिज़ॉल्यूशन** जितना ज़्यादा (जैसे 32), उतनी ही बारीकी से आपकी असली टाइमिंग बचती है — "
            "लेकिन बहुत महीन टाइमिंग के लिए ब्राउज़र थोड़ा लेट हो सकता है, इसलिए बहुत तेज़ बजाने पर हल्का फ़र्क़ आ सकता है।\n"
            "- रिकॉर्डिंग रोकने के बाद बना script हिस्सा पूरी तरह से एडिट करने लायक टेक्स्ट है — नीचे बॉक्स में जाकर "
            "हाथ से भी ठीक कर सकते हैं।"
        )

    ctrl_col1, ctrl_col2 = st.columns([1, 1])
    with ctrl_col1:
        step_options = [8, 16, 32]
        current_steps = st.session_state.get("live_pad_steps", 16)
        if current_steps not in step_options:
            current_steps = 16
        st.session_state["live_pad_steps"] = st.selectbox(
            "ग्रिड रिज़ॉल्यूशन (steps)", options=step_options,
            index=step_options.index(current_steps), key="live_pad_steps_select",
            help="रिकॉर्डिंग की पूरी लंबाई को कितने बराबर हिस्सों में बाँटा जाए — ज़्यादा steps = ज़्यादा बारीक टाइमिंग।",
        )
    with ctrl_col2:
        if st.session_state.get("live_pad_recording"):
            elapsed = time.time() - st.session_state["live_pad_start_time"]
            total_taps = sum(len(v) for v in st.session_state.get("live_pad_taps", {}).values())
            st.metric("🔴 रिकॉर्डिंग जारी है", f"{elapsed:.1f} सेकंड", f"{total_taps} टैप दर्ज")
        else:
            st.caption("अभी रिकॉर्डिंग बंद है — नीचे बटन दबाकर शुरू करें।")

    rec_col1, rec_col2, rec_col3 = st.columns(3)
    with rec_col1:
        if not st.session_state.get("live_pad_recording"):
            if st.button("⏺️ लाइव पैड रिकॉर्ड करें", key="live_pad_start_btn", type="primary",
                         use_container_width=True):
                st.session_state["live_pad_recording"] = True
                st.session_state["live_pad_start_time"] = time.time()
                st.session_state["live_pad_taps"] = {}
                st.session_state["live_pad_last_finalize_msg"] = None
                st.rerun()
        else:
            if st.button("⏹️ रोकें और Script में जोड़ें", key="live_pad_stop_btn", type="primary",
                         use_container_width=True):
                _finalize_live_pad_recording()
                st.rerun()
    with rec_col2:
        if st.button("🗑️ रीसेट करें", key="live_pad_reset_btn", use_container_width=True,
                      help="अभी तक की रिकॉर्डिंग (अगर चल रही हो) मिटाकर शुरुआत जैसा कर देगा।"):
            st.session_state["live_pad_recording"] = False
            st.session_state["live_pad_start_time"] = None
            st.session_state["live_pad_taps"] = {}
            st.session_state["live_pad_last_finalize_msg"] = None
            st.rerun()
    with rec_col3:
        pass

    if st.session_state.get("live_pad_last_finalize_msg"):
        st.success(st.session_state["live_pad_last_finalize_msg"])

    st.markdown("**पैड्स:**")
    pads = me.LIVE_PAD_INSTRUMENTS  # canonical order, engine se aata hai
    pad_rows = [pads[i:i + 4] for i in range(0, len(pads), 4)]
    for row in pad_rows:
        cols = st.columns(4)
        for col, inst_key in zip(cols, row):
            label = PAD_INSTRUMENT_LABELS.get(inst_key, inst_key)
            with col:
                tapped = st.button(label, key=f"pad_btn_{inst_key}", use_container_width=True)
                if tapped:
                    try:
                        preview_audio = me.render_instrument_preview(inst_key)
                        preview_path = os.path.join(UPLOAD_ROOT, f"pad_preview_{inst_key}.wav")
                        me.save_wav(preview_audio, preview_path)
                        st.session_state["live_pad_last_preview_path"] = preview_path
                        st.session_state["live_pad_last_preview_label"] = label
                    except Exception as e:
                        st.session_state["live_pad_last_preview_path"] = None
                        st.warning(f"⚠️ '{label}' प्रीव्यू बनाने में गड़बड़ी: {e}")
                    if st.session_state.get("live_pad_recording"):
                        elapsed = time.time() - st.session_state["live_pad_start_time"]
                        st.session_state["live_pad_taps"].setdefault(inst_key, []).append(elapsed)
                    st.rerun()

    if st.session_state.get("live_pad_last_preview_path") and os.path.exists(st.session_state["live_pad_last_preview_path"]):
        st.caption(f"🔊 आख़िरी टैप: **{st.session_state.get('live_pad_last_preview_label', '')}**")
        st.audio(st.session_state["live_pad_last_preview_path"])


def _render_compose_tab():
    st.subheader("✍️ Compose — taal/sargam text script")
    st.caption(
        "Har line ek setting ya ek track batati hai. Taal, tempo aur tracks ke beech "
        "khaali line (blank line) chhodein. Jitne chahein utne track likhein (tabla, damru, "
        "nagada, temple_bell, shankha, dafli, manjira, kartal, jhanjh, matka, payal, ghungru, "
        "bansuri, harmonium, guitar_pad, sitar) — na likhein to woh instrument nahi bajega। "
        "English aur हिंदी (Devanagari) dono mein likh sakte hain, ya नीचे 🎹 Live Pad se खुद तापकर बजाकर भी "
        "record kar sakte hain।"
    )

    sf_status = me.check_soundfont_status()
    if sf_status["found"]:
        st.success(sf_status["message"])
    else:
        st.info(sf_status["message"])

    st.markdown("---")

    # -------------------------------------------------------------
    # 🤖 AI AUTO-COMPOSE
    # -------------------------------------------------------------
    st.markdown("#### 🤖 AI ऑटो-कंपोज़ धुन मेकर")
    st.caption(
        "मौका/भाव/देवता का नाम टाइप करें (जैसे 'शिव सुबह आरती' या 'कृष्ण भक्ति शाम') — "
        "AI उससे जुड़ा राग, ताल और रफ़्तार चुनकर एक बिल्कुल नई धुन बना देगा। "
        "हर बार क्लिक करने पर **अलग** धुन बनेगी (कभी दोहराई नहीं जाएगी), ताकि YouTube पर "
        "duplicate-content जैसी दिक्कत ना आए।"
    )
    with st.expander("ℹ️ कौन से शब्द इस्तेमाल कर सकते हैं?"):
        st.markdown(
            "पहचाने जाने वाले कुछ शब्द: " + ", ".join(AI_COMPOSE_EXAMPLE_KEYWORDS) + "।\n\n"
            "इनमें से कोई भी शब्द अपने वाक्य में कहीं भी लिखें (जैसे 'आज सुबह शिव जी की आरती के लिए धुन बनाओ') — "
            "AI उसे ढूंढकर सही राग/ताल चुन लेगा। **कोई पहचाना शब्द न मिले तो भी कोई बात नहीं** — "
            "एक संतुलित, शांत धुन अपने-आप बन जाएगी।\n\n"
            "कुछ शब्दों पर ख़ास वाद्य अपने-आप जुड़ जाते हैं — जैसे 'शिव'/'महादेव' पर डमरू, "
            "'आरती'/'कीर्तन' पर मंदिर की घंटी, 'दुर्गा'/'हनुमान' पर नगाड़ा।"
        )

    st.session_state["ai_compose_keywords"] = st.text_input(
        "मौका/भाव/देवता लिखें", value=st.session_state["ai_compose_keywords"],
        placeholder="जैसे: शिव सुबह आरती", key="ai_compose_keywords_input",
        help="एक या कई शब्द लिखें - जितने चाहें, वाक्य की तरह भी लिख सकते हैं।",
    )
    ai_col1, ai_col2 = st.columns([1, 3])
    with ai_col1:
        ai_compose_clicked = st.button(
            "✨ धुन बनाएं", type="primary", key="ai_compose_btn", use_container_width=True,
            help="ऊपर लिखे शब्दों से एक नई, अनोखी धुन बनाकर सीधे नीचे वाले script बॉक्स में भर देगा।",
        )
    if ai_compose_clicked:
        keywords = st.session_state["ai_compose_keywords"].strip()
        if not keywords:
            st.warning("⚠️ पहले ऊपर कोई शब्द (जैसे 'शिव सुबह आरती') लिखें।")
        else:
            result = me.auto_compose_script(keywords)
            st.session_state["music_script_text"] = result["script"]
            st.session_state["ai_compose_last_result"] = result
            st.rerun()

    last_result = st.session_state.get("ai_compose_last_result")
    if last_result:
        matched = last_result["matched_keyword"] or "(कोई खास शब्द नहीं मिला, डिफ़ॉल्ट धुन)"
        st.success(
            f"✅ धुन तैयार! पहचाना शब्द: **{matched}** • राग: **{last_result['raag']}** "
            f"({last_result['mood']}) • ताल: **{last_result['taal']}** • tempo: **{last_result['tempo']} BPM** — "
            f"नीचे script बॉक्स में भर दिया गया है।"
        )

    st.markdown("---")

    # -------------------------------------------------------------
    # 🎹 LIVE MIDI VIRTUAL PAD (Part 3)
    # -------------------------------------------------------------
    _render_live_pad_panel()

    st.markdown("---")

    # -------------------------------------------------------------
    # 📋 TEMPLATES
    # -------------------------------------------------------------
    st.markdown("#### 📋 तैयार टेम्पलेट")
    ex_col1, ex_col2 = st.columns(2)
    with ex_col1:
        if st.button("🎶 Dadra टेम्पलेट", key="ms_load_dadra_btn", use_container_width=True,
                      help="एक तैयार, हल्के-फुल्के Dadra ताल वाला उदाहरण भर देगा।"):
            st.session_state["music_script_text"] = DADRA_TEMPLATE_SCRIPT
            st.rerun()
    with ex_col2:
        if st.button("🙏 Bhajan टेम्पलेट", key="ms_load_bhajan_btn", use_container_width=True,
                      help="एक धीमी, भक्ति-भाव वाली Kaharwa ताल की उदाहरण भजन-धुन भर देगा।"):
            st.session_state["music_script_text"] = BHAJAN_TEMPLATE_SCRIPT
            st.rerun()

    st.text_area(
        "Script", height=280, key="music_script_text",
        help="यहाँ अपनी धुन का पूरा 'नक्शा' लिखें — कौन सी ताल, कितनी स्पीड, कौन-कौन से साज़ क्या बजाएंगे।",
    )

    with st.expander("📖 Script फॉर्मेट गाइड — हर लाइन का मतलब (पहली बार इस्तेमाल कर रहे हैं तो ज़रूर पढ़ें)"):
        st.markdown(
            "एक script हमेशा दो हिस्सों में बंटी होती है — पहले **सेटिंग्स** (ऊपर), फिर एक-एक करके **साज़ (track) के ब्लॉक** (नीचे), "
            "हर हिस्से के बीच एक खाली लाइन ज़रूरी है। **पूरी script English या हिंदी (Devanagari), दोनों में लिख सकते हैं।**\n\n"
            "### 1️⃣ ऊपर की सेटिंग्स (पूरे गाने पर लागू)\n"
            "- `taal:` — कौन सी ताल इस्तेमाल होगी (English: dadra/kaharwa/rupak/teentaal/ektaal, "
            "या हिंदी: दादरा/कहरवा/रूपक/तीनताल/एकताल)\n"
            "- `tempo:` — गाने की रफ़्तार, एक मिनट में कितनी बीट बजेंगी (beats per minute)। "
            "**कम नंबर (जैसे 60) = धीमा, शांत गाना। ज़्यादा नंबर (जैसे 120) = तेज़, उत्सव जैसा गाना।** आमतौर पर भजन के लिए 65-90 ठीक रहता है।\n"
            "- `cycles:` — पूरी ताल कितनी बार दोहराई जाए (जैसे 4 का मतलब है ताल 4 बार बजेगी)। "
            "**ज़्यादा cycles = लंबा गाना। कम cycles = छोटा गाना।** अगर किसी साज़ के notes में `|` से ज़्यादा bars बना दें, तो वो अपने आप ज़्यादा cycles ले लेगा।\n\n"
            "### 2️⃣ हर साज़ (track) का ब्लॉक\n"
            "हर block `track: <साज़ का नाम>` से शुरू होता है (English या हिंदी नाम, जैसे `tabla`/`तबला`), फिर उसकी अपनी सेटिंग:\n"
            "- `track: tabla` / `damru` / `nagada` / `temple_bell` / `manjira` / `kartal` / `jhanjh` / `matka` / "
            "`payal` / `ghungru` + `pattern: <ताल-नाम>` — अगर pattern न दें तो ऊपर वाली taal ही अपने आप इस्तेमाल होगी\n"
            "- **या** इन सभी के लिए `bols:` से अपनी खुद की rhythm लिखें (जैसे `bols: dha dhin dhin dha | ...` या `धा धिन धिन धा | ...`) — "
            "इस्तेमाल होते ही `pattern:` अपने आप नज़रअंदाज़ हो जाता है\n"
            "- `track: dafli` — **खास/दोहरी क्षमता**: अगर इसे `notes: sa re ga | ...` दें तो यह सरगम के साथ **मेलोडी** में बजता है "
            "(जैसे बांसुरी/हारमोनियम); अगर `pattern:`/`bols:` दें तो बाकी ढोलों की तरह सिर्फ़ **ताल** बजाता है।\n"
            "- `track: shankha` — कोई notes/pattern नहीं चाहिए, हर ताल-चक्र के शुरू में अपने-आप एक बार फूँक देता है "
            "(चाहें तो `hold: 3.0` से फूँक की लंबाई सेकंड में बदल सकते हैं)\n"
            "- `track: bansuri` / `harmonium` / `sitar` / `flute` + `notes: sa re ga ma pa | ...` "
            "+ (चाहें तो) `octave: low/middle/high` — यानी सुर नीचा/मध्यम/ऊँचा रखना है\n"
            "- `track: guitar_pad` + `chord: C, Am, F, G | ...`\n\n"
            "### 3️⃣ सरगम स्वर कैसे लिखें\n"
            "**बुनियादी स्वर (English)**: sa re ga ma pa dha ni • **(हिंदी)**: सा रे ग/गा म/मा प/पा ध/धा नि\n"
            "**कोमल/तीव्र स्वर (English)**: kre kga tma kdha kni • **(हिंदी, दो शब्दों में)**: 'कोमल रे' 'कोमल ग' 'तीव्र म' 'कोमल ध' 'कोमल नि'\n"
            "**ऊँचा सुर**: स्वर के बाद `'` लगाएं (जैसे `sa'` / `सा'`)। **नीचा सुर**: स्वर के बाद `,` लगाएं (जैसे `sa,` / `सा,`)\n"
            "**खामोशी/रुकना**: `-` लिखें (कोई आवाज़ नहीं बजेगी उस जगह)\n\n"
            "**`|` का मतलब** — एक `|` से अगला हिस्सा एक नया 'bar' (एक पूरा ताल-चक्र) शुरू करता है। "
            "कई bars लिखने का मतलब है वो धुन बदल-बदल कर उतनी ही बार दोहराई जाएगी।"
        )

    with st.expander("🥁 कौन सी ताल कब चुनें? (हर ताल का मूड और इस्तेमाल)"):
        for name, info in TAAL_GUIDE.items():
            st.markdown(
                f"**{name}** — {info['beats']}\n"
                f"- 🎭 महसूस कैसी होती है: {info['feel']}\n"
                f"- ✅ कब इस्तेमाल करें: {info['use']}"
            )
            st.markdown("---")

    with st.expander("🎻 कौन सा साज़ (track) क्या काम करता है?"):
        for name, desc in TRACK_GUIDE.items():
            st.markdown(f"- {desc}")

    render_col1, render_col2 = st.columns([1, 3])
    with render_col1:
        render_clicked = st.button(
            "🎬 Render करें", type="primary", key="ms_render_btn", use_container_width=True,
            help="ऊपर लिखी script को पढ़कर असली ऑडियो (और MIDI फ़ाइल) बनाएगा।",
        )

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


VOCAL_UPLOAD_ROOT = os.path.join(tempfile.gettempdir(), "music_studio_vocals")
os.makedirs(VOCAL_UPLOAD_ROOT, exist_ok=True)

CHORUS_UPLOAD_ROOT = os.path.join(tempfile.gettempdir(), "music_studio_chorus")
os.makedirs(CHORUS_UPLOAD_ROOT, exist_ok=True)

SLIDER_SPECS = [
    ("brilliance", "✨ आवाज़ की खनक (Brilliance)", 0, 100, "%"),
    ("warmth", "🍯 सुरीलापन और मिठास (Warmth)", 0, 100, "%"),
    ("bass_db", "🎚️ भारीपन/वजन (Bass)", -12.0, 12.0, "dB"),
    ("treble_db", "🎚️ तीखा सुर (Treble)", -12.0, 12.0, "dB"),
    ("crowd_intensity", "🙏 भक्तों की भीड़ प्रभाव (Crowd Chorus) - पुराना सरल तरीका", 0, 100, "%"),
]

# हर slider के लिए पूरी, आसान भाषा में जानकारी - "क्या है", "बढ़ाने पर क्या होगा",
# "बहुत ज़्यादा बढ़ाने पर क्या दिक्कत आएगी", "घटाने पर क्या होगा"। Vocal tab में
# हर slider के नीचे एक "ℹ️" expander में यही दिखाया जाता है।
SLIDER_INFO = {
    "brilliance": {
        "kya_hai": "आवाज़ के सबसे ऊँचे/तीखे सुरों (7kHz से ऊपर) को हल्का तेज़ करता है, जिससे आवाज़ में "
                   "'चमक' या 'खनक' महसूस होती है — जैसे स्टूडियो-रिकॉर्डिंग में आवाज़ साफ़ और आगे आई हुई लगती है।",
        "badhane_par": "आवाज़ ज़्यादा साफ़, तेज़ और 'प्रोफेशनल' लगेगी।",
        "zyada_par": "बहुत ज़्यादा बढ़ाने पर आवाज़ चुभने वाली/धातु जैसी (tinny) लग सकती है, कानों में चुभेगी।",
        "ghatane_par": "आवाज़ नरम, थोड़ी दबी/भारी लगेगी — जैसे फ़ोन पर बात कर रहे हों।",
    },
    "warmth": {
        "kya_hai": "आवाज़ में हल्का, प्राकृतिक 'भराव' और मुलायम (tube-style) harmonic saturation जोड़ता है — "
                   "जिससे डिजिटल आवाज़ की कठोरता (harshness) खत्म होकर एक गर्म, आरामदायक एहसास आता है।",
        "badhane_par": "आवाज़ मीठी, सुरीली और सुकून देने वाली लगेगी — भजन/मंत्र के लिए अच्छा।",
        "zyada_par": "बहुत ज़्यादा पर आवाज़ थोड़ी धुंधली/अस्पष्ट (mushy) लग सकती है।",
        "ghatane_par": "आवाज़ बिल्कुल सीधी/कच्ची (raw) रहेगी, जैसी रिकॉर्ड हुई थी, बिना किसी बदलाव के।",
    },
    "bass_db": {
        "kya_hai": "आवाज़ के भारी/गहरे हिस्से (जैसे ढोल की गूंज जैसा असर) को कम या ज़्यादा करता है — "
                   "यह आवाज़ का 'वज़न' है, कथा/मंत्र के लिए एक गंभीर, अधिकारपूर्ण गूंज देता है।",
        "badhane_par": "आवाज़ भारी, गंभीर और ताकतवर लगेगी।",
        "zyada_par": "बहुत ज़्यादा पर आवाज़ गूंजने वाली/धुंधली (boomy) लग सकती है, शब्द साफ़ सुनाई नहीं देंगे।",
        "ghatane_par": "आवाज़ पतली, हल्की सी लगेगी — कम ताकतवर, कम मौजूदगी वाली।",
    },
    "treble_db": {
        "kya_hai": "आवाज़ के तीखे/पतले सुरों (जैसे 'स', 'श' जैसे अक्षरों की आवाज़) को कम-ज़्यादा करता है — "
                   "यह शब्दों की 'साफ़ई' तय करता है।",
        "badhane_par": "शब्द ज़्यादा साफ़, स्पष्ट सुनाई देंगे, हर लफ़्ज़ समझ आएगा।",
        "zyada_par": "बहुत ज़्यादा पर 'स'/'श' जैसे अक्षर चुभने लगेंगे, सीटी जैसी तेज़ आवाज़ आ सकती है।",
        "ghatane_par": "आवाज़ धीमी, दबी हुई, थोड़ी अस्पष्ट लगेगी — शब्द साफ़ समझ नहीं आएँगे।",
    },
    "crowd_intensity": {
        "kya_hai": "यह पुराना, सरल crowd-effect है (delay+muffle आधारित) — आपकी अकेली आवाज़ के पीछे कुछ हल्की "
                   "प्रतिध्वनियाँ जोड़ता है। ज़्यादा असली, विविध भीड़ के लिए नीचे 'दोहरा-स्रोत क्राउड कोरस इंजन' सेक्शन इस्तेमाल करें।",
        "badhane_par": "माहौल में हल्का 'सामूहिक भजन' जैसा एहसास आएगा।",
        "zyada_par": "बहुत ज़्यादा पर आपकी असली आवाज़ दब सकती है, शोर/गूंज जैसा लग सकता है।",
        "ghatane_par": "0% पर सिर्फ़ आपकी अकेली, साफ़ आवाज़ रहेगी — कोई भीड़-प्रभाव नहीं।",
    },
}


def _save_audio_bytes(data: bytes, suffix: str, label: str, root: str) -> str:
    ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
    path = os.path.join(root, f"{label}_{ts}{suffix}")
    with open(path, "wb") as f:
        f.write(data)
    return path


def _save_vocal_bytes(data: bytes, suffix: str, label: str) -> str:
    return _save_audio_bytes(data, suffix, label, VOCAL_UPLOAD_ROOT)


def _reset_vocal_processed_state():
    st.session_state["vocal_processed_path"] = None
    st.session_state["vocal_active_params"] = None
    st.session_state["vocal_active_mode_label"] = None
    # Naya raw vocal aaya to purana final mix bhi ab purana ho gaya - use bhi reset karein
    st.session_state["final_mix_path"] = None


def _run_vocal_processing(params: dict, mode_label: str):
    raw_path = st.session_state.get("vocal_raw_path")
    if not raw_path or not os.path.exists(raw_path):
        st.session_state["vocal_error"] = "पहले ऊपर से आवाज़ रिकॉर्ड करें या अपलोड करें।"
        return
    try:
        with st.spinner("आवाज़ प्रोसेस हो रही है... (नॉइज़-रिडक्शन → EQ → कम्प्रेशन → लिमिटर)"):
            audio, sr = me.load_vocal_audio(raw_path)
            noise_pct = st.session_state.get("vocal_noise_reduction_pct", 60)
            processed = me.process_vocal_full(audio, sr, params, noise_reduction_pct=noise_pct)
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            out_path = os.path.join(VOCAL_UPLOAD_ROOT, f"processed_{mode_label}_{ts}.wav")
            me.save_mono_wav(processed, out_path, sr)
        st.session_state["vocal_processed_path"] = out_path
        st.session_state["vocal_active_params"] = dict(params)
        st.session_state["vocal_active_mode_label"] = mode_label
        st.session_state["vocal_error"] = None
        st.session_state["final_mix_path"] = None  # naye vocal ke saath purana final mix invalid
    except me.VocalLoadError as e:
        st.session_state["vocal_error"] = str(e)
    except Exception as e:
        st.session_state["vocal_error"] = f"अनपेक्षित गड़बड़ी: {e}"


def _render_input_capture_section(session_prefix: str, mode_key: str, raw_path_key: str,
                                   raw_name_key: str, upload_root: str,
                                   record_label: str, uploader_label: str,
                                   on_new_audio=None):
    """
    Generic record-ya-upload capture block — mukhya vocal (Step 1) aur
    dedicated chorus track (naya, Part 2) dono isi ek function se banaye
    jaate hain, taaki code duplicate na ho।
    """
    mode_options = ["🎤 लाइव रिकॉर्ड करें", "📤 ऑडियो फ़ाइल अपलोड करें"]
    st.session_state[mode_key] = st.radio(
        "इनपुट तरीका चुनें", options=mode_options,
        index=mode_options.index(st.session_state[mode_key]),
        key=f"{session_prefix}_input_mode_radio", horizontal=True, label_visibility="collapsed",
    )

    if st.session_state[mode_key] == "🎤 लाइव रिकॉर्ड करें":
        try:
            recorded = st.audio_input(record_label, key=f"{session_prefix}_audio_input_widget")
        except AttributeError:
            recorded = None
            st.warning(
                "⚠️ आपके Streamlit वर्शन में लाइव रिकॉर्डिंग (st.audio_input) उपलब्ध नहीं है "
                "(`pip install --upgrade streamlit` करें, version ≥ 1.31 चाहिए)। "
                "तब तक कृपया 'फ़ाइल अपलोड करें' वाला तरीका इस्तेमाल करें।"
            )
        if recorded is not None:
            data = recorded.getvalue()
            size_mb = len(data) / (1024 * 1024)
            if size_mb > me.MAX_VOCAL_UPLOAD_MB:
                st.error(f"⚠️ रिकॉर्डिंग {size_mb:.1f} MB की है — {me.MAX_VOCAL_UPLOAD_MB} MB से छोटी होनी चाहिए।")
            else:
                path = _save_audio_bytes(data, ".wav", f"{session_prefix}_recorded", upload_root)
                if path != st.session_state.get(raw_path_key):
                    st.session_state[raw_path_key] = path
                    st.session_state[raw_name_key] = "लाइव रिकॉर्डिंग"
                    if on_new_audio:
                        on_new_audio()
    else:
        uploaded = st.file_uploader(
            uploader_label, type=["wav", "mp3"], key=f"{session_prefix}_file_uploader",
        )
        if uploaded is not None:
            size_mb = uploaded.size / (1024 * 1024)
            if size_mb > me.MAX_VOCAL_UPLOAD_MB:
                st.error(f"⚠️ फ़ाइल {size_mb:.1f} MB की है — {me.MAX_VOCAL_UPLOAD_MB} MB से छोटी होनी चाहिए।")
            else:
                suffix = os.path.splitext(uploaded.name)[1].lower() or ".wav"
                data = uploaded.getvalue()
                path = _save_audio_bytes(data, suffix, f"{session_prefix}_uploaded", upload_root)
                if uploaded.name != st.session_state.get(raw_name_key):
                    st.session_state[raw_path_key] = path
                    st.session_state[raw_name_key] = uploaded.name
                    if on_new_audio:
                        on_new_audio()


def _run_final_mix():
    """
    Part 2 ka poora "मिक्स इंजन" — polished main vocal + backing
    instrumental (agar Compose tab mein render hui ho) + dual-source
    crowd chorus (Auto-Clone ya Dedicated Chorus Track), sabko
    independent volume ke saath ek final stereo WAV mein jodta hai।
    """
    processed_path = st.session_state.get("vocal_processed_path")
    if not processed_path or not os.path.exists(processed_path):
        st.session_state["final_mix_error"] = (
            "पहले ऊपर '✨ ऑटो-वॉइस परफेक्ट करें' या 'कस्टम सेटिंग लगाएं' दबाकर अपनी आवाज़ प्रोसेस करें।"
        )
        return
    try:
        with st.spinner("फाइनल मिक्स तैयार हो रहा है... (crowd chorus + backing track + vocal)"):
            vocal_mono, sr = me.load_vocal_audio(processed_path)

            # ---- crowd chorus source chuno: auto-clone ya dedicated track ----
            crowd_stereo = None
            intensity = st.session_state.get("crowd_intensity_pct", 45)
            if intensity > 0:
                if st.session_state["crowd_source_mode"].startswith("🤖"):
                    crowd_source = vocal_mono
                else:
                    chorus_raw_path = st.session_state.get("chorus_raw_path")
                    if not chorus_raw_path or not os.path.exists(chorus_raw_path):
                        st.session_state["final_mix_error"] = (
                            "'कस्टम कोरस ट्रैक' मोड चुना है, लेकिन नीचे कोई अलग कोरस आवाज़ रिकॉर्ड/अपलोड नहीं की गई। "
                            "पहले वह आवाज़ भरें, या मोड बदलकर 'ऑटो-क्लोन' चुनें।"
                        )
                        return
                    crowd_source, crowd_sr = me.load_vocal_audio(chorus_raw_path, target_sr=sr)
                    crowd_source = me.noise_reduce_vocal(crowd_source, sr, strength_pct=40)
                    crowd_source = crowd_source

                seed = None
                if st.session_state.get("crowd_seed_lock"):
                    if st.session_state.get("crowd_last_seed") is None:
                        st.session_state["crowd_last_seed"] = int(np.random.default_rng().integers(0, 2**31 - 1))
                    seed = st.session_state["crowd_last_seed"]
                else:
                    st.session_state["crowd_last_seed"] = None  # lock off = हर बार नया crowd

                crowd_stereo = me.generate_crowd_chorus(
                    crowd_source if not st.session_state["crowd_source_mode"].startswith("🤖") else vocal_mono,
                    sr, num_voices=st.session_state.get("crowd_num_voices", 6),
                    intensity_pct=intensity, seed=seed,
                )

            # ---- backing instrumental (agar Compose tab mein render hui ho) ----
            backing_stereo = None
            backing_info = me.get_backing_track_for_overdub(st.session_state.get("music_wav_path"))
            if backing_info["available"]:
                backing_audio_mono, backing_sr = me.load_vocal_audio(backing_info["path"], target_sr=sr)
                backing_stereo = me._to_stereo(backing_audio_mono)

            final = me.mix_final_master(
                vocal_mono, sr, backing_stereo=backing_stereo, crowd_stereo=crowd_stereo,
                vocal_gain_db=st.session_state.get("mix_vocal_gain_db", 0.0),
                backing_gain_db=st.session_state.get("mix_backing_gain_db", -4.0),
                crowd_gain_db=st.session_state.get("mix_crowd_gain_db", -7.0),
            )
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            out_path = os.path.join(VOCAL_UPLOAD_ROOT, f"final_mix_{ts}.wav")
            me.save_wav(final, out_path, sr)
        st.session_state["final_mix_path"] = out_path
        st.session_state["final_mix_error"] = None
    except me.VocalLoadError as e:
        st.session_state["final_mix_error"] = str(e)
    except Exception as e:
        st.session_state["final_mix_error"] = f"अनपेक्षित गड़बड़ी: {e}"


def _render_vocal_tab():
    st.subheader("🎙️ Vocal — अपनी आवाज़ रिकॉर्ड/अपलोड करें और परफेक्ट बनाएं")
    st.caption("गाना, मंत्र या कथा अपनी असली आवाज़ में — फिर एक क्लिक में स्टूडियो-क्वालिटी साउंड, बैकिंग ट्रैक और भक्तों की भीड़ के साथ।")

    # -------------------------------------------------------------
    # 1. INPUT: Record vs Upload (मुख्य गायक/गायिका की आवाज़)
    # -------------------------------------------------------------
    st.markdown("#### 1️⃣ अपनी मुख्य आवाज़ कहाँ से लें")
    with st.expander("ℹ️ कौन सा तरीका चुनें?"):
        st.markdown(
            "- **🎤 लाइव रिकॉर्ड करें**: अभी, इसी वक़्त बोलना/गाना है तो यह चुनें — ब्राउज़र आपके माइक से सीधे रिकॉर्ड करेगा।\n"
            "- **📤 अपलोड करें**: अगर आपने पहले से मोबाइल के रिकॉर्डर ऐप या कहीं और आवाज़ रिकॉर्ड कर रखी है (WAV या MP3 फ़ाइल), "
            "तो वह फ़ाइल यहाँ सीधे भेज दें — दोबारा बोलने की ज़रूरत नहीं।\n"
            "- फ़ाइल **10 MB से बड़ी** नहीं होनी चाहिए (लगभग 8-10 मिनट की सामान्य क्वालिटी की रिकॉर्डिंग)।"
        )
    _render_input_capture_section(
        session_prefix="vocal", mode_key="vocal_input_mode",
        raw_path_key="vocal_raw_path", raw_name_key="vocal_raw_name",
        upload_root=VOCAL_UPLOAD_ROOT,
        record_label="🎤 यहाँ दबाकर रिकॉर्ड करें",
        uploader_label="ऑडियो फ़ाइल चुनें (WAV/MP3, अधिकतम 10MB)",
        on_new_audio=_reset_vocal_processed_state,
    )

    if st.session_state.get("vocal_raw_path") and os.path.exists(st.session_state["vocal_raw_path"]):
        st.success(f"✅ आवाज़ तैयार है: **{st.session_state['vocal_raw_name']}**")
        st.audio(st.session_state["vocal_raw_path"])
    else:
        st.info("ℹ️ ऊपर से रिकॉर्ड करें या फ़ाइल अपलोड करें, फिर नीचे प्रोसेसिंग शुरू करें।")
        return

    st.markdown("---")

    # -------------------------------------------------------------
    # 2. OVERDUB SYNC — बैकिंग ट्रैक के साथ गाना (मल्टी-ट्रैक ओवरडबिंग)
    # -------------------------------------------------------------
    st.markdown("#### 2️⃣ 🎼 बैकिंग ट्रैक के साथ सिंक में गाएं (Overdub)")
    backing_info = me.get_backing_track_for_overdub(st.session_state.get("music_wav_path"))
    if backing_info["available"]:
        st.success(backing_info["message"])
        st.audio(backing_info["path"])
        with st.expander("ℹ️ ठीक से सिंक में गाने का तरीका"):
            st.markdown(
                "1. **हेडफ़ोन/इयरफ़ोन लगाएं** — इससे ऊपर बज रही instrumental आपके माइक में लीक नहीं होगी।\n"
                "2. ऊपर वाला ▶️ बटन दबाकर instrumental प्ले करें।\n"
                "3. उसी वक़्त, ऊपर '1️⃣' सेक्शन में 🎤 रिकॉर्डिंग बटन दबाकर ताल के साथ गाना/मंत्र बोलना शुरू करें।\n"
                "4. रिकॉर्डिंग खत्म होने पर वह अपने-आप ऊपर '1️⃣' सेक्शन में भर जाएगी — फिर नीचे प्रोसेसिंग शुरू करें।\n\n"
                "📌 ध्यान दें: instrumental चलाना और मिक gaana साथ-साथ, एक ही ब्राउज़र टैब में हो सकता है — "
                "ब्राउज़र प्लेबैक (स्पीकर/हेडफ़ोन) और रिकॉर्डिंग (माइक) दोनों अलग-अलग, एक साथ काम करते हैं।"
            )
    else:
        st.info(backing_info["message"])

    st.markdown("---")

    # -------------------------------------------------------------
    # 3. AUTO-PERFECT MAGIC BUTTON
    # -------------------------------------------------------------
    st.markdown("#### 3️⃣ एक क्लिक में तैयार")
    if st.button(
        "✨ ऑटो-वॉइस परफेक्ट करें", type="primary", key="vocal_auto_perfect_btn", use_container_width=True,
        help="आपकी कच्ची आवाज़ पर नॉइज़-रिडक्शन + भक्ति-संगीत के लिए पहले से तय, संतुलित सेटिंग्स लगाकर एक स्टूडियो-जैसा नतीजा देगा।",
    ):
        _run_vocal_processing(me.AUTO_PERFECT_PRESET, "auto")

    st.caption(
        "यह बटन आवाज़ पर पहले हल्का नॉइज़-रिडक्शन, फिर भक्ति-संगीत के लिए पहले से तय किए गए स्मार्ट EQ, compression, "
        "खनक (brilliance) और सुरीलापन (warmth) अपने आप लगा देता है — production-ready साउंड, बिना किसी सेटिंग छेड़े।"
    )
    with st.expander("ℹ️ यह बटन अंदर क्या-क्या करता है? (पूरी जानकारी)"):
        st.markdown(
            "एक क्लिक में यह सब अपने-आप, बताए गए क्रम में लगता है:\n\n"
            "1. **नॉइज़-रिडक्शन** — रिकॉर्डिंग की हल्की background hiss/hum (पंखा, कमरे की गूंज) कम करता है, ताकि बाकी सारी प्रोसेसिंग साफ़ आवाज़ पर लगे\n"
            "2. **भारी आवाज़ों की गड़बड़ी हटाना** — बोलने में जो हल्की 'बॉक्स जैसी' या धीमी गूंज होती है, उसे कम करता है ताकि आवाज़ साफ़ निकले\n"
            "3. **भारीपन/वजन थोड़ा बढ़ाना** — आवाज़ को थोड़ी गहराई/मज़बूती देता है\n"
            "4. **तीखापन थोड़ा बढ़ाना** — शब्द ज़्यादा साफ़ सुनाई दें, इसके लिए हल्का सुधार\n"
            "5. **सुरीलापन/मिठास जोड़ना** — आवाज़ को नरम, सुनने में अच्छा और 'गर्म' बनाता है\n"
            "6. **खनक (brilliance) जोड़ना** — आवाज़ में हल्की चमक/तेज़ी लाता है, जिससे वो पेशेवर लगे\n"
            "7. **आवाज़ का उतार-चढ़ाव बराबर करना (compression)** — बहुत धीमे और बहुत तेज़ हिस्सों के बीच का फ़र्क़ कम करता है\n"
            "8. **मास्टर लिमिटर** — आख़िर में कोई भी क्लिपिंग/चटकाहट न आए, यह पक्का करता है\n\n"
            "यह सारी सेटिंग्स **संतुलित (moderate)** रखी गई हैं — पसंद न आए तो नीचे 'कस्टमाइज़' मोड से खुद बदल सकते हैं। "
            "इस बटन से सिर्फ़ आपकी अपनी आवाज़ पॉलिश होती है — भीड़ (crowd) और बैकिंग ट्रैक नीचे '5️⃣ फाइनल मिक्स' सेक्शन में जुड़ते हैं।"
        )

    # -------------------------------------------------------------
    # 4. ADVANCED CUSTOMIZE MODE
    # -------------------------------------------------------------
    st.markdown("---")
    st.session_state["vocal_advanced_mode"] = st.checkbox(
        "⚙️ एडवांस्ड कस्टमाइज़/एडिट मोड", value=st.session_state["vocal_advanced_mode"],
        key="vocal_advanced_mode_checkbox",
        help="चेक करने पर हर सेटिंग को खुद अपनी पसंद के हिसाब से घटा-बढ़ा सकते हैं। शुरुआत में इसे बंद ही रहने दें।",
    )

    if st.session_state["vocal_advanced_mode"]:
        st.markdown("#### खुद सेट करें")
        st.caption(
            "हर slider के नीचे एक 'ℹ️ यह क्या करता है?' बॉक्स है — बिना खोले भी slider पर mouse ले जाकर "
            "छोटी जानकारी (tooltip) दिख जाएगी। घबराएं नहीं, कभी भी 'Auto-Perfect' बटन दोबारा दबाकर मूल सेटिंग पर लौट सकते हैं।"
        )

        st.session_state["vocal_noise_reduction_pct"] = st.slider(
            "🧹 नॉइज़-रिडक्शन ताकत (Noise Reduction)", min_value=0, max_value=100,
            value=int(st.session_state.get("vocal_noise_reduction_pct", 60)), step=5,
            key="vocal_noise_reduction_slider",
            help="बैकग्राउंड हिस/हम कितनी मज़बूती से कम करें। 0 = कुछ मत करो, 100 = सबसे ज़्यादा (लेकिन बहुत ज़्यादा पर आवाज़ थोड़ी 'पानी के अंदर जैसी' लग सकती है)।",
        )

        cv = st.session_state["vocal_custom_values"]
        for key, label, min_v, max_v, unit in SLIDER_SPECS:
            step = 1 if unit == "%" else 0.5
            info = SLIDER_INFO[key]
            cv[key] = st.slider(
                f"{label}", min_value=float(min_v), max_value=float(max_v),
                value=float(cv.get(key, 0)), step=float(step),
                format=f"%.1f {unit}" if unit == "dB" else f"%.0f {unit}",
                key=f"vocal_slider_{key}",
                help=info["kya_hai"],
            )
            with st.expander(f"ℹ️ '{label}' यह क्या करता है? (पूरी जानकारी)"):
                st.markdown(
                    f"**यह है क्या**: {info['kya_hai']}\n\n"
                    f"**बढ़ाने पर**: {info['badhane_par']}\n\n"
                    f"**बहुत ज़्यादा बढ़ाने पर सावधानी**: {info['zyada_par']}\n\n"
                    f"**घटाने/0 पर रखने पर**: {info['ghatane_par']}"
                )
        st.session_state["vocal_custom_values"] = cv

        cc1, cc2 = st.columns([1, 1])
        with cc1:
            if st.button(
                "🎚️ कस्टम सेटिंग लगाएं", key="vocal_apply_custom_btn", use_container_width=True,
                help="ऊपर की slider वैल्यू के साथ आवाज़ को फिर से प्रोसेस करेगा।",
            ):
                _run_vocal_processing(cv, "custom")
        with cc2:
            if st.button(
                "↩️ Auto-Perfect वैल्यू पर वापस लाएं", key="vocal_reset_to_auto_btn", use_container_width=True,
                help="सारी sliders को वापस डिफ़ॉल्ट/संतुलित (Auto-Perfect) वैल्यू पर सेट कर देगा।",
            ):
                st.session_state["vocal_custom_values"] = dict(me.AUTO_PERFECT_PRESET)
                st.rerun()

    if st.session_state.get("vocal_error"):
        st.error(f"❌ {st.session_state['vocal_error']}")

    processed_path = st.session_state.get("vocal_processed_path")
    if processed_path and os.path.exists(processed_path):
        st.markdown("---")
        st.markdown("#### 🎧 आपकी अकेली पॉलिश आवाज़ (बिना भीड़/बैकिंग के)")
        mode_badge = "✨ Auto-Perfect" if st.session_state["vocal_active_mode_label"] == "auto" else "⚙️ Custom"
        st.caption(f"मोड: **{mode_badge}** — ऊपर वाली मूल आवाज़ (Step 1) से तुलना करके सुनें कि क्या फ़र्क़ आया।")
        st.audio(processed_path)

    st.markdown("---")

    # -------------------------------------------------------------
    # 5. DEDICATED CHORUS TRACK (Part 2) — अलग कोरस आवाज़ का इनपुट
    # -------------------------------------------------------------
    st.markdown("#### 4️⃣ 🙏 कस्टम कोरस ट्रैक (Dedicated Backup Vocal) — वैकल्पिक")
    st.caption(
        "अगर चाहें, तो अपनी ही आवाज़ की क्लोन बनाने के बजाय, किसी दोस्त/परिवार के सदस्य की एक **अलग, असली आवाज़** "
        "यहाँ रिकॉर्ड/अपलोड करें। इंजन इसी आवाज़ को भीड़ (crowd) बनाने का source मानेगा — जिससे एक बड़ा, असली, "
        "बार-बार न दोहराने वाला मंदिर जैसा माहौल बनेगा।"
    )
    with st.expander("ℹ️ यह ज़रूरी है क्या?"):
        st.markdown(
            "नहीं — बिल्कुल वैकल्पिक है। अगर यहाँ कुछ नहीं भरा, तो नीचे '5️⃣ फाइनल मिक्स' सेक्शन में "
            "**'🤖 ऑटो-क्लोन'** मोड चुनकर आपकी अपनी आवाज़ से ही भीड़ बना दी जाएगी। "
            "अगर सच में अलग-अलग असली आवाज़ों जैसा वैरायटी चाहिए, तो यहाँ किसी और की आवाज़ भर दें और "
            "नीचे **'🙏 कस्टम कोरस ट्रैक'** मोड चुनें।"
        )
    _render_input_capture_section(
        session_prefix="chorus", mode_key="chorus_input_mode",
        raw_path_key="chorus_raw_path", raw_name_key="chorus_raw_name",
        upload_root=CHORUS_UPLOAD_ROOT,
        record_label="🎤 कोरस आवाज़ यहाँ रिकॉर्ड करें",
        uploader_label="कोरस ऑडियो फ़ाइल चुनें (WAV/MP3, अधिकतम 10MB)",
        on_new_audio=lambda: st.session_state.update({"final_mix_path": None}),
    )
    if st.session_state.get("chorus_raw_path") and os.path.exists(st.session_state["chorus_raw_path"]):
        st.success(f"✅ कोरस आवाज़ तैयार है: **{st.session_state['chorus_raw_name']}**")
        st.audio(st.session_state["chorus_raw_path"])
    else:
        st.caption("ℹ️ अभी कोई अलग कोरस आवाज़ नहीं भरी गई है (वैकल्पिक है)।")

    st.markdown("---")

    # -------------------------------------------------------------
    # 6. CROWD CHORUS ENGINE SETTINGS (Part 2)
    # -------------------------------------------------------------
    st.markdown("#### 5️⃣ 🙏🎚️ दोहरा-स्रोत क्राउड कोरस इंजन (Dual-Source Crowd Chorus)")
    st.caption(
        "आपकी अकेली आवाज़ के पीछे कई अलग-अलग, असली-जैसी आवाज़ों (बच्चे, महिला, पुरुष, बुज़ुर्ग जैसी) की एक "
        "पूरी भीड़ बनाता है — हर एक की अपनी pitch, timing और stereo जगह — ताकि सच में मंदिर/सत्संग जैसा भरा-पूरा माहौल बने।"
    )
    crowd_mode_options = ["🤖 ऑटो-क्लोन (मेरी अपनी आवाज़ से)", "🙏 कस्टम कोरस ट्रैक (ऊपर वाली अलग आवाज़ से)"]
    st.session_state["crowd_source_mode"] = st.radio(
        "भीड़ किस आवाज़ से बने?", options=crowd_mode_options,
        index=crowd_mode_options.index(st.session_state["crowd_source_mode"])
        if st.session_state["crowd_source_mode"] in crowd_mode_options else 0,
        key="crowd_source_mode_radio",
        help="'ऑटो-क्लोन' आपकी ही पॉलिश आवाज़ से भीड़ बनाता है। 'कस्टम कोरस ट्रैक' ऊपर भरी गई अलग आवाज़ से — ज़्यादा असली वैरायटी के लिए बेहतर।",
    )
    with st.expander("ℹ️ कौन सी 'आवाज़ की किस्में' शामिल होंगी?"):
        for profile in me.CROWD_VOICE_PROFILES:
            st.markdown(f"- {profile['label']}")
        st.caption("हर बार अलग-अलग सटीक pitch/timing/pan रैंडम तरीके से चुनी जाती है, ताकि क्लोन कभी हूबहू एक जैसे न लगें।")

    cs1, cs2 = st.columns(2)
    with cs1:
        st.session_state["crowd_num_voices"] = st.slider(
            "👥 कितनी आवाज़ें जोड़ें (Clones)", min_value=2, max_value=12,
            value=int(st.session_state.get("crowd_num_voices", 6)), step=1,
            key="crowd_num_voices_slider",
            help="ज़्यादा clones = बड़ी, भरी-पूरी भीड़; कम clones = हल्का, सादा असर।",
        )
    with cs2:
        st.session_state["crowd_intensity_pct"] = st.slider(
            "🙏 भीड़ की तीव्रता (Crowd Intensity)", min_value=0, max_value=100,
            value=int(st.session_state.get("crowd_intensity_pct", 45)), step=5,
            key="crowd_intensity_slider",
            help="0% = कोई भीड़ नहीं, सिर्फ़ आपकी अकेली आवाज़। ज़्यादा % = भीड़ ज़्यादा सुनाई देगी, लेकिन बहुत ज़्यादा पर आपकी असली आवाज़ दब सकती है।",
        )

    st.session_state["crowd_seed_lock"] = st.checkbox(
        "🔒 इस भीड़ को लॉक करें (दोबारा render करने पर भी वही भीड़ मिले)", value=st.session_state.get("crowd_seed_lock", False),
        key="crowd_seed_lock_checkbox",
        help="चेक न करें तो हर बार '🎬 फाइनल मिक्स बनाएं' दबाने पर एक बिल्कुल नई भीड़ बनेगी (ज़्यादा वैरायटी, YouTube के लिए बेहतर)। चेक करने पर एक बार बनी भीड़ बार-बार दोबारा इस्तेमाल होगी।",
    )

    st.markdown("---")

    # -------------------------------------------------------------
    # 7. FINAL MIX ENGINE (Part 2)
    # -------------------------------------------------------------
    st.markdown("#### 6️⃣ 🎬 फाइनल मिक्स — वोकल + बैकिंग ट्रैक + भीड़, सबको एक साथ जोड़ें")
    st.caption("तीनों का अपना अलग वॉल्यूम (dB) रखें और एक तैयार, बजाने लायक फाइनल गाना बनाएं।")

    mg1, mg2, mg3 = st.columns(3)
    with mg1:
        st.session_state["mix_vocal_gain_db"] = st.slider(
            "🎤 वोकल वॉल्यूम (dB)", min_value=-12.0, max_value=12.0,
            value=float(st.session_state.get("mix_vocal_gain_db", 0.0)), step=0.5,
            key="mix_vocal_gain_slider",
        )
    with mg2:
        st.session_state["mix_backing_gain_db"] = st.slider(
            "🎼 बैकिंग ट्रैक वॉल्यूम (dB)", min_value=-24.0, max_value=6.0,
            value=float(st.session_state.get("mix_backing_gain_db", -4.0)), step=0.5,
            key="mix_backing_gain_slider",
        )
    with mg3:
        st.session_state["mix_crowd_gain_db"] = st.slider(
            "🙏 भीड़ वॉल्यूम (dB)", min_value=-24.0, max_value=6.0,
            value=float(st.session_state.get("mix_crowd_gain_db", -7.0)), step=0.5,
            key="mix_crowd_gain_slider",
        )

    if st.button(
        "🎬 फाइनल मिक्स बनाएं", type="primary", key="final_mix_btn", use_container_width=True,
        help="ऊपर पॉलिश की गई आवाज़, Compose टैब की instrumental (अगर बनी हो), और भीड़-कोरस — सबको मिलाकर एक फाइनल WAV बनाएगा।",
    ):
        _run_final_mix()

    if st.session_state.get("final_mix_error"):
        st.error(f"❌ {st.session_state['final_mix_error']}")

    final_mix_path = st.session_state.get("final_mix_path")
    if final_mix_path and os.path.exists(final_mix_path):
        st.markdown("---")
        st.markdown("#### 🎧 फाइनल तैयार गाना")
        st.audio(final_mix_path)
        with open(final_mix_path, "rb") as f:
            st.download_button(
                "⬇️ फाइनल मिक्स डाउनलोड करें (WAV)", data=f,
                file_name=os.path.basename(final_mix_path), mime="audio/wav",
                key="final_mix_download_btn",
                help="इस पूरी तरह तैयार फ़ाइल को सीधे YouTube पर अपलोड करने से पहले Video Generator में इस्तेमाल करें।",
            )
        st.info(
            "📌 इस फाइनल WAV फ़ाइल को **🎬 Video Generator** मोड में मुख्य ऑडियो की तरह अपलोड करें — "
            "इसमें आपकी आवाज़, इंस्ट्रूमेंटल और भीड़-कोरस, तीनों पहले से मिक्स हैं।"
        )


def _render_midi_viewer_tab():
    st.subheader("👁️ MIDI Viewer — हर ट्रैक की piano-roll")
    with st.expander("ℹ️ यह screen क्या दिखाती है?"):
        st.markdown(
            "यह एक 'नक़्शा' है कि Compose टैब में लिखी script से **असल में क्या-क्या बना** — "
            "हर साज़ (track) की एक अलग पंक्ति (row) है, और उसमें बनी हर पट्टी (bar) एक स्वर या ताल की चोट है। "
            "**पट्टी जितनी लंबी, वो स्वर/चोट उतनी देर बजेगी।** धुंधली खड़ी लाइनें बताती हैं कि हर ताल-चक्र कहाँ से "
            "नया शुरू हो रहा है। नीचे 'Raw event list' में हर एक स्वर का ठीक-ठीक समय भी टेबल में देख सकते हैं।"
        )
    comp = st.session_state.get("music_composition")
    if comp is None:
        st.info("ℹ️ पहले 'Compose' टैब में एक script render करें, फिर यहाँ हर track का timing/notes दिखेगा।")
        return

    st.caption(
        f"ताल: **{comp.taal}** • tempo: **{comp.tempo_bpm} BPM** • cycles: **{comp.cycles}** • "
        f"कुल लंबाई: **{comp.total_duration_sec:.1f}s**"
    )

    fig, ax = plt.subplots(figsize=(11, max(3, 1.2 * len(comp.tracks))))
    row_height = 0.8
    yticks = []
    ylabels = []

    for row_i, track in enumerate(comp.tracks):
        color = TRACK_COLORS.get(track.instrument, "#7f8c8d")
        y_center = row_i * row_height
        # डफली को छोड़कर बाकी percussion ke events mein hamesha midi_pitch
        # None hota hai; डफली अगर 'notes:' (melodic mode) se bani ho to
        # uske events mein asli pitch hoti hai — is check se dono सही
        # style mein sahi tarike se dikhte hain (yeh Part 1 ka ek purana
        # bug bhi theek karta hai, jahan sirf 'tabla' ko bar-style milti
        # thi aur damru/nagada/temple_bell khaali reh jaate the).
        is_pitched_track = any(ev.midi_pitch is not None for ev in track.events)
        if track.instrument in me.PERCUSSION_TYPES and not is_pitched_track:
            for ev in track.events:
                strength = "heavy" if ("heavy" in ev.label or "sam" in ev.label or "tali" in ev.label) else (
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


def _handoff_to_video_generator(path: str, source_label: str):
    """
    Part 3 ka सीधा handoff — chuni hui audio file ke bytes seedhe
    st.session_state['bg_music_audio'] mein daal deta hai। Baba Web
    Studio ke core app (Video Generator mode) mein Track 3 (background
    music) ya Track 5 (mantra audio loop) isi session_state key se apna
    audio uthaa sakte hain, bina manual download+re-upload kiye।
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
        st.session_state["bg_music_audio"] = data
        st.session_state["bg_music_audio_source"] = source_label
        st.success(
            f"✅ '{source_label}' अब सीधे 🎬 Video Generator मोड के Track 3/5 के लिए तैयार है — "
            f"वहां जाकर इस्तेमाल करें, दोबारा डाउनलोड/अपलोड करने की ज़रूरत नहीं।"
        )
    except Exception as e:
        st.error(f"❌ Handoff करते वक़्त गड़बड़ी: {e}")


def _render_export_tab():
    st.subheader("📤 Export")

    final_mix_path = st.session_state.get("final_mix_path")
    if final_mix_path and os.path.exists(final_mix_path):
        st.markdown("**🎉 फाइनल मिक्स (वोकल + बैकिंग + भीड़, तीनों साथ)**")
        st.caption("यह Vocal टैब में तैयार हुआ पूरा गाना है — सीधे YouTube पर अपलोड करने लायक।")
        st.audio(final_mix_path)
        fm_col1, fm_col2 = st.columns(2)
        with fm_col1:
            with open(final_mix_path, "rb") as f:
                st.download_button(
                    "⬇️ फाइनल मिक्स डाउनलोड करें (WAV)", data=f, file_name=os.path.basename(final_mix_path),
                    mime="audio/wav", key="export_final_mix_download_btn", use_container_width=True,
                )
        with fm_col2:
            if st.button("🎬 सीधे वीडियो जनरेटर (Track 3/5) में भेजें", key="export_final_mix_handoff_btn",
                         type="primary", use_container_width=True,
                         help="डाउनलोड किए बिना, यह फाइनल मिक्स सीधे Video Generator मोड को दे देगा।"):
                _handoff_to_video_generator(final_mix_path, os.path.basename(final_mix_path))
        st.markdown("---")

    wav_path = st.session_state.get("music_wav_path")
    midi_path = st.session_state.get("music_midi_path")

    if not wav_path or not os.path.exists(wav_path):
        st.info("ℹ️ पहले 'Compose' टैब में render करें, फिर यहाँ से files download कर सकते हैं।")
        return

    st.markdown("**🎧 Audio (WAV) — सिर्फ़ इंस्ट्रूमेंटल**")
    st.caption("यह वही तैयार इंस्ट्रूमेंटल है जो Compose टैब में सुना था — असली, बजाने लायक ऑडियो फ़ाइल (बिना वोकल के)।")
    st.audio(wav_path)
    inst_col1, inst_col2 = st.columns(2)
    with inst_col1:
        with open(wav_path, "rb") as f:
            st.download_button(
                "⬇️ इंस्ट्रूमेंटल WAV डाउनलोड करें", data=f, file_name=os.path.basename(wav_path),
                mime="audio/wav", key="ms_download_wav_btn", use_container_width=True,
                help="इस फ़ाइल को Video Generator मोड में या किसी भी प्लेयर में इस्तेमाल कर सकते हैं।",
            )
    with inst_col2:
        if st.button("🎬 सीधे वीडियो जनरेटर (Track 3/5) में भेजें", key="export_instrumental_handoff_btn",
                     use_container_width=True,
                     help="डाउनलोड किए बिना, यह इंस्ट्रूमेंटल सीधे Video Generator मोड को दे देगा।"):
            _handoff_to_video_generator(wav_path, os.path.basename(wav_path))

    if st.session_state.get("bg_music_audio_source"):
        st.caption(f"📌 अभी Video Generator के लिए तैयार: **{st.session_state['bg_music_audio_source']}**")

    if midi_path and os.path.exists(midi_path):
        st.markdown("**🎼 MIDI (.mid — MuseScore या किसी भी DAW में खोल सकते हैं)**")
        st.caption(
            "MIDI ऑडियो नहीं है, यह सिर्फ़ 'नोट्स की सूची' है — कौन सा स्वर कब-कब बजा। "
            "इसे मुफ़्त सॉफ़्टवेयर MuseScore में खोलकर देख/बदल सकते हैं, अगर आगे और बारीकी से एडिट करना हो।"
        )
        with open(midi_path, "rb") as f:
            st.download_button(
                "⬇️ MIDI डाउनलोड करें", data=f, file_name=os.path.basename(midi_path),
                mime="audio/midi", key="ms_download_midi_btn",
                help="अगर आपको MuseScore जैसे नोटेशन सॉफ़्टवेयर में एडिट करना हो, तो यह फ़ाइल वहाँ खुलेगी।",
            )
    else:
        st.caption("ℹ️ MIDI export उपलब्ध नहीं है (pretty_midi install नहीं है)।")

    st.markdown("---")
    if final_mix_path and os.path.exists(final_mix_path):
        st.info(
            "📌 ऊपर वाला **'फाइनल मिक्स'** ही सीधे इस्तेमाल करने लायक है (वोकल+बैकिंग+भीड़ मिला हुआ)। "
            "नीचे वाली सिर्फ़-इंस्ट्रूमेंटल WAV/MIDI फ़ाइलें सिर्फ़ तब चाहिए जब आपको अलग-अलग हिस्से चाहिए हों।"
        )
    else:
        st.info(
            "📌 इस इंस्ट्रूमेंटल WAV फ़ाइल को Vocal टैब में अपनी आवाज़ के साथ मिलाकर एक फाइनल मिक्स बना सकते हैं, "
            "या इसे मैन्युअली **🎬 Video Generator** मोड के Track 3/Track 5 में अपलोड करें।"
        )


def render_music_studio_ui():
    _init_state()
    st.title("🎼 Music Studio")
    st.caption("टेक्स्ट स्क्रिप्ट से ताल+सरगम कंपोज़ करें, अपनी आवाज़ जोड़ें, और मल्टी-इंस्ट्रूमेंट ऑडियो+MIDI बनाएं।")

    tab1, tab2, tab3, tab4 = st.tabs(["✍️ Compose", "🎙️ Vocal", "👁️ MIDI Viewer", "📤 Export"])
    with tab1:
        _render_compose_tab()
    with tab2:
        _render_vocal_tab()
    with tab3:
        _render_midi_viewer_tab()
    with tab4:
        _render_export_tab()


if __name__ == "__main__":
    st.set_page_config(page_title="Music Studio", page_icon="🎼", layout="wide")
    render_music_studio_ui()
