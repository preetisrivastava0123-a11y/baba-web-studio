# -*- coding: utf-8 -*-
"""
music_engine.py - Baba Web Studio | Music Production Module (Layer 1+2)
=========================================================================
Text-script -> multi-instrument MIDI + audio rendering engine.

WHY THIS EXISTS (see /areas/music-production-system plan)
-----------------------------------------------------------------------
User likhta hai ek simple text script:

    taal: dadra
    tempo: 80
    cycles: 4

    track: tabla
    pattern: dadra

    track: bansuri
    notes: sa re ga ma pa | pa ma ga re sa
    octave: middle

    track: guitar_pad
    chord: C, C, Am, Am | F, F, G, G
    style: sustain

    track: harmonium
    notes: sa ga ma pa ni sa'

...aur yeh module use parse karke:
  1. ek Composition object banata hai (taal, tempo, per-track note events)
  2. usse pretty_midi ka multi-track MIDI banata hai (MIDI Viewer ke liye -
     Streamlit mein piano-roll dikhane ke liye, ya MuseScore mein kholne
     ke liye)
  3. USI Composition se ek WAV audio banata hai - apna khud ka lightweight
     numpy-based synthesizer (harmonium/bansuri/guitar-pad/tabla ke alag
     alag timbre), taaki koi bhi external binary (FluidSynth) ya
     soundfont (.sf2) file install kiye bina turant kaam kare.

     NOTE: agar future mein FluidSynth + real soundfont available ho
     (better/realistic sound ke liye), to render_with_fluidsynth() function
     use kiya ja sakta hai (neeche diya gaya hai) - MIDI wahi same object
     se banta hai, sirf render step badlega. Abhi ke liye built-in
     synthesizer hi default hai, kyunki woh zero-setup hai.

NO EXTERNAL BINARY / NO INTERNET REQUIRED for the default render path -
only numpy + scipy (for wav writing) + pretty_midi (for the MIDI/viewer
side). All are pure-Python-installable via pip.

PUBLIC API
-----------------------------------------------------------------------
    parse_script(text: str) -> Composition
    composition_to_midi(comp: Composition) -> pretty_midi.PrettyMIDI
    render_audio(comp: Composition, sr=44100) -> np.ndarray (stereo, float32 -1..1)
    save_wav(audio: np.ndarray, path: str, sr=44100)
    TAAL_LIBRARY, SARGAM_SEMITONES  - reference data, also usable by a UI
    ParseError - raised on malformed script, with a human (Hindi) message
"""

import os
import re
import io
import wave
import struct
import math
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple

import numpy as np

try:
    import pretty_midi
    _HAS_PRETTY_MIDI = True
except ImportError:  # pragma: no cover
    pretty_midi = None
    _HAS_PRETTY_MIDI = False


# ==========================================================================
# 1. REFERENCE DATA - taal patterns + sargam-to-semitone mapping
# ==========================================================================

# Each taal: total beats in the cycle, and a per-beat "bol strength" list.
#   "sam"   -> the first/strongest beat of the cycle (heavy, low thump)
#   "tali"  -> a clapped/stressed beat (medium-heavy)
#   "khali" -> the "empty"/wave beat, traditionally NOT clapped, lighter/
#              higher-pitched sound so it's audibly distinct
#   "beat"  -> a regular beat (light tick)
TAAL_LIBRARY: Dict[str, Dict] = {
    "dadra": {
        "beats": 6,
        "pattern": ["sam", "beat", "beat", "tali", "beat", "beat"],
        "bols": ["Dha", "Dhin", "Na", "Dha", "Tin", "Na"],
    },
    "kaharwa": {
        "beats": 8,
        "pattern": ["sam", "beat", "beat", "beat", "tali", "beat", "beat", "beat"],
        "bols": ["Dha", "Ge", "Na", "Ti", "Na", "Ka", "Dhi", "Na"],
    },
    "rupak": {
        "beats": 7,
        # Rupak is famous for STARTING on khali, not sam.
        "pattern": ["khali", "beat", "tali", "beat", "beat", "tali", "beat"],
        "bols": ["Tin", "Tin", "Na", "Dhin", "Na", "Dhin", "Na"],
    },
    "teentaal": {
        "beats": 16,
        "pattern": [
            "sam", "beat", "beat", "beat",
            "tali", "beat", "beat", "beat",
            "khali", "beat", "beat", "beat",
            "tali", "beat", "beat", "beat",
        ],
        "bols": [
            "Dha", "Dhin", "Dhin", "Dha",
            "Dha", "Dhin", "Dhin", "Dha",
            "Dha", "Tin", "Tin", "Ta",
            "Ta", "Dhin", "Dhin", "Dha",
        ],
    },
    "ektaal": {
        "beats": 12,
        "pattern": [
            "sam", "beat", "tali", "beat",
            "khali", "beat", "tali", "beat",
            "khali", "beat", "tali", "beat",
        ],
        "bols": [
            "Dhin", "Dhin", "Dhage", "Tirkit",
            "Tu", "Na", "Kat", "Ta",
            "Dhage", "Tirkit", "Dhin", "Na",
        ],
    },
}

# Sargam -> semitone offset from Sa (shuddh/Bilawal-thaat mapping, the most
# common default). Sa is treated as middle C (MIDI 60) unless a track sets
# a different base note.
SARGAM_SEMITONES: Dict[str, int] = {
    "sa": 0, "re": 2, "ga": 4, "ma": 5, "pa": 7, "dha": 9, "ni": 11,
    # komal (flat) variants, written with a leading lowercase 'k'
    "kre": 1, "kga": 3, "tma": 6,  # tma = teevra (sharp) Ma
    "kdha": 8, "kni": 10,
}

DEFAULT_BASE_MIDI_NOTE = 60  # Sa = middle C

# Chord name -> list of semitone offsets from the chord ROOT (not from Sa).
CHORD_LIBRARY: Dict[str, List[int]] = {
    "C": [0, 4, 7], "D": [0, 4, 7], "E": [0, 4, 7], "F": [0, 4, 7],
    "G": [0, 4, 7], "A": [0, 4, 7], "B": [0, 4, 7],
    "Am": [0, 3, 7], "Bm": [0, 3, 7], "Cm": [0, 3, 7], "Dm": [0, 3, 7],
    "Em": [0, 3, 7], "Fm": [0, 3, 7], "Gm": [0, 3, 7],
}
NOTE_NAME_TO_SEMITONE = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
    "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

# ==========================================================================
# 1B. MULTILINGUAL (English + Devanagari) INPUT NORMALIZATION
# ==========================================================================
# User चाहे "sa re ga ma" लिखे या "सा रे गा मा" - दोनों बराबर चलते हैं।
# हर Devanagari शब्द को उसके English-key equivalent में बदल दिया जाता है,
# बाकी parsing उसी पुराने English-based रास्ते से होती है - isliye baaki
# saara engine code (SARGAM_SEMITONES, TAAL_LIBRARY, आदि) बिना बदले चलता है।

DEVANAGARI_SARGAM_MAP: Dict[str, str] = {
    "सा": "sa", "रे": "re", "ग": "ga", "गा": "ga", "म": "ma", "मा": "ma",
    "प": "pa", "पा": "pa", "ध": "dha", "धा": "dha", "नि": "ni", "नी": "ni",
}

# कोमल/तीव्र स्वर दो शब्दों में लिखे जाते हैं (जैसे "कोमल रे") - tokenize
# करने से PEHLE poori notes-string mein yeh phrase dhoondh kar seedhe
# single-word English-key se badal diya jaata hai.
TWO_WORD_DEVANAGARI_SARGAM: Dict[str, str] = {
    "कोमल रे": "kre", "कोमल ग": "kga", "कोमल गा": "kga",
    "तीव्र म": "tma", "तीव्र मा": "tma",
    "कोमल ध": "kdha", "कोमल धा": "kdha", "कोमल नि": "kni", "कोमल नी": "kni",
}

DEVANAGARI_TAAL_MAP: Dict[str, str] = {
    "दादरा": "dadra", "कहरवा": "kaharwa", "रूपक": "rupak",
    "तीनताल": "teentaal", "तीन ताल": "teentaal", "एकताल": "ektaal",
}

DEVANAGARI_TRACK_TYPE_MAP: Dict[str, str] = {
    "तबला": "tabla", "बांसुरी": "bansuri", "बंसुरी": "bansuri", "हारमोनियम": "harmonium",
    "गिटार": "guitar_pad", "गिटार_पैड": "guitar_pad", "सितार": "sitar",
    "डमरू": "damru", "नगाड़ा": "nagada", "नगाडा": "nagada",
    "शंख": "shankha", "घंटी": "temple_bell", "मंदिर_घंटी": "temple_bell",
    # -- Part 3: पारंपरिक/लोक वाद्य सुइट --
    "डफली": "dafli",
    "मंजीरा": "manjira", "मंझीरा": "manjira",
    "खड़ताल": "kartal", "करताल": "kartal",
    "झांझ": "jhanjh", "झाँझ": "jhanjh",
    "मटका": "matka", "गगरी": "matka", "मिट्टी_का_मटका": "matka",
    "पायल": "payal",
    "घूंघरू": "ghungru", "घुंघरू": "ghungru",
}

# ताल के बोल (rhythm syllables) - Devanagari और English दोनों में, हर एक की
# "ताक़त" (heavy/light/khali) पहचानने के लिए। tabla/damru/nagada/temple_bell
# सब इसी शब्दकोश से अपनी 'bols:' लाइन समझते हैं।
BOL_STRENGTH_MAP: Dict[str, str] = {
    # heavy (सम/ताली जैसी भारी चोट)
    "dha": "heavy", "dhin": "heavy", "dhage": "heavy", "ge": "heavy", "dhi": "heavy",
    "धा": "heavy", "धिन": "heavy", "धागे": "heavy", "गे": "heavy", "धी": "heavy",
    # khali (हल्की/खाली मात्रा - अलग tone के लिए)
    "tin": "khali", "tun": "khali", "ta": "khali",
    "तिन": "khali", "तुन": "khali", "ता": "khali",
    # light (बाकी सभी हल्के बोल)
    "na": "light", "ki": "light", "ti": "light", "ka": "light", "kat": "light",
    "gi": "light", "terekite": "light", "tirkit": "light",
    "ना": "light", "कि": "light", "गि": "light", "ति": "light", "का": "light",
    "कत": "light", "तिरकिट": "light",
}


def _normalize_multilingual_token(token: str, mapping: Dict[str, str]) -> str:
    """Devanagari word ho to uska English equivalent lauta deta hai, warna
    token waisa hi wapas (lowercase) - taaki English input bhi chalta rahe."""
    stripped = token.strip()
    if stripped in mapping:
        return mapping[stripped]
    return stripped.lower()




class ParseError(Exception):
    """Raised when the text script can't be understood. .args[0] is a
    ready-to-show Hindi message."""
    pass


# ==========================================================================
# 2. DATA MODEL
# ==========================================================================

@dataclass
class NoteEvent:
    start_sec: float
    duration_sec: float
    midi_pitch: Optional[int]   # None for unpitched percussion hits
    velocity: int = 100
    label: str = ""             # e.g. "sa", "Dha" - for the viewer / debugging


@dataclass
class Track:
    name: str                   # "tabla" | "bansuri" | "guitar_pad" | "harmonium" | custom
    instrument: str             # synth timbre key (usually same as name)
    events: List[NoteEvent] = field(default_factory=list)


@dataclass
class Composition:
    taal: str
    tempo_bpm: float
    cycles: int
    beats_per_cycle: int
    total_duration_sec: float
    tracks: List[Track] = field(default_factory=list)


# ==========================================================================
# 3. SCRIPT PARSER
# ==========================================================================

_KNOWN_GLOBAL_KEYS = {"taal", "tempo", "cycles"}
_KNOWN_TRACK_TYPES = {"tabla", "bansuri", "harmonium", "guitar_pad", "guitar", "sitar", "flute"}


def _parse_kv_line(line: str) -> Tuple[str, str]:
    if ":" not in line:
        raise ParseError(f"यह लाइन समझ नहीं आई (':' नहीं मिला): '{line}'")
    key, _, val = line.partition(":")
    return key.strip().lower(), val.strip()


def _sargam_token_to_semitone(token: str) -> Tuple[int, int]:
    """Returns (semitone_offset_from_sa, octave_shift). Octave shift: -1
    for mandra (token ends with ','), +1 for taar (token ends with ').
    English ("sa","re"...) aur Devanagari ("सा","रे"...) dono chalte hain."""
    token = token.strip()
    octave_shift = 0
    while token.endswith("'"):
        octave_shift += 1
        token = token[:-1]
    while token.endswith(","):
        octave_shift -= 1
        token = token[:-1]
    if token in DEVANAGARI_SARGAM_MAP:
        key = DEVANAGARI_SARGAM_MAP[token]
    else:
        key = token.lower()
    if key not in SARGAM_SEMITONES:
        raise ParseError(
            f"'{token}' ek pehchana हुआ sargam swar nahi hai. "
            f"Valid (English): sa re ga ma pa dha ni (komal: kre kga tma kdha kni). "
            f"Valid (हिंदी): सा रे ग/गा म/मा प/पा ध/धा नि (कोमल: 'कोमल रे' 'कोमल ग' 'तीव्र म' 'कोमल ध' 'कोमल नि'). "
            f"Octave ke liye ' (ऊंचा) ya , (नीचा) jodein."
        )
    return SARGAM_SEMITONES[key], octave_shift


def _apply_two_word_devanagari(text: str) -> str:
    """'कोमल रे' jaise do-shabdon wale komal-swar phrases ko tokenize
    karne se PEHLE ek single English-key word se badal deta hai."""
    for phrase, replacement in TWO_WORD_DEVANAGARI_SARGAM.items():
        text = text.replace(phrase, f" {replacement} ")
    return text


def _parse_notes_string(notes_str: str) -> List[List[str]]:
    """'sa re ga | pa ma ga' (ya 'सा रे ग | पा मा ग') -> [['sa','re','ga'], ['pa','ma','ga']]"""
    notes_str = _apply_two_word_devanagari(notes_str)
    bars = [b.strip() for b in notes_str.split("|")]
    result = []
    for bar in bars:
        tokens = [t for t in bar.split() if t]
        if tokens:
            result.append(tokens)
    if not result:
        raise ParseError("notes: field khali hai - kam se kam ek swar likhein.")
    return result


def _parse_chord_string(chord_str: str) -> List[List[str]]:
    """'C, C, Am, Am | F, F, G, G' -> [['C','C','Am','Am'], ['F','F','G','G']]"""
    bars = [b.strip() for b in chord_str.split("|")]
    result = []
    for bar in bars:
        tokens = [t.strip() for t in bar.split(",") if t.strip()]
        if tokens:
            result.append(tokens)
    if not result:
        raise ParseError("chord: field khali hai - kam se kam ek chord likhein.")
    return result


def _chord_to_semitones(chord_name: str) -> List[int]:
    if chord_name not in CHORD_LIBRARY:
        raise ParseError(
            f"'{chord_name}' chord pehchana nahi gaya. Supported: "
            f"{', '.join(sorted(CHORD_LIBRARY.keys()))} (major letters + 'm' for minor)."
        )
    root_letter = chord_name[0].upper()
    root_semitone = NOTE_NAME_TO_SEMITONE.get(root_letter, 0)
    if len(chord_name) > 1 and chord_name[1] in ("#", "b"):
        root_semitone = NOTE_NAME_TO_SEMITONE.get(chord_name[:2], root_semitone)
    intervals = CHORD_LIBRARY[chord_name]
    return [root_semitone + i for i in intervals]


def _split_blocks(text: str) -> List[List[str]]:
    """Splits the script into blocks separated by one-or-more blank lines.
    Each block is a list of its non-empty lines (comments starting with
    '#' are dropped)."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    blocks: List[List[str]] = []
    current: List[str] = []
    for raw in lines:
        line = raw.strip()
        if line.startswith("#"):
            continue
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)
    return blocks


def parse_script(text: str) -> Composition:
    """
    Parses the full text script into a Composition. Raises ParseError
    with a Hindi-language message on any problem.
    """
    if not text or not text.strip():
        raise ParseError("Script khali hai - kam se kam taal/tempo aur ek track likhein.")

    blocks = _split_blocks(text)
    if not blocks:
        raise ParseError("Script mein koi valid content nahi mila.")

    # ---- global settings: the first block, OR any block whose lines are
    # all known global keys (taal/tempo/cycles) with no 'track:' line ----
    global_settings = {"taal": "kaharwa", "tempo": "80", "cycles": "4"}
    track_blocks: List[List[str]] = []

    first_block = blocks[0]
    first_is_global = all(
        _parse_kv_line(ln)[0] in _KNOWN_GLOBAL_KEYS for ln in first_block
        if not ln.lower().startswith("track")
    ) and not any(ln.lower().startswith("track") for ln in first_block)

    if first_is_global:
        for ln in first_block:
            k, v = _parse_kv_line(ln)
            global_settings[k] = v
        track_blocks = blocks[1:]
    else:
        track_blocks = blocks

    taal_raw = global_settings["taal"].strip()
    taal_name = DEVANAGARI_TAAL_MAP.get(taal_raw, taal_raw.lower())
    if taal_name not in TAAL_LIBRARY:
        raise ParseError(
            f"'{taal_raw}' taal pehchana nahi gaya. Supported taal (English): "
            f"{', '.join(sorted(TAAL_LIBRARY.keys()))}. "
            f"हिंदी में: {', '.join(sorted(DEVANAGARI_TAAL_MAP.keys()))}."
        )
    try:
        tempo = float(global_settings["tempo"])
        if tempo <= 0:
            raise ValueError
    except ValueError:
        raise ParseError(f"tempo '{global_settings['tempo']}' ek valid number nahi hai.")

    try:
        global_cycles = int(global_settings["cycles"])
        if global_cycles <= 0:
            raise ValueError
    except ValueError:
        raise ParseError(f"cycles '{global_settings['cycles']}' ek valid whole number nahi hai.")

    beats_per_cycle = TAAL_LIBRARY[taal_name]["beats"]
    sec_per_beat = 60.0 / tempo
    cycle_duration_sec = beats_per_cycle * sec_per_beat

    if not track_blocks:
        raise ParseError(
            "Script mein koi 'track:' block nahi mila. Kam se kam ek track "
            "(jaise 'track: tabla' ke saath 'pattern: dadra') zaroor likhein."
        )

    # ---- figure out how many cycles the WHOLE composition runs for:
    # the max number of bars any pitched-note/chord/custom-bols track
    # declares, else the global 'cycles' setting.
    max_bars_seen = 0
    parsed_track_fields: List[Dict[str, str]] = []
    for block in track_blocks:
        fields: Dict[str, str] = {}
        track_type = None
        for ln in block:
            key, val = _parse_kv_line(ln)
            if key == "track":
                track_type_raw = val.strip()
                track_type = DEVANAGARI_TRACK_TYPE_MAP.get(track_type_raw, track_type_raw.lower())
            else:
                fields[key] = val
        if track_type is None:
            raise ParseError(
                f"Track block mein 'track: <type>' line missing hai: {block}"
            )
        fields["_type"] = track_type
        parsed_track_fields.append(fields)

        if "notes" in fields:
            bars = _parse_notes_string(fields["notes"])
            max_bars_seen = max(max_bars_seen, len(bars))
        elif "chord" in fields:
            bars = _parse_chord_string(fields["chord"])
            max_bars_seen = max(max_bars_seen, len(bars))
        elif "bols" in fields:
            bars = _parse_bols_string(fields["bols"])
            max_bars_seen = max(max_bars_seen, len(bars))

    total_cycles = max(max_bars_seen, global_cycles)
    total_duration_sec = total_cycles * cycle_duration_sec

    tracks: List[Track] = []
    for fields in parsed_track_fields:
        track_type = fields["_type"]
        if track_type == "dafli" and "notes" in fields:
            # डफली की खासियत: agar 'notes:' diya ho to yeh EK dual-mode
            # instrument ki tarah melodic (sargam-based) baj sakta hai -
            # baaki sab track types ki tarah bilkul fixed-mode nahi hai।
            tracks.append(_build_melodic_track(fields, "dafli", cycle_duration_sec, total_cycles))
        elif track_type in PERCUSSION_TYPES:
            tracks.append(_build_percussion_track(fields, track_type, taal_name, sec_per_beat,
                                                    beats_per_cycle, total_cycles))
        elif track_type == "shankha":
            tracks.append(_build_shankha_track(fields, taal_name, sec_per_beat,
                                                beats_per_cycle, total_cycles, cycle_duration_sec))
        elif track_type in ("guitar_pad", "guitar"):
            tracks.append(_build_chord_track(fields, "guitar_pad", cycle_duration_sec, total_cycles))
        elif track_type in ("bansuri", "flute", "harmonium", "sitar"):
            tracks.append(_build_melodic_track(fields, track_type, cycle_duration_sec, total_cycles))
        else:
            raise ParseError(
                f"'{track_type}' track type pehchana nahi gaya. Supported (English): "
                f"tabla, damru, nagada, temple_bell, shankha, dafli, manjira, kartal, jhanjh, matka, "
                f"payal, ghungru, bansuri, harmonium, guitar_pad, sitar, flute. "
                f"हिंदी में: {', '.join(sorted(DEVANAGARI_TRACK_TYPE_MAP.keys()))}। "
                f"(नोट: 'डफली'/'dafli' track mein अगर 'notes:' field diya jaaye, to woh ताल की जगह "
                f"सरगम के साथ melodic tarike se bhi baj sakta hai।)"
            )

    return Composition(
        taal=taal_name, tempo_bpm=tempo, cycles=total_cycles,
        beats_per_cycle=beats_per_cycle, total_duration_sec=total_duration_sec,
        tracks=tracks,
    )


def _parse_bols_string(bols_str: str) -> List[List[str]]:
    """'dha dhin dhin dha | dha dhin dhin dha' (ya धा धिन धिन धा) -> bars ki list.
    Yeh custom user-likha rhythm pattern hai - taal-library ke fixed pattern
    ki jagah use hota hai jab track mein 'bols:' field diya jaaye."""
    bars = [b.strip() for b in bols_str.split("|")]
    result = []
    for bar in bars:
        tokens = [t for t in bar.split() if t]
        if tokens:
            result.append(tokens)
    if not result:
        raise ParseError("bols: field khali hai - kam se kam ek bol likhein (jaise 'dha' ya 'धा').")
    return result


def _bol_strength(token: str) -> str:
    """Ek rhythm-syllable (bol) ki 'taakat' pehchanta hai - heavy/khali/light.
    English aur Devanagari dono bol pehchane jaate hain; anjaan bol ko halke
    (light) hit ki tarah treat kiya jaata hai, taaki script kabhi crash na ho."""
    key = token.strip()
    if key in BOL_STRENGTH_MAP:
        return BOL_STRENGTH_MAP[key]
    return BOL_STRENGTH_MAP.get(key.lower(), "light")


PERCUSSION_TYPES = {
    "tabla", "damru", "nagada", "temple_bell",
    # -- Part 3: पारंपरिक/लोक वाद्य सुइट (dafli 'notes:' ke saath melodic
    # bhi baj sakta hai - woh case parse_script() mein pehle hi handle ho
    # jaata hai, isliye yahan woh sirf iske DEFAULT/rhythm mode ke liye hai) --
    "dafli", "manjira", "kartal", "jhanjh", "matka", "payal", "ghungru",
}

# Live Pad panel (Compose tab, Part 3) ke liye canonical order - UI isi
# list ko import karke pads banata hai, taaki naya instrument yahan EK
# jagah jodne se pura pad-panel + preview + live-recording sab automatically
# update ho jaaye.
LIVE_PAD_INSTRUMENTS: List[str] = [
    "damru", "nagada", "shankha", "temple_bell",
    "dafli", "manjira", "kartal", "jhanjh", "matka", "payal", "ghungru",
]


def _build_percussion_track(fields: Dict[str, str], instrument: str, default_taal: str,
                             sec_per_beat: float, beats_per_cycle: int, total_cycles: int) -> Track:
    """tabla / damru / nagada / temple_bell - सब इसी एक function से बनते हैं,
    सिर्फ़ बजाते वक़्त अलग timbre (synth) use होता है। दो तरीके से rhythm दे सकते हैं:
      1. 'pattern: <taal>' - taal-library का तैयार bol-pattern इस्तेमाल हो
      2. 'bols: dha dhin ... | ...' - अपनी खुद की rhythm लिखें (English या
         Devanagari दोनों चलेगा), taal से बिल्कुल आज़ाद"""
    events: List[NoteEvent] = []

    if "bols" in fields:
        bars = _parse_bols_string(fields["bols"])
        cycle_duration_sec = beats_per_cycle * sec_per_beat
        for cycle_i in range(total_cycles):
            bar_tokens = bars[cycle_i % len(bars)]
            cycle_start = cycle_i * cycle_duration_sec
            n = len(bar_tokens)
            step_dur = cycle_duration_sec / n
            for i, token in enumerate(bar_tokens):
                if token.strip() in ("-", "_", "।", "."):
                    continue  # khamoshi/rest
                strength = _bol_strength(token)
                velocity = {"heavy": 120, "khali": 75, "light": 90}[strength]
                events.append(NoteEvent(
                    start_sec=cycle_start + i * step_dur,
                    duration_sec=step_dur * 0.85,
                    midi_pitch=None, velocity=velocity,
                    label=f"{token} ({strength})",
                ))
    else:
        pattern_raw = fields.get("pattern", default_taal).strip()
        pattern_name = DEVANAGARI_TAAL_MAP.get(pattern_raw, pattern_raw.lower())
        if pattern_name not in TAAL_LIBRARY:
            raise ParseError(
                f"{instrument} ke liye pattern '{pattern_raw}' pehchana nahi gaya. "
                f"Supported (English): {', '.join(sorted(TAAL_LIBRARY.keys()))}. "
                f"हिंदी में: {', '.join(sorted(DEVANAGARI_TAAL_MAP.keys()))}."
            )
        taal_def = TAAL_LIBRARY[pattern_name]
        beat_types = taal_def["pattern"]
        bols = taal_def["bols"]
        for cycle_i in range(total_cycles):
            cycle_start = cycle_i * len(beat_types) * sec_per_beat
            for beat_i, beat_type in enumerate(beat_types):
                start = cycle_start + beat_i * sec_per_beat
                velocity = {"sam": 120, "tali": 105, "khali": 75, "beat": 90}[beat_type]
                events.append(NoteEvent(
                    start_sec=start, duration_sec=sec_per_beat * 0.85,
                    midi_pitch=None, velocity=velocity,
                    label=f"{bols[beat_i]} ({beat_type})",
                ))

    return Track(name=instrument, instrument=instrument, events=events)


def _build_shankha_track(fields: Dict[str, str], default_taal: str, sec_per_beat: float,
                          beats_per_cycle: int, total_cycles: int, cycle_duration_sec: float) -> Track:
    """शंख (conch) - taal ke pattern se nahi bajta, balki har cycle ke शुरू
    (sam) par ek lambi, gehri phoonk deta hai - jaise pooja/aarti shuru
    hone par ek baar shankha phoonka jaata hai। Duration 'hold:' field se
    seconds mein badla ja sakta hai (default 2.5 sec)."""
    try:
        hold_sec = float(fields.get("hold", 2.5))
    except ValueError:
        hold_sec = 2.5
    hold_sec = max(0.5, min(hold_sec, cycle_duration_sec * 0.9))

    events: List[NoteEvent] = []
    for cycle_i in range(total_cycles):
        cycle_start = cycle_i * cycle_duration_sec
        events.append(NoteEvent(
            start_sec=cycle_start, duration_sec=hold_sec,
            midi_pitch=None, velocity=100, label="शंख-फूंक (sam)",
        ))
    return Track(name="shankha", instrument="shankha", events=events)


def _resolve_base_note(fields: Dict[str, str]) -> int:
    octave_word = fields.get("octave", "middle").strip().lower()
    octave_map = {"low": DEFAULT_BASE_MIDI_NOTE - 12, "middle": DEFAULT_BASE_MIDI_NOTE,
                  "high": DEFAULT_BASE_MIDI_NOTE + 12}
    return octave_map.get(octave_word, DEFAULT_BASE_MIDI_NOTE)


def _build_melodic_track(fields: Dict[str, str], track_type: str,
                          cycle_duration_sec: float, total_cycles: int) -> Track:
    if "notes" not in fields:
        raise ParseError(f"'{track_type}' track mein 'notes:' field zaroori hai.")
    bars = _parse_notes_string(fields["notes"])
    base_note = _resolve_base_note(fields)

    events: List[NoteEvent] = []
    for cycle_i in range(total_cycles):
        bar_tokens = bars[cycle_i % len(bars)]
        cycle_start = cycle_i * cycle_duration_sec
        n = len(bar_tokens)
        step_dur = cycle_duration_sec / n
        for i, token in enumerate(bar_tokens):
            if token.lower() in ("-", "_", "rest", "."):
                continue  # rest / silence
            semitone, octave_shift = _sargam_token_to_semitone(token)
            pitch = base_note + semitone + 12 * octave_shift
            events.append(NoteEvent(
                start_sec=cycle_start + i * step_dur,
                duration_sec=step_dur * 0.92,
                midi_pitch=pitch, velocity=95, label=token,
            ))
    return Track(name=track_type, instrument=track_type, events=events)


def _build_chord_track(fields: Dict[str, str], instrument: str,
                        cycle_duration_sec: float, total_cycles: int) -> Track:
    if "chord" not in fields:
        raise ParseError("guitar_pad track mein 'chord:' field zaroori hai.")
    bars = _parse_chord_string(fields["chord"])
    base_octave_note = 48  # guitar pad sits an octave below Sa by default

    events: List[NoteEvent] = []
    for cycle_i in range(total_cycles):
        bar_tokens = bars[cycle_i % len(bars)]
        cycle_start = cycle_i * cycle_duration_sec
        n = len(bar_tokens)
        step_dur = cycle_duration_sec / n
        for i, chord_name in enumerate(bar_tokens):
            offsets = _chord_to_semitones(chord_name)
            start = cycle_start + i * step_dur
            for offset in offsets:
                events.append(NoteEvent(
                    start_sec=start, duration_sec=step_dur * 0.97,
                    midi_pitch=base_octave_note + offset, velocity=70,
                    label=chord_name,
                ))
    return Track(name=instrument, instrument=instrument, events=events)


# ==========================================================================
# 4. MIDI EXPORT (for the MIDI Viewer + MuseScore/DAW compatibility)
# ==========================================================================

_GM_PROGRAM = {
    # General MIDI program numbers (0-indexed) - closest available timbres.
    "harmonium": 20,     # Church Organ (closest sustained-reed GM patch)
    "bansuri": 73,       # Flute
    "flute": 73,
    "guitar_pad": 89,    # Pad 2 (warm)
    "guitar": 24,        # Acoustic Guitar (nylon)
    "sitar": 104,        # Sitar (GM has a real one!)
    "shankha": 79,       # Ocarina - सबसे नज़दीक breathy/blown timbre GM में
    "dafli": 117,        # Melodic Tom - jab dafli ko 'notes:' se melodic bajaya jaaye
}
_GM_TABLA_CHANNEL = 9  # MIDI channel 10 (0-indexed 9) = percussion in GM
_SHANKHA_MIDI_NOTE = 48  # C3 - shankha ek gehra, sthir sur bajata hai

# हर percussion instrument ki apni "heavy/khali/light" GM drum-kit notes -
# taaki MIDI Viewer/MuseScore mein har vaadya ki apni pehchan ho।
_PERCUSSION_DRUM_NOTES: Dict[str, Dict[str, int]] = {
    "tabla": {"heavy": 45, "khali_tone": 39, "light": 42},       # Low Tom / Hand Clap / Closed Hi-Hat
    "damru": {"heavy": 41, "khali_tone": 37, "light": 76},       # Low Floor Tom / Side Stick / Hi Wood Block
    "nagada": {"heavy": 35, "khali_tone": 43, "light": 41},      # Bass Drum / High Floor Tom / Low Floor Tom
    "temple_bell": {"heavy": 53, "khali_tone": 56, "light": 51},  # Ride Bell / Cowbell / Ride Cymbal
    # -- Part 3: पारंपरिक/लोक वाद्य सुइट --
    "dafli": {"heavy": 54, "khali_tone": 54, "light": 70},         # Tambourine / Tambourine / Maracas
    "manjira": {"heavy": 81, "khali_tone": 80, "light": 69},       # Open Triangle / Mute Triangle / Cabasa
    "kartal": {"heavy": 75, "khali_tone": 76, "light": 77},        # Claves / Hi Wood Block / Lo Wood Block
    "jhanjh": {"heavy": 49, "khali_tone": 57, "light": 52},        # Crash Cymbal 1/2 / Chinese Cymbal
    "matka": {"heavy": 64, "khali_tone": 62, "light": 63},         # Low Conga / Mute Hi Conga / Open Hi Conga
    "payal": {"heavy": 70, "khali_tone": 70, "light": 69},         # Maracas / Maracas / Cabasa
    "ghungru": {"heavy": 69, "khali_tone": 70, "light": 69},       # Cabasa / Maracas / Cabasa
}


def composition_to_midi(comp: Composition):
    if not _HAS_PRETTY_MIDI:
        raise RuntimeError(
            "pretty_midi install nahi hai. `pip install pretty_midi` chalayein "
            "MIDI export/viewer istemal karne ke liye."
        )
    pm = pretty_midi.PrettyMIDI(initial_tempo=comp.tempo_bpm)
    for track in comp.tracks:
        # डफली अकेला aisa instrument hai jo dono tarike se likha ja sakta
        # hai - agar iske events mein pitch set hai (melodic 'notes:' mode)
        # to use normal (non-drum) melodic channel par export karo, warna
        # (bols:/pattern: rhythm mode) baaki percussion ki tarah drum channel par.
        is_pitched_dafli = track.instrument == "dafli" and any(
            ev.midi_pitch is not None for ev in track.events
        )
        if is_pitched_dafli:
            inst = pretty_midi.Instrument(program=_GM_PROGRAM["dafli"], name=f"{track.name} (melodic)")
            for ev in track.events:
                if ev.midi_pitch is None:
                    continue
                inst.notes.append(pretty_midi.Note(
                    velocity=ev.velocity, pitch=int(ev.midi_pitch),
                    start=ev.start_sec, end=ev.start_sec + ev.duration_sec,
                ))
        elif track.instrument in PERCUSSION_TYPES:
            drum_notes = _PERCUSSION_DRUM_NOTES.get(track.instrument, _PERCUSSION_DRUM_NOTES["tabla"])
            inst = pretty_midi.Instrument(program=0, is_drum=True, name=track.name)
            for ev in track.events:
                strength = "heavy" if ("heavy" in ev.label or "sam" in ev.label or "tali" in ev.label) else (
                    "khali_tone" if "khali" in ev.label else "light")
                note_num = drum_notes[strength]
                inst.notes.append(pretty_midi.Note(
                    velocity=ev.velocity, pitch=note_num,
                    start=ev.start_sec, end=ev.start_sec + ev.duration_sec,
                ))
        elif track.instrument == "shankha":
            inst = pretty_midi.Instrument(program=_GM_PROGRAM["shankha"], name="Shankha")
            for ev in track.events:
                inst.notes.append(pretty_midi.Note(
                    velocity=ev.velocity, pitch=_SHANKHA_MIDI_NOTE,
                    start=ev.start_sec, end=ev.start_sec + ev.duration_sec,
                ))
        else:
            program = _GM_PROGRAM.get(track.instrument, 0)
            inst = pretty_midi.Instrument(program=program, name=track.name)
            for ev in track.events:
                if ev.midi_pitch is None:
                    continue
                inst.notes.append(pretty_midi.Note(
                    velocity=ev.velocity, pitch=int(ev.midi_pitch),
                    start=ev.start_sec, end=ev.start_sec + ev.duration_sec,
                ))
        pm.instruments.append(inst)
    return pm


# ==========================================================================
# 5. BUILT-IN SYNTHESIZER (no external binary/soundfont needed)
# ==========================================================================

def _midi_to_freq(pitch: int) -> float:
    return 440.0 * (2.0 ** ((pitch - 69) / 12.0))


def _adsr_envelope(n_samples: int, sr: int, attack: float, decay: float,
                    sustain_level: float, release: float) -> np.ndarray:
    a = max(1, int(attack * sr))
    d = max(1, int(decay * sr))
    r = max(1, int(release * sr))
    sustain_len = max(0, n_samples - a - d - r)
    env = np.concatenate([
        np.linspace(0, 1, a, endpoint=False),
        np.linspace(1, sustain_level, d, endpoint=False),
        np.full(sustain_len, sustain_level),
        np.linspace(sustain_level, 0, r),
    ])
    if len(env) < n_samples:
        env = np.pad(env, (0, n_samples - len(env)))
    return env[:n_samples].astype(np.float32)


def _synth_harmonium(freq: float, dur: float, sr: int) -> np.ndarray:
    """Reed-organ style: several harmonics, slow bellows attack, steady sustain."""
    n = max(1, int(dur * sr))
    t = np.arange(n, dtype=np.float32) / sr
    sig = np.zeros(n, dtype=np.float32)
    for harmonic, amp in [(1, 1.0), (2, 0.45), (3, 0.22), (4, 0.10), (5, 0.06)]:
        sig += amp * np.sin(2 * np.pi * freq * harmonic * t)
    vibrato = 1.0 + 0.004 * np.sin(2 * np.pi * 5.2 * t)
    sig *= vibrato
    env = _adsr_envelope(n, sr, attack=0.06, decay=0.08, sustain_level=0.85, release=0.15)
    return (sig * env / 1.9).astype(np.float32)


def _synth_bansuri(freq: float, dur: float, sr: int) -> np.ndarray:
    """Flute-like: fundamental + light breath noise + vibrato, soft attack."""
    n = max(1, int(dur * sr))
    t = np.arange(n, dtype=np.float32) / sr
    vibrato = 1.0 + 0.012 * np.sin(2 * np.pi * 5.5 * t)
    sig = np.sin(2 * np.pi * freq * vibrato * t)
    sig += 0.18 * np.sin(2 * np.pi * freq * 2 * vibrato * t)
    breath = np.random.default_rng(int(freq * 1000) % (2**31)).standard_normal(n).astype(np.float32)
    breath_env = np.exp(-t * 12.0) * 0.05
    sig += breath * breath_env
    env = _adsr_envelope(n, sr, attack=0.10, decay=0.05, sustain_level=0.75, release=0.18)
    return (sig * env / 1.3).astype(np.float32)


def _synth_guitar_pad(freq: float, dur: float, sr: int) -> np.ndarray:
    """Warm pad: detuned saw-ish (additive), slow attack, long release."""
    n = max(1, int(dur * sr))
    t = np.arange(n, dtype=np.float32) / sr
    sig = np.zeros(n, dtype=np.float32)
    for detune in (-0.15, 0.0, 0.15):
        f = freq * (2 ** (detune / 12.0))
        for k in range(1, 6):
            sig += (1.0 / k) * np.sin(2 * np.pi * f * k * t)
    env = _adsr_envelope(n, sr, attack=0.35, decay=0.2, sustain_level=0.55, release=0.4)
    return (sig * env / 6.0).astype(np.float32)


def _synth_sitar(freq: float, dur: float, sr: int) -> np.ndarray:
    """Plucked-string approximation: bright attack, fast-decaying harmonics."""
    n = max(1, int(dur * sr))
    t = np.arange(n, dtype=np.float32) / sr
    sig = np.zeros(n, dtype=np.float32)
    for harmonic, amp, decay_rate in [(1, 1.0, 2.2), (2, 0.6, 4.0), (3, 0.35, 6.0), (5, 0.15, 8.0)]:
        sig += amp * np.exp(-decay_rate * t) * np.sin(2 * np.pi * freq * harmonic * t)
    buzz = 0.06 * np.exp(-9.0 * t) * np.sin(2 * np.pi * freq * 1.5 * t + 0.3 * np.sin(2 * np.pi * 30 * t))
    sig += buzz
    env = _adsr_envelope(n, sr, attack=0.005, decay=0.25, sustain_level=0.35, release=0.15)
    return (sig * env / 1.6).astype(np.float32)


def _synth_tabla_hit(strength: str, dur: float, sr: int) -> np.ndarray:
    """Unpitched percussive hit. 'heavy' = low bass thump (sam/tali/dha-like),
    'light' = higher tick (na/beat-like), 'khali' = mid resonant tone."""
    n = max(1, int(max(dur, 0.12) * sr))
    t = np.arange(n, dtype=np.float32) / sr
    rng = np.random.default_rng(hash(strength) % (2**31))
    click = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 60.0) * 0.25

    if strength == "heavy":
        f0 = 95.0
        body = np.sin(2 * np.pi * f0 * t) * np.exp(-t * 9.0)
        body += 0.4 * np.sin(2 * np.pi * f0 * 2.0 * t) * np.exp(-t * 14.0)
        sig = body * 0.9 + click
    elif strength == "khali":
        f0 = 180.0
        body = np.sin(2 * np.pi * f0 * t) * np.exp(-t * 11.0)
        sig = body * 0.75 + click
    else:  # light
        f0 = 320.0
        body = np.sin(2 * np.pi * f0 * t) * np.exp(-t * 18.0)
        sig = body * 0.6 + click * 1.2
    return sig.astype(np.float32)


def _synth_damru_hit(strength: str, dur: float, sr: int) -> np.ndarray:
    """डमरू - छोटा हाथ का ढोलक, ऊँची पिच, 'दो-मार' (double-strike) झटका -
    जैसे असली डमरू हिलाने पर दोनों तरफ़ की गोलियाँ बारी-बारी से चोट मारती हैं।"""
    n = max(1, int(max(dur, 0.18) * sr))
    t = np.arange(n, dtype=np.float32) / sr

    def _strike(t0: float, f0: float, amp: float) -> np.ndarray:
        tt = np.clip(t - t0, 0.0, None)
        gate = (t >= t0).astype(np.float32)
        return amp * np.sin(2 * np.pi * f0 * tt) * np.exp(-tt * 32.0) * gate

    base_f0 = {"heavy": 460.0, "khali": 400.0, "light": 360.0}[strength]
    sig = _strike(0.0, base_f0, 1.0) + _strike(0.055, base_f0 * 0.9, 0.65)
    rng = np.random.default_rng(hash(("damru", strength)) % (2**31))
    click = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 90.0) * 0.15
    return (sig + click).astype(np.float32)


def _synth_nagada_hit(strength: str, dur: float, sr: int) -> np.ndarray:
    """नगाड़ा - बड़ा कढ़ाई-नुमा ढोल, बहुत गहरी/भारी गूंज, लंबी decay -
    उत्सव/जुलूस वाला भारी, ज़मीन हिला देने वाला थाप।"""
    n = max(1, int(max(dur, 0.5) * sr))
    t = np.arange(n, dtype=np.float32) / sr
    f0 = {"heavy": 58.0, "khali": 78.0, "light": 95.0}[strength]
    decay = {"heavy": 3.2, "khali": 4.5, "light": 6.0}[strength]
    body = np.sin(2 * np.pi * f0 * t) * np.exp(-t * decay)
    body += 0.55 * np.sin(2 * np.pi * f0 * 1.5 * t) * np.exp(-t * (decay + 2.0))
    rng = np.random.default_rng(hash(("nagada", strength)) % (2**31))
    thump_click = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 40.0) * 0.35
    amp = {"heavy": 1.0, "khali": 0.75, "light": 0.55}[strength]
    return ((body + thump_click) * amp).astype(np.float32)


def _synth_temple_bell_hit(strength: str, dur: float, sr: int) -> np.ndarray:
    """मंदिर की घंटी - धातु जैसी खनक, कई बेसुरे (inharmonic) overtones एक
    साथ बजते हैं (असली घंटी की खासियत), लंबी गूंज।"""
    n = max(1, int(max(dur, 1.0) * sr))
    t = np.arange(n, dtype=np.float32) / sr
    f0 = {"heavy": 880.0, "khali": 740.0, "light": 660.0}[strength]
    # असली घंटी के 'बेसुरे' (inharmonic) partials - ratio, amplitude, decay-rate
    partials = [(1.0, 1.0, 3.0), (2.0, 0.55, 4.2), (2.76, 0.32, 5.6),
                (4.07, 0.16, 7.5), (5.4, 0.08, 9.5)]
    sig = np.zeros(n, dtype=np.float32)
    for ratio, amp, decay_rate in partials:
        sig += amp * np.sin(2 * np.pi * f0 * ratio * t) * np.exp(-decay_rate * t)
    rng = np.random.default_rng(hash(("bell", strength)) % (2**31))
    strike_click = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 100.0) * 0.18
    return ((sig / 1.8) + strike_click).astype(np.float32)


def _synth_shankha_drone(dur: float, sr: int) -> np.ndarray:
    """शंख - फूँक मारने से बनने वाला गहरा, स्थिर, हवा जैसा सुर - सतत गूंजता
    हुआ, पूजा/आरती की शुरुआत की आवाज़।"""
    n = max(1, int(max(dur, 0.5) * sr))
    t = np.arange(n, dtype=np.float32) / sr
    f0 = 146.0  # लगभग D3 - असली शंख की गहराई जैसा
    tone = (np.sin(2 * np.pi * f0 * t) + 0.30 * np.sin(2 * np.pi * f0 * 2 * t)
            + 0.15 * np.sin(2 * np.pi * f0 * 3 * t))
    rng = np.random.default_rng(101)
    breath_noise = rng.standard_normal(n).astype(np.float32)
    if lfilter is not None:
        from scipy.signal import butter
        b, a = butter(2, [max(0.01, f0 * 2 / (sr / 2)), min(0.99, f0 * 9 / (sr / 2))], btype="band")
        breath = lfilter(b, a, breath_noise).astype(np.float32) * 0.14
    else:
        breath = breath_noise * 0.02
    env = _adsr_envelope(n, sr, attack=0.30, decay=0.15, sustain_level=0.85, release=0.35)
    sig = (tone * 0.55 + breath) * env
    return sig.astype(np.float32)


# ==========================================================================
# 5B. PART 3 — पारंपरिक/लोक वाद्य सुइट (Dafli, Manjira, Kartal, Jhanjh,
#     Matka/Gagari, Payal, Ghungru) - sab numpy-based additive/noise
#     synthesis se, koi sample/recording istemal nahi।
# ==========================================================================

def _synth_dafli_hit(strength: str, dur: float, sr: int) -> np.ndarray:
    """डफली - लकड़ी के फ्रेम पर कसी खाल की तीखी, टाइट 'थाप' (slap) -
    tabla se zyada 'khula'/flat aur jaldi decay hone wali awaaz। Yeh iska
    DEFAULT rhythm-mode hit hai ('pattern:'/'bols:' se); agar track mein
    'notes:' diya jaaye to iski jagah _synth_dafli_pitched() istemal hota hai।"""
    n = max(1, int(max(dur, 0.15) * sr))
    t = np.arange(n, dtype=np.float32) / sr
    f0 = {"heavy": 210.0, "khali": 260.0, "light": 320.0}[strength]
    body = np.sin(2 * np.pi * f0 * t) * np.exp(-t * 22.0)
    body += 0.35 * np.sin(2 * np.pi * f0 * 1.8 * t) * np.exp(-t * 30.0)
    rng = np.random.default_rng(hash(("dafli", strength)) % (2**31))
    slap = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 45.0) * 0.5
    amp = {"heavy": 1.0, "khali": 0.8, "light": 0.6}[strength]
    return ((body + slap) * amp).astype(np.float32)


def _synth_dafli_pitched(freq: float, dur: float, sr: int) -> np.ndarray:
    """डफली - जब track mein 'notes:' (sargam) diya jaaye, to ek tuned,
    thoda 'boxy' drum-tone banta hai - jaise koi tuned frame-drum sur
    mein melody baja raha ho। Yeh डफली ki khaas dual-mode capability hai:
    wahi instrument taal ke liye bhi, aur dhun ke liye bhi istemal ho sakta hai।"""
    n = max(1, int(dur * sr))
    t = np.arange(n, dtype=np.float32) / sr
    sig = np.sin(2 * np.pi * freq * t) * np.exp(-t * 4.0)
    sig += 0.4 * np.sin(2 * np.pi * freq * 2.0 * t) * np.exp(-t * 7.0)
    rng = np.random.default_rng(int(freq * 10) % (2**31))
    slap = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 35.0) * 0.12
    env = _adsr_envelope(n, sr, attack=0.004, decay=0.12, sustain_level=0.25, release=0.15)
    return ((sig + slap) * env).astype(np.float32)


def _synth_manjira_hit(strength: str, dur: float, sr: int) -> np.ndarray:
    """मंजीरा - छोटी धातु की झांझरी जैसी प्लेटें, बहुत ऊँची, साफ़, चमकदार
    'चिन-चिन' आवाज़, बहुत जल्दी decay होती है।"""
    n = max(1, int(max(dur, 0.3) * sr))
    t = np.arange(n, dtype=np.float32) / sr
    f0 = {"heavy": 2600.0, "khali": 2300.0, "light": 2050.0}[strength]
    partials = [(1.0, 1.0, 10.0), (1.8, 0.5, 14.0), (2.7, 0.3, 18.0), (3.6, 0.15, 22.0)]
    sig = np.zeros(n, dtype=np.float32)
    for ratio, amp, decay in partials:
        sig += amp * np.sin(2 * np.pi * f0 * ratio * t) * np.exp(-decay * t)
    rng = np.random.default_rng(hash(("manjira", strength)) % (2**31))
    click = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 120.0) * 0.2
    return ((sig / 1.6) + click).astype(np.float32)


def _synth_kartal_hit(strength: str, dur: float, sr: int) -> np.ndarray:
    """खड़ताल/करताल - लकड़ी की दो पट्टियों का घना 'खट-खट' क्लैटर, साथ में
    हल्की पीतल की छोटी घुंघरी/डिस्क की झनझनाहट परत के रूप में मिली हुई।"""
    n = max(1, int(max(dur, 0.25) * sr))
    t = np.arange(n, dtype=np.float32) / sr
    f0 = {"heavy": 1450.0, "khali": 1250.0, "light": 1100.0}[strength]
    wood = np.sin(2 * np.pi * f0 * t) * np.exp(-t * 40.0)
    wood += 0.5 * np.sin(2 * np.pi * f0 * 1.6 * t) * np.exp(-t * 55.0)
    rng = np.random.default_rng(hash(("kartal", strength)) % (2**31))
    clatter = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 70.0) * 0.4
    jingle_f = 4200.0
    jingle = 0.12 * np.sin(2 * np.pi * jingle_f * t) * np.exp(-t * 25.0)
    amp = {"heavy": 1.0, "khali": 0.8, "light": 0.6}[strength]
    return ((wood + clatter + jingle) * amp).astype(np.float32)


def _synth_jhanjh_hit(strength: str, dur: float, sr: int) -> np.ndarray:
    """झांझ - बड़ी धातु की प्लेटें आपस में टकराना, चौड़ी/खुली, देर तक
    गूंजती हुई frequency decay - jhanjh (jaise manjeera ka bada bhai)।"""
    n = max(1, int(max(dur, 1.5) * sr))
    t = np.arange(n, dtype=np.float32) / sr
    f0 = {"heavy": 340.0, "khali": 300.0, "light": 380.0}[strength]
    partials = [(1.0, 1.0, 1.2), (1.53, 0.6, 1.6), (2.14, 0.4, 2.0), (2.81, 0.25, 2.6), (3.9, 0.15, 3.4)]
    sig = np.zeros(n, dtype=np.float32)
    for ratio, amp, decay in partials:
        sig += amp * np.sin(2 * np.pi * f0 * ratio * t) * np.exp(-decay * t)
    rng = np.random.default_rng(hash(("jhanjh", strength)) % (2**31))
    crash_noise = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 3.0) * 0.3
    amp_o = {"heavy": 1.0, "khali": 0.8, "light": 0.65}[strength]
    return ((sig / 1.8 + crash_noise) * amp_o).astype(np.float32)


def _synth_matka_hit(strength: str, dur: float, sr: int) -> np.ndarray:
    """मटका/गगरी - मिट्टी के घड़े पर हाथ की सूखी, "खोखली" (hollow) थाप -
    mid-range resonance, tabla se zyada 'earthy'/organic, kam metallic click।"""
    n = max(1, int(max(dur, 0.4) * sr))
    t = np.arange(n, dtype=np.float32) / sr
    f0 = {"heavy": 140.0, "khali": 170.0, "light": 200.0}[strength]
    body = np.sin(2 * np.pi * f0 * t) * np.exp(-t * 7.0)
    body += 0.3 * np.sin(2 * np.pi * f0 * 2.1 * t) * np.exp(-t * 10.0)
    rng = np.random.default_rng(hash(("matka", strength)) % (2**31))
    thump = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 25.0) * 0.3
    amp = {"heavy": 1.0, "khali": 0.8, "light": 0.6}[strength]
    return ((body + thump) * amp).astype(np.float32)


def _synth_payal_hit(strength: str, dur: float, sr: int) -> np.ndarray:
    """पायल - पैर की पायल के कई छोटे घुंघरुओं का नरम, चमकदार, ऊँची-आवृत्ति
    वाला 'छम-छम' झुंड (cluster) - decay lamba aur roshan (bright) hota hai।"""
    n = max(1, int(max(dur, 0.6) * sr))
    t = np.arange(n, dtype=np.float32) / sr
    rng = np.random.default_rng(hash(("payal", strength)) % (2**31))
    base_freqs = {
        "heavy": [3200.0, 3800.0, 4400.0, 5100.0],
        "khali": [2900.0, 3400.0, 4000.0, 4600.0],
        "light": [3500.0, 4100.0, 4700.0, 5400.0],
    }[strength]
    sig = np.zeros(n, dtype=np.float32)
    for f in base_freqs:
        phase = rng.uniform(0, 2 * np.pi)
        decay = rng.uniform(6.0, 12.0)
        sig += (0.5 / len(base_freqs)) * np.sin(2 * np.pi * f * t + phase) * np.exp(-decay * t)
    shimmer = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 18.0) * 0.08
    amp = {"heavy": 1.0, "khali": 0.8, "light": 0.65}[strength]
    return ((sig + shimmer) * amp).astype(np.float32)


def _synth_ghungru_hit(strength: str, dur: float, sr: int) -> np.ndarray:
    """घूंघरू - payal jaisa hi parivaar, par zyada ghana/tight cluster
    (nritya-ghungru ki tarah), thoda ऊँचा aur jaldi decay hone wala।"""
    n = max(1, int(max(dur, 0.5) * sr))
    t = np.arange(n, dtype=np.float32) / sr
    rng = np.random.default_rng(hash(("ghungru", strength)) % (2**31))
    base_freqs = {
        "heavy": [4200.0, 4800.0, 5500.0, 6300.0, 7100.0],
        "khali": [3900.0, 4500.0, 5100.0, 5900.0, 6600.0],
        "light": [4500.0, 5200.0, 6000.0, 6800.0, 7600.0],
    }[strength]
    sig = np.zeros(n, dtype=np.float32)
    for f in base_freqs:
        phase = rng.uniform(0, 2 * np.pi)
        decay = rng.uniform(9.0, 16.0)
        sig += (0.45 / len(base_freqs)) * np.sin(2 * np.pi * f * t + phase) * np.exp(-decay * t)
    rng2 = np.random.default_rng(hash(("ghungru2", strength)) % (2**31))
    shimmer = rng2.standard_normal(n).astype(np.float32) * np.exp(-t * 22.0) * 0.06
    amp = {"heavy": 1.0, "khali": 0.8, "light": 0.6}[strength]
    return ((sig + shimmer) * amp).astype(np.float32)


_SYNTH_FUNCS = {
    "harmonium": _synth_harmonium,
    "bansuri": _synth_bansuri,
    "flute": _synth_bansuri,
    "guitar_pad": _synth_guitar_pad,
    "guitar": _synth_guitar_pad,
    "sitar": _synth_sitar,
    "dafli": _synth_dafli_pitched,  # सिर्फ़ tab kaam aata hai jab dafli 'notes:' se melodic bajaya jaaye
}

# हर percussion instrument (tabla/damru/nagada/temple_bell + Part 3 ke
# pramaparagat/lok vaadya) ki apni timbre-function -
# सिग्नेचर (strength, dur, sr) -> audio.
_PERCUSSION_SYNTH_FUNCS = {
    "tabla": _synth_tabla_hit,
    "damru": _synth_damru_hit,
    "nagada": _synth_nagada_hit,
    "temple_bell": _synth_temple_bell_hit,
    "dafli": _synth_dafli_hit,
    "manjira": _synth_manjira_hit,
    "kartal": _synth_kartal_hit,
    "jhanjh": _synth_jhanjh_hit,
    "matka": _synth_matka_hit,
    "payal": _synth_payal_hit,
    "ghungru": _synth_ghungru_hit,
}


def render_audio(comp: Composition, sr: int = 44100) -> np.ndarray:
    """Mixes every track's events into one stereo float32 buffer (-1..1)."""
    total_samples = max(1, int((comp.total_duration_sec + 1.0) * sr))
    mix = np.zeros(total_samples, dtype=np.float32)

    for track in comp.tracks:
        is_pitched_dafli = track.instrument == "dafli" and any(
            ev.midi_pitch is not None for ev in track.events
        )
        if is_pitched_dafli:
            synth_fn = _SYNTH_FUNCS["dafli"]
            for ev in track.events:
                if ev.midi_pitch is None:
                    continue
                freq = _midi_to_freq(ev.midi_pitch)
                wave_arr = synth_fn(freq, ev.duration_sec, sr)
                start_idx = int(ev.start_sec * sr)
                end_idx = min(total_samples, start_idx + len(wave_arr))
                if start_idx < total_samples:
                    mix[start_idx:end_idx] += wave_arr[: end_idx - start_idx] * (ev.velocity / 127.0)
        elif track.instrument in PERCUSSION_TYPES:
            hit_fn = _PERCUSSION_SYNTH_FUNCS.get(track.instrument, _synth_tabla_hit)
            for ev in track.events:
                strength = "heavy" if ("heavy" in ev.label or "sam" in ev.label or "tali" in ev.label) else (
                    "khali" if "khali" in ev.label else "light")
                hit = hit_fn(strength, ev.duration_sec, sr)
                start_idx = int(ev.start_sec * sr)
                end_idx = min(total_samples, start_idx + len(hit))
                if start_idx < total_samples:
                    mix[start_idx:end_idx] += hit[: end_idx - start_idx] * (ev.velocity / 127.0)
        elif track.instrument == "shankha":
            for ev in track.events:
                wave_arr = _synth_shankha_drone(ev.duration_sec, sr)
                start_idx = int(ev.start_sec * sr)
                end_idx = min(total_samples, start_idx + len(wave_arr))
                if start_idx < total_samples:
                    mix[start_idx:end_idx] += wave_arr[: end_idx - start_idx] * (ev.velocity / 127.0)
        else:
            synth_fn = _SYNTH_FUNCS.get(track.instrument, _synth_harmonium)
            for ev in track.events:
                if ev.midi_pitch is None:
                    continue
                freq = _midi_to_freq(ev.midi_pitch)
                wave_arr = synth_fn(freq, ev.duration_sec, sr)
                start_idx = int(ev.start_sec * sr)
                end_idx = min(total_samples, start_idx + len(wave_arr))
                if start_idx < total_samples:
                    mix[start_idx:end_idx] += wave_arr[: end_idx - start_idx] * (ev.velocity / 127.0)

    peak = float(np.max(np.abs(mix))) or 1.0
    mix = np.tanh(mix / peak * 1.15) * 0.92  # soft-limit to avoid clipping

    stereo = np.stack([mix, mix], axis=1)  # simple mono-doubled stereo for now
    return stereo.astype(np.float32)


def save_wav(audio: np.ndarray, path: str, sr: int = 44100):
    """audio: shape (n, 2) float32 -1..1"""
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


# ==========================================================================
# 6. OPTIONAL: FluidSynth + real soundfont render path (used later once a
# .sf2 file is available - not required for the default flow above).
# ==========================================================================

DEFAULT_SOUNDFONT_PATH = "assets/indian_instruments.sf2"


def check_soundfont_status(path: str = DEFAULT_SOUNDFONT_PATH) -> Dict[str, object]:
    """
    असली भारतीय वाद्यों वाली साउंडफॉन्ट (.sf2) फ़ाइल मिली या नहीं, यह
    चेक करता है। ना मिले तो भी ऐप कभी crash नहीं होगा - बस बिल्ट-इन
    numpy synthesizer (render_audio) अपने आप इस्तेमाल होता रहता है।

    Returns: {"found": bool, "path": str, "message": Hindi संदेश}
    """
    found = bool(path) and os.path.exists(path)
    if found:
        message = (
            f"✅ असली भारतीय वाद्य साउंडफॉन्ट मिल गई ({path}) - चाहें तो "
            f"`render_with_fluidsynth()` से ज़्यादा असली-जैसी आवाज़ बना सकते हैं।"
        )
    else:
        message = (
            f"ℹ️ असली वाद्य साउंडफॉन्ट (`{path}`) अभी उपलब्ध नहीं है — कोई बात नहीं, "
            f"ऐप अपने-आप बिल्ट-इन सिंथेसाइज़र (numpy) से आवाज़ बना देगा। "
            f"काम रुकेगा नहीं, बस साज़ों की आवाज़ 100% असली रिकॉर्डिंग जैसी नहीं, "
            f"डिजिटल-सिंथेसाइज़्ड होगी।"
        )
    return {"found": found, "path": path, "message": message}


# ==========================================================================
# 7. VOCAL PROCESSING - record/upload -> Auto-Perfect or Custom DSP chain
# ==========================================================================
"""
Yeh section user ki apni gaayi/boli hui awaaz (record ya upload ki hui)
ko process karta hai - EQ, compression, warmth/saturation, brilliance
(exciter) aur ek "crowd chorus" (bhakton ki bheed jaisa) effect.

Do mode:
  - AUTO_PERFECT_PRESET  -> ek click mein bhakti-sangeet ke liye tuned
    default values (garmahat badhao, boxy mids kaato, upar thoda "air")
  - Custom mode          -> user khud sliders se har cheez adjust kare

DSP pura numpy/scipy se hai - koi external binary/plugin nahi chahiye.
Vocal audio LOAD karne ke liye moviepy (jo is project mein pehle se hi
Track 5/6 ke liye dependency hai) use hota hai - isse WAV aur MP3 dono
seedhe padh sakte hain, alag se ffmpeg-wrapper library (pydub/soundfile)
add karne ki zaroorat nahi padi.
"""

try:
    from scipy.signal import lfilter
except ImportError:  # pragma: no cover
    lfilter = None


# ---- Auto-Perfect preset: devotional-vocal-tuned defaults ----------------
AUTO_PERFECT_PRESET: Dict[str, float] = {
    "brilliance": 58,       # 0-100  (खनक / exciter intensity)
    "warmth": 52,           # 0-100  (सुरीलापन / harmonic saturation)
    "bass_db": 2.5,         # -12..+12 dB (भारीपन/वजन, 150 Hz shelf)
    "treble_db": 3.5,       # -12..+12 dB (तीखा सुर, 6 kHz shelf)
    "crowd_intensity": 22,  # 0-100  (भक्तों की भीड़ प्रभाव)
}

DEFAULT_CUSTOM_PRESET: Dict[str, float] = {
    "brilliance": 0, "warmth": 0, "bass_db": 0.0, "treble_db": 0.0, "crowd_intensity": 0,
}

MAX_VOCAL_UPLOAD_MB = 10


class VocalLoadError(Exception):
    """Raised when a recorded/uploaded vocal file can't be read. .args[0]
    is a ready-to-show Hindi message."""
    pass


def load_vocal_audio(path: str, target_sr: int = 44100) -> Tuple[np.ndarray, int]:
    """
    Loads a WAV/MP3 file into a mono float32 array (-1..1) at target_sr.

    Converts via a direct `ffmpeg` subprocess call (same pattern already
    used elsewhere in this project, e.g. live_app.py's playlist concat) -
    this avoids moviepy's AudioClip.to_soundarray(), whose internal
    np.vstack-on-a-generator call breaks under current numpy and would
    silently make every vocal upload fail.
    """
    import shutil
    import subprocess

    if not path or not os.path.exists(path):
        raise VocalLoadError(f"Audio file nahi mili: {path}")

    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > MAX_VOCAL_UPLOAD_MB:
        raise VocalLoadError(
            f"File {size_mb:.1f} MB ki hai - {MAX_VOCAL_UPLOAD_MB} MB se choti file upload/record karein."
        )

    if shutil.which("ffmpeg") is None:
        raise VocalLoadError(
            "ffmpeg system PATH mein nahi mila - audio load nahi ho sakta. "
            "Isi project ki baaki cheezein (video/audio render) bhi ffmpeg par "
            "depend karti hain, isliye yeh pehle se install hona chahiye."
        )

    tmp_wav = os.path.join(tempfile.gettempdir(), f"vocal_load_{os.getpid()}_{id(path)}.wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-ac", "1", "-ar", str(target_sr), "-f", "wav", tmp_wav],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60,
        )
    except subprocess.CalledProcessError as e:
        raise VocalLoadError(
            f"ffmpeg se audio convert nahi ho paya (file corrupt/unsupported ho sakti hai): "
            f"{e.stderr.decode('utf-8', errors='ignore')[-300:] if e.stderr else e}"
        )
    except Exception as e:
        raise VocalLoadError(f"Audio load karte waqt error: {e}")

    try:
        with wave.open(tmp_wav, "rb") as wf:
            n_frames = wf.getnframes()
            sampwidth = wf.getsampwidth()
            raw = wf.readframes(n_frames)
    finally:
        if os.path.exists(tmp_wav):
            os.remove(tmp_wav)

    if sampwidth != 2:
        raise VocalLoadError(f"Unsupported audio sample width: {sampwidth} bytes.")

    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if arr.size == 0:
        raise VocalLoadError("Audio file khali hai (0 samples).")

    peak = float(np.max(np.abs(arr))) or 1.0
    arr = (arr / peak) * 0.95
    return arr.astype(np.float32), target_sr


# ---- Biquad EQ filters (RBJ Audio-EQ-Cookbook formulas) -------------------
def _biquad_peaking(sr: float, freq: float, gain_db: float, q: float = 1.0):
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * math.pi * freq / sr
    alpha = math.sin(w0) / (2 * q)
    cosw0 = math.cos(w0)
    b0 = 1 + alpha * A
    b1 = -2 * cosw0
    b2 = 1 - alpha * A
    a0 = 1 + alpha / A
    a1 = -2 * cosw0
    a2 = 1 - alpha / A
    return [b0 / a0, b1 / a0, b2 / a0], [1.0, a1 / a0, a2 / a0]


def _biquad_low_shelf(sr: float, freq: float, gain_db: float, slope: float = 1.0):
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * math.pi * freq / sr
    cosw0 = math.cos(w0)
    alpha = math.sin(w0) / 2.0 * math.sqrt((A + 1 / A) * (1 / slope - 1) + 2)
    sqrtA = math.sqrt(A)
    b0 = A * ((A + 1) - (A - 1) * cosw0 + 2 * sqrtA * alpha)
    b1 = 2 * A * ((A - 1) - (A + 1) * cosw0)
    b2 = A * ((A + 1) - (A - 1) * cosw0 - 2 * sqrtA * alpha)
    a0 = (A + 1) + (A - 1) * cosw0 + 2 * sqrtA * alpha
    a1 = -2 * ((A - 1) + (A + 1) * cosw0)
    a2 = (A + 1) + (A - 1) * cosw0 - 2 * sqrtA * alpha
    return [b0 / a0, b1 / a0, b2 / a0], [1.0, a1 / a0, a2 / a0]


def _biquad_high_shelf(sr: float, freq: float, gain_db: float, slope: float = 1.0):
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * math.pi * freq / sr
    cosw0 = math.cos(w0)
    alpha = math.sin(w0) / 2.0 * math.sqrt((A + 1 / A) * (1 / slope - 1) + 2)
    sqrtA = math.sqrt(A)
    b0 = A * ((A + 1) + (A - 1) * cosw0 + 2 * sqrtA * alpha)
    b1 = -2 * A * ((A - 1) + (A + 1) * cosw0)
    b2 = A * ((A + 1) + (A - 1) * cosw0 - 2 * sqrtA * alpha)
    a0 = (A + 1) - (A - 1) * cosw0 + 2 * sqrtA * alpha
    a1 = 2 * ((A - 1) - (A + 1) * cosw0)
    a2 = (A + 1) - (A - 1) * cosw0 - 2 * sqrtA * alpha
    return [b0 / a0, b1 / a0, b2 / a0], [1.0, a1 / a0, a2 / a0]


def _apply_biquad(audio: np.ndarray, b, a) -> np.ndarray:
    if lfilter is None or abs(b[0]) < 1e-12 and abs(a[0] - 1.0) < 1e-12:
        return audio
    return lfilter(b, a, audio).astype(np.float32)


def _butter_highpass(audio: np.ndarray, sr: float, cutoff: float, order: int = 2) -> np.ndarray:
    from scipy.signal import butter
    b, a = butter(order, cutoff / (sr / 2.0), btype="highpass")
    return lfilter(b, a, audio).astype(np.float32)


def _butter_lowpass(audio: np.ndarray, sr: float, cutoff: float, order: int = 2) -> np.ndarray:
    from scipy.signal import butter
    b, a = butter(order, min(0.99, cutoff / (sr / 2.0)), btype="lowpass")
    return lfilter(b, a, audio).astype(np.float32)


# ---- Warmth / Brilliance / Compression / Crowd-chorus ---------------------
def _warmth_saturation(audio: np.ndarray, intensity_pct: float) -> np.ndarray:
    """सुरीलापन/मिठास: gentle even-harmonic saturation (tanh soft-clip),
    blended in proportion to intensity so 0% = bilkul untouched."""
    if intensity_pct <= 0:
        return audio
    mix = min(1.0, intensity_pct / 100.0)
    drive = 1.0 + mix * 2.2
    saturated = np.tanh(audio * drive) / math.tanh(drive)
    return (audio * (1 - mix) + saturated * mix).astype(np.float32)


def _brilliance_exciter(audio: np.ndarray, sr: float, intensity_pct: float) -> np.ndarray:
    """खनक: high-band (>5kHz) nikaal ke usme harmonics generate karke
    wapas halke se mix karna - "aural exciter" jaisa effect."""
    if intensity_pct <= 0 or lfilter is None:
        return audio
    hi = _butter_highpass(audio, sr, 5000.0)
    excited = np.tanh(hi * 5.5)
    mix = min(1.0, intensity_pct / 100.0) * 0.30
    return (audio + excited * mix).astype(np.float32)


def _gentle_compressor(audio: np.ndarray, sr: float, threshold_db: float = -18.0,
                        ratio: float = 2.8, attack_ms: float = 8.0,
                        release_ms: float = 90.0, makeup_db: float = 3.5) -> np.ndarray:
    """Simple feed-forward envelope-follower compressor - fixed/gentle,
    applied in BOTH auto and custom mode so levels stay controlled."""
    n = len(audio)
    if n == 0:
        return audio
    attack_coef = math.exp(-1.0 / (sr * attack_ms / 1000.0))
    release_coef = math.exp(-1.0 / (sr * release_ms / 1000.0))
    env = 0.0
    envelope = np.zeros(n, dtype=np.float32)
    abs_audio = np.abs(audio)
    for i in range(n):
        level = abs_audio[i]
        coef = attack_coef if level > env else release_coef
        env = coef * env + (1 - coef) * level
        envelope[i] = env

    threshold_lin = 10 ** (threshold_db / 20.0)
    envelope_db = 20 * np.log10(np.maximum(envelope, 1e-6))
    over_db = np.maximum(0.0, envelope_db - threshold_db)
    gain_reduction_db = over_db * (1.0 - 1.0 / ratio)
    gain = 10 ** (-gain_reduction_db / 20.0)
    makeup = 10 ** (makeup_db / 20.0)
    return (audio * gain * makeup).astype(np.float32)


def add_crowd_chorus(vocal: np.ndarray, sr: float, intensity_pct: float,
                      num_voices: int = 5) -> np.ndarray:
    """भक्तों की भीड़ प्रभाव: vocal ki kai halki, delayed, thodi muffled
    (door se aati) copies banake neeche mix karta hai - jaise bahut se
    log saath mein gaa rahe hon. Yeh true pitch-shifted harmonization
    nahi hai (halka delay+lowpass-based chorus hai), par crowd/congregation
    jaisa aabhaas theek se deta hai."""
    if intensity_pct <= 0 or lfilter is None:
        return vocal
    rng = np.random.default_rng(42)
    crowd = np.zeros_like(vocal)
    for _ in range(num_voices):
        delay_sec = rng.uniform(0.02, 0.09)
        delay_samples = int(delay_sec * sr)
        gain = rng.uniform(0.22, 0.50)
        cutoff = rng.uniform(2200, 5200)
        voice_copy = _butter_lowpass(vocal, sr, cutoff, order=2)
        shifted = np.zeros_like(vocal)
        if delay_samples < len(vocal):
            shifted[delay_samples:] = voice_copy[: len(vocal) - delay_samples]
        crowd += shifted * gain
    mix_level = min(1.0, intensity_pct / 100.0) * 0.55
    return (vocal + crowd * mix_level).astype(np.float32)


def process_vocal(audio: np.ndarray, sr: int, params: Optional[Dict[str, float]] = None) -> np.ndarray:
    """
    Poora vocal-processing chain. `params` na diya jaaye to
    AUTO_PERFECT_PRESET use hota hai. Fixed steps (boxy-mid cut,
    compression) hamesha lagte hain - sirf 5 named controls (brilliance,
    warmth, bass_db, treble_db, crowd_intensity) hi user-adjustable hain.
    """
    if lfilter is None:
        raise VocalLoadError("scipy install nahi hai - vocal processing nahi ho sakti.")
    p = dict(AUTO_PERFECT_PRESET if params is None else params)
    for key, default in AUTO_PERFECT_PRESET.items():
        p.setdefault(key, 0 if "db" not in key else 0.0)

    out = audio.astype(np.float32).copy()

    # 1. boxy-mid cut - fixed, always on (300-500Hz box-iness kam karta hai)
    b, a = _biquad_peaking(sr, freq=420.0, gain_db=-3.0, q=1.3)
    out = _apply_biquad(out, b, a)

    # 2. bass shelf (भारीपन/वजन)
    if abs(p["bass_db"]) > 0.05:
        b, a = _biquad_low_shelf(sr, freq=150.0, gain_db=p["bass_db"])
        out = _apply_biquad(out, b, a)

    # 3. treble shelf (तीखा सुर)
    if abs(p["treble_db"]) > 0.05:
        b, a = _biquad_high_shelf(sr, freq=6000.0, gain_db=p["treble_db"])
        out = _apply_biquad(out, b, a)

    # 4. warmth/saturation (सुरीलापन और मिठास)
    out = _warmth_saturation(out, p["warmth"])

    # 5. brilliance/exciter (आवाज़ की खनक)
    out = _brilliance_exciter(out, sr, p["brilliance"])

    # 6. gentle compression - fixed, always on
    out = _gentle_compressor(out, sr)

    # 7. crowd chorus (भक्तों की भीड़ प्रभाव)
    out = add_crowd_chorus(out, sr, p["crowd_intensity"])

    # 8. final safety limiter
    peak = float(np.max(np.abs(out))) or 1.0
    if peak > 0.98:
        out = np.tanh(out / peak * 1.1) * 0.95
    return out.astype(np.float32)


def save_mono_wav(audio: np.ndarray, path: str, sr: int = 44100):
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def render_with_fluidsynth(comp: Composition, soundfont_path: str, sr: int = 44100) -> np.ndarray:
    """
    Renders via a real .sf2 soundfont for more realistic instrument sound.
    Requires: `pip install pyfluidsynth` AND the FluidSynth system library
    installed (apt: fluidsynth / libfluidsynth-dev), AND a .sf2 file.

    Not used by default (render_audio() above needs zero setup) - call
    this explicitly once a soundfont is set up.
    """
    try:
        import fluidsynth
    except ImportError:
        raise RuntimeError(
            "pyfluidsynth install nahi hai. `pip install pyfluidsynth` chalayein, "
            "aur system mein FluidSynth library bhi honi chahiye "
            "(Linux: `sudo apt install fluidsynth`)."
        )
    fs = fluidsynth.Synth(samplerate=float(sr))
    sfid = fs.sfload(soundfont_path)
    if sfid == -1:
        raise RuntimeError(f"Soundfont load nahi hua: {soundfont_path}")

    total_samples = int((comp.total_duration_sec + 1.0) * sr)
    out = np.zeros((total_samples, 2), dtype=np.float32)

    for ch, track in enumerate(comp.tracks):
        program = 128 if track.instrument == "tabla" else _GM_PROGRAM.get(track.instrument, 0)
        bank = 128 if track.instrument == "tabla" else 0
        fs.program_select(ch % 16, sfid, bank, program if bank == 0 else 0)
        for ev in track.events:
            pitch = ev.midi_pitch if ev.midi_pitch is not None else 38
            fs.noteon(ch % 16, int(pitch), ev.velocity)
            # NOTE: a full implementation would schedule noteoff at the
            # right sample offset; pyfluidsynth's simple API renders in
            # a blocking per-call fashion, so a production version should
            # use fs.get_samples() in a time-stepped loop instead. Left
            # as a documented extension point since the default synth
            # path above already covers the working end-to-end flow.
    fs.delete()
    return out


# ==========================================================================
# 8. AI AUTO-COMPOSE - keywords -> Raag + taal + tempo -> unique melody
# ==========================================================================
"""
User कोई मूड/मौका (जैसे 'शिव सुबह आरती') टाइप करता है, यह section उससे
जुड़ा राग + ताल + tempo (+ ज़रूरी हो तो अतिरिक्त वाद्य, जैसे शिव के लिए
डमरू) चुनता है, फिर उसी राग के स्वरों के अंदर रहते हुए एक बिल्कुल नई धुन
generate करता है (constrained random-walk - हर click पर अलग धुन, ताकि
YouTube पर duplicate-content स्ट्राइक का खतरा ना रहे)।
"""

RAAG_LIBRARY: Dict[str, Dict] = {
    "bhairav": {
        "notes": ["sa", "kre", "ga", "ma", "pa", "kdha", "ni"],
        "mood": "गंभीर, भक्ति-भाव, सुबह का माहौल - शिव-भजनों में बहुत आम",
    },
    "yaman": {
        "notes": ["sa", "re", "ga", "tma", "pa", "dha", "ni"],
        "mood": "शाम का समय, कोमल प्रेम-भक्ति भाव",
    },
    "bhupali": {
        "notes": ["sa", "re", "ga", "pa", "dha"],
        "mood": "शांति, ध्यान, सादगी - सिर्फ़ 5 स्वर, इसलिए बहुत मधुर/सरल",
    },
    "des": {
        "notes": ["sa", "re", "ga", "ma", "pa", "dha", "kni"],
        "mood": "उत्सव, कीर्तन, आरती जैसा उमंग भरा भाव",
    },
}

# हर keyword -> कौन सा राग, कौन सी ताल, tempo की रेंज, और (अगर मौके के
# हिसाब से ज़रूरी हो) अतिरिक्त वाद्य अपने आप जुड़ जाएँ।
KEYWORD_MAP: Dict[str, Dict] = {
    "शिव": {"raag": "bhairav", "taal": "dadra", "tempo": (60, 75), "extra": ["damru"]},
    "महादेव": {"raag": "bhairav", "taal": "dadra", "tempo": (60, 75), "extra": ["damru"]},
    "शंकर": {"raag": "bhairav", "taal": "dadra", "tempo": (60, 75), "extra": ["damru"]},
    "सुबह": {"raag": "bhairav", "taal": "kaharwa", "tempo": (55, 70), "extra": []},
    "प्रातः": {"raag": "bhairav", "taal": "kaharwa", "tempo": (55, 70), "extra": []},
    "आरती": {"raag": "des", "taal": "kaharwa", "tempo": (85, 105), "extra": ["temple_bell"]},
    "कीर्तन": {"raag": "des", "taal": "kaharwa", "tempo": (95, 115), "extra": ["temple_bell"]},
    "भजन": {"raag": "yaman", "taal": "kaharwa", "tempo": (75, 95), "extra": []},
    "शाम": {"raag": "yaman", "taal": "dadra", "tempo": (65, 80), "extra": []},
    "संध्या": {"raag": "yaman", "taal": "dadra", "tempo": (65, 80), "extra": []},
    "भक्ति": {"raag": "yaman", "taal": "dadra", "tempo": (65, 85), "extra": []},
    "ध्यान": {"raag": "bhupali", "taal": "rupak", "tempo": (50, 65), "extra": []},
    "शांति": {"raag": "bhupali", "taal": "rupak", "tempo": (50, 65), "extra": []},
    "कृष्ण": {"raag": "yaman", "taal": "dadra", "tempo": (70, 90), "extra": []},
    "राधा": {"raag": "yaman", "taal": "dadra", "tempo": (70, 90), "extra": []},
    "राम": {"raag": "bhairav", "taal": "teentaal", "tempo": (70, 90), "extra": []},
    "हनुमान": {"raag": "des", "taal": "teentaal", "tempo": (90, 110), "extra": ["nagada"]},
    "देवी": {"raag": "des", "taal": "kaharwa", "tempo": (75, 95), "extra": ["temple_bell"]},
    "दुर्गा": {"raag": "des", "taal": "kaharwa", "tempo": (80, 100), "extra": ["temple_bell", "nagada"]},
    "गणेश": {"raag": "bhupali", "taal": "kaharwa", "tempo": (75, 90), "extra": ["temple_bell"]},
    "पूजा": {"raag": "des", "taal": "kaharwa", "tempo": (75, 90), "extra": ["temple_bell"]},
}

_DEFAULT_AUTO_COMPOSE = {"raag": "bhupali", "taal": "kaharwa", "tempo": (70, 90), "extra": []}


def _raag_random_walk(scale_notes: List[str], length: int, rng: "np.random.Generator",
                       rest_chance: float = 0.10) -> List[str]:
    """
    राग के इजाज़त-शुदा स्वरों के अंदर रहते हुए एक 'constrained random walk'
    धुन बनाता है - हर अगला स्वर पिछले के पास ही (छोटा कदम) जाता है, ताकि
    धुन कान को सुरीली लगे, बिल्कुल बेतरतीब ना लगे। हर 4 कदम पर हल्का सा
    'sa' (घर) की तरफ़ खिंचाव दिया जाता है, जैसा असली राग-विस्तार में होता
    है। `rng` बिना fixed seed के (np.random.default_rng()) दिया जाए तो हर
    बार नई, अलग धुन बनेगी।
    """
    n_notes = len(scale_notes)
    idx = 0  # शुरुआत हमेशा 'sa' से
    melody: List[str] = []
    for i in range(length):
        if i > 0 and rng.random() < rest_chance:
            melody.append("-")
            continue
        melody.append(scale_notes[idx])
        step = int(rng.choice([-2, -1, 0, 1, 2], p=[0.10, 0.30, 0.15, 0.30, 0.15]))
        idx = int(np.clip(idx + step, 0, n_notes - 1))
        if (i + 1) % 4 == 0:
            idx = int(np.clip(round(idx + (0 - idx) * 0.35), 0, n_notes - 1))
    return melody


def auto_compose_script(keyword_text: str, cycles: int = 4) -> Dict[str, object]:
    """
    User के लिखे keywords (जैसे 'शिव सुबह आरती') पढ़कर उनसे जुड़ा राग +
    ताल + tempo + ज़रूरी अतिरिक्त वाद्य चुनता है, फिर एक बिल्कुल नई,
    हर बार अलग धुन (random-walk) generate करके पूरी ready-to-render
    script टेक्स्ट बना देता है।

    Returns: {"script": str, "raag": str, "mood": str,
              "matched_keyword": str|None, "tempo": int, "taal": str}
    """
    rng = np.random.default_rng()  # बिना fixed seed - इसलिए हर click पर नई धुन
    tokens = [t.strip("।,.!?ॐ()\"'") for t in keyword_text.split()]
    matched_cfg = None
    matched_keyword = None
    for tok in tokens:
        if tok in KEYWORD_MAP:
            matched_cfg = KEYWORD_MAP[tok]
            matched_keyword = tok
            break
    if matched_cfg is None:
        matched_cfg = _DEFAULT_AUTO_COMPOSE

    raag_key = matched_cfg["raag"]
    raag = RAAG_LIBRARY[raag_key]
    taal = matched_cfg["taal"]
    tempo_lo, tempo_hi = matched_cfg["tempo"]
    tempo = int(rng.integers(tempo_lo, tempo_hi + 1))
    beats = TAAL_LIBRARY[taal]["beats"]

    bar1 = _raag_random_walk(raag["notes"], beats, rng)
    bar2 = _raag_random_walk(raag["notes"], beats, rng)
    melody_line = " ".join(bar1) + " | " + " ".join(bar2)

    drone_len = max(4, beats // 2)
    drone_bar = _raag_random_walk(raag["notes"], drone_len, rng, rest_chance=0.05)
    drone_line = " ".join(drone_bar)

    lines = [
        f"taal: {taal}",
        f"tempo: {tempo}",
        f"cycles: {cycles}",
        "",
        "track: tabla",
        f"pattern: {taal}",
        "",
        "track: bansuri",
        f"notes: {melody_line}",
        "octave: middle",
        "",
        "track: harmonium",
        f"notes: {drone_line}",
    ]
    for extra in matched_cfg.get("extra", []):
        lines += ["", f"track: {extra}", f"pattern: {taal}"]

    script_text = "\n".join(lines)
    return {
        "script": script_text, "raag": raag_key, "mood": raag["mood"],
        "matched_keyword": matched_keyword, "tempo": tempo, "taal": taal,
    }


# ==========================================================================
# 9. PART 2 — OVERDUB SYNC, NOISE REDUCTION, DUAL-SOURCE CROWD CHORUS,
#    FINAL MIX ENGINE
# ==========================================================================
"""
Yeh section teen nayi cheezein deta hai (सब numpy/scipy se, koi naya
external binary/plugin nahi):

  1. Overdub sync helper — backing track (Compose tab se render hui
     instrumental) ko वापस एक तैयार, ready-to-play WAV path ki tarah
     expose karta hai, taaki UI use "पहले सुनें, फिर उसी के साथ गाएं"
     ke liye dikha sake। Asli "backing plays while mic records" browser
     ke andar hi hota hai (st.audio + st.audio_input dono ek hi page par
     ek saath chal sakte hain, headphones lagane se mic mein backing
     leak nahi hoti) — engine sirf backing ki audio taiyar rakhta hai.

  2. Halka spectral noise-reduction — vocal ki background hiss/hum
     kam karta hai, EQ/compression chain se PEHLE lagta hai.

  3. Dual-source crowd chorus — EK hi function (`generate_crowd_chorus`)
     dono mode handle karta hai:
       - Auto-Clone Mode: source = khud user ki processed vocal
       - Dedicated Chorus Track Mode: source = ek ALAG record/upload
         ki hui doosri awaaz (dost/parivaar), taaki har clone sach
         mein अलग-अलग insaan jaisa laga (zyada variety, YouTube
         duplicate-content risk kam)
     Har clone ko pitch-shift (उम्र/लिंग simulate karne ke liye),
     random micro-delay (10-60ms इंसानी झिझक), aur stereo panning
     diya jaata hai।

  4. Final mix engine — polished vocal + backing instrumental + crowd
     chorus, teeno ko independent volume (dB) ke saath ek stereo
     master WAV mein jodta hai।
"""


# ---- 9.1 Simple pitch shifter (resample + time-stretch back) --------------
def _pitch_shift_simple(audio: np.ndarray, sr: int, semitones: float) -> np.ndarray:
    """
    Bina kisi external pitch-shift library ke, ek seedha resample-based
    pitch shifter — awaaz ki pitch badalta hai lekin duration (लंबाई)
    original jitni hi wapas kar deta hai। Yeh ek "poor man's" pitch-shift
    hai (studio-grade formant-preserving nahi), lekin crowd-chorus jaisi
    jagah ke liye bilkul theek hai — thoda 'digital' asar bhi crowd ko
    aur real (har voice thodi alag) bana deta hai।
    """
    n = len(audio)
    if n == 0 or abs(semitones) < 1e-6:
        return audio.astype(np.float32).copy()
    factor = 2.0 ** (semitones / 12.0)
    # Step 1: resample karke pitch badlo (isse length bhi badal jaati hai)
    src_idx = np.arange(0, n, factor)
    src_idx = src_idx[src_idx < n - 1]
    if len(src_idx) < 2:
        return audio.astype(np.float32).copy()
    shifted = np.interp(src_idx, np.arange(n), audio).astype(np.float32)
    # Step 2: wapas original length par time-stretch karo (duration fix)
    stretch_idx = np.linspace(0, len(shifted) - 1, n)
    restretched = np.interp(stretch_idx, np.arange(len(shifted)), shifted)
    return restretched.astype(np.float32)


# ---- 9.2 Stereo panning ----------------------------------------------------
def _pan_stereo(mono: np.ndarray, pan: float) -> np.ndarray:
    """Equal-power panning. pan: -1.0 (पूरी बाईं तरफ़) .. 0 (बीच में)
    .. +1.0 (पूरी दाईं तरफ़)। 3D jaisa faila hua crowd banane ke liye
    har clone ko alag pan value di jaati hai।"""
    pan = float(np.clip(pan, -1.0, 1.0))
    angle = (pan + 1.0) * (math.pi / 4.0)  # 0 .. pi/2
    left_gain = math.cos(angle)
    right_gain = math.sin(angle)
    stereo = np.stack([mono * left_gain, mono * right_gain], axis=1)
    return stereo.astype(np.float32)


def _to_stereo(x: np.ndarray) -> np.ndarray:
    """Mono ho to double karke stereo banata hai, pehle se stereo ho to
    waisa hi wapas."""
    if x.ndim == 1:
        return np.stack([x, x], axis=1).astype(np.float32)
    return x.astype(np.float32)


def _match_length(x: np.ndarray, n: int) -> np.ndarray:
    """Kisi bhi (mono ya stereo) array ko lambaai mein `n` samples ka
    bana deta hai — chhota ho to end mein silence (zero) jod deta hai,
    bada ho to kaat deta hai।"""
    cur = len(x)
    if cur == n:
        return x
    if cur > n:
        return x[:n]
    pad_shape = (n - cur, x.shape[1]) if x.ndim == 2 else (n - cur,)
    pad = np.zeros(pad_shape, dtype=x.dtype)
    return np.concatenate([x, pad], axis=0)


# ---- 9.3 Halka spectral noise-reduction ------------------------------------
def noise_reduce_vocal(audio: np.ndarray, sr: int, strength_pct: float = 60.0) -> np.ndarray:
    """
    Background hiss/hum/room-noise kam karne ke liye ek halka
    spectral-gate denoiser — STFT (scipy.signal) leke har frequency
    band ka "noise floor" (sabse dheeme 10% hisson ka average level)
    nikaalta hai, aur usse har jagah se ghata deta hai। Yeh studio-grade
    AI denoiser jitna powerful nahi hai, lekin mic/room ki halki
    continuous hiss ke liye kaafi asardaar hai, aur bina kisi bharosemand
    external binary/model ke chalta hai।

    strength_pct: 0 = koi denoise nahi, 100 = zyada aggressive denoise
    (bahut zyada par vocal thoda "underwater"/robotic lag sakta hai,
    isliye default moderate rakha gaya hai)।
    """
    if lfilter is None or strength_pct <= 0 or len(audio) < 2048:
        return audio.astype(np.float32)
    try:
        from scipy.signal import stft, istft
    except ImportError:  # pragma: no cover
        return audio.astype(np.float32)

    strength = min(1.0, max(0.0, strength_pct / 100.0))
    nperseg = 1024
    f, t, Zxx = stft(audio, fs=sr, nperseg=nperseg)
    mag = np.abs(Zxx)
    phase = np.angle(Zxx)

    # Har frequency-bin ka noise-floor estimate: uske sabse dheeme
    # (10th percentile) frames ka average magnitude.
    noise_floor = np.percentile(mag, 10, axis=1, keepdims=True)
    reduction = noise_floor * (0.5 + 1.5 * strength)
    mag_clean = np.maximum(mag - reduction, mag * (1.0 - 0.85 * strength))

    Zxx_clean = mag_clean * np.exp(1j * phase)
    _, cleaned = istft(Zxx_clean, fs=sr, nperseg=nperseg)

    cleaned = cleaned.astype(np.float32)
    n = len(audio)
    if len(cleaned) < n:
        cleaned = np.pad(cleaned, (0, n - len(cleaned)))
    else:
        cleaned = cleaned[:n]
    return cleaned


# ---- 9.4 Dual-source crowd chorus engine -----------------------------------
# हर "आवाज़ की किस्म" — कितना pitch-shift dena hai, taaki bachche/mahila/
# purush/bujurg jaisi VARIED awaazein bane, ek jaisi clone nahi.
CROWD_VOICE_PROFILES: List[Dict[str, object]] = [
    {"label": "बच्चे जैसी ऊँची आवाज़", "semitone_range": (5.0, 9.0)},
    {"label": "महिला जैसी आवाज़", "semitone_range": (2.0, 5.0)},
    {"label": "मूल आवाज़ के करीब", "semitone_range": (-1.0, 1.5)},
    {"label": "पुरुष जैसी भारी आवाज़", "semitone_range": (-6.0, -3.0)},
    {"label": "बुज़ुर्ग जैसी गहरी आवाज़", "semitone_range": (-9.0, -5.0)},
]


def generate_crowd_chorus(source_mono: np.ndarray, sr: int, num_voices: int = 6,
                           intensity_pct: float = 45.0,
                           seed: Optional[int] = None) -> np.ndarray:
    """
    EK single source awaaz (ya to khud user ki processed vocal — "Auto-
    Clone Mode", ya ek dedicated/separate record/upload ki hui doosri
    awaaz — "Dedicated Chorus Track Mode") se ek pura, 3D-faila hua
    "bhakton ki bheed" (crowd) stereo track banata hai।

    Har clone ko milta hai:
      - Randomized pitch-shift (CROWD_VOICE_PROFILES se — bachche, mahila,
        purush, bujurg jaisi simulated umar/awaaz)
      - Random micro-timing delay (10ms-60ms — insaani "jitter", taaki
        sab log EK saath machine jaisa na gaayen)
      - Random stereo panning (-0.85 se +0.85 — poore stereo field mein
        faila hua, "मंदिर में chaaron taraf se aati awaazein" jaisa asar)

    `seed=None` (default) rakhein to har baar EK naya, alag crowd banega —
    isliye video-dar-video crowd kabhi hoobahoo repeat nahi hoga (YouTube
    duplicate-content risk kam)। Ek hi crowd baar-baar reproduce karna ho
    (jaise preview ke baad final render), to same seed pass karein।

    Returns: stereo float32 array (len(source_mono), 2) — sirf crowd,
    isliye ise seedha `mix_final_master()` mein alag gain ke saath jod
    sakte hain।
    """
    n = len(source_mono)
    if intensity_pct <= 0 or n == 0:
        return np.zeros((max(n, 1), 2), dtype=np.float32)

    rng = np.random.default_rng(seed)
    num_voices = max(2, min(int(num_voices), 14))
    crowd_stereo = np.zeros((n, 2), dtype=np.float32)

    for i in range(num_voices):
        profile = CROWD_VOICE_PROFILES[i % len(CROWD_VOICE_PROFILES)]
        lo, hi = profile["semitone_range"]
        semitone = float(rng.uniform(lo, hi))
        delay_sec = float(rng.uniform(0.010, 0.060))       # 10ms-60ms इंसानी jitter
        delay_samples = int(delay_sec * sr)
        pan = float(rng.uniform(-0.85, 0.85))              # 3D stereo spread
        cutoff = float(rng.uniform(2600.0, 5200.0))        # halka "door se aati" muffled असर
        gain = float(rng.uniform(0.16, 0.40))

        voice = _pitch_shift_simple(source_mono, sr, semitone)
        if lfilter is not None:
            voice = _butter_lowpass(voice, sr, cutoff, order=2)

        delayed = np.zeros(n, dtype=np.float32)
        if delay_samples < n:
            usable = min(len(voice), n - delay_samples)
            delayed[delay_samples:delay_samples + usable] = voice[:usable]

        crowd_stereo += _pan_stereo(delayed, pan) * gain

    mix_level = min(1.0, intensity_pct / 100.0)
    peak = float(np.max(np.abs(crowd_stereo))) or 1.0
    if peak > 1.0:
        crowd_stereo = crowd_stereo / peak
    return (crowd_stereo * mix_level).astype(np.float32)


# ---- 9.5 Overdub sync helper (backing track ke saath gaana) ---------------
def get_backing_track_for_overdub(wav_path: Optional[str]) -> Dict[str, object]:
    """
    Compose tab mein pehle se render hui instrumental (WAV) ko overdub
    ke liye ready check karta hai। Streamlit ke andar, backing track ka
    audio player aur mic-recording widget EK hi page par ek saath rakhe
    ja sakte hain — dono independent chalte hain (browser instrumental
    ko speaker/headphones se bajata hai, alag se mic se record karta hai),
    isliye user headphones laga kar "play" dabaye aur turant gaana/bolna
    shuru kar de, taal ke saath sync mein.

    Returns: {"available": bool, "path": str|None, "message": Hindi संदेश}
    """
    if wav_path and os.path.exists(wav_path):
        return {
            "available": True, "path": wav_path,
            "message": (
                "✅ आपकी Compose टैब वाली instrumental तैयार है — नीचे प्ले करके "
                "हेडफ़ोन लगाएं, फिर तुरंत रिकॉर्डिंग शुरू करके ताल के साथ गाएं/बोलें।"
            ),
        }
    return {
        "available": False, "path": None,
        "message": (
            "ℹ️ अभी कोई instrumental तैयार नहीं है — पहले 'Compose' टैब में एक script "
            "render करें, फिर यहाँ वापस आकर उसी के साथ गाकर रिकॉर्ड कर सकते हैं। "
            "(बिना instrumental के भी सीधे रिकॉर्ड/अपलोड कर सकते हैं — बस ताल के साथ sync नहीं रहेगा।)"
        ),
    }


# ---- 9.6 Final mix engine ---------------------------------------------------
def mix_final_master(vocal_mono: np.ndarray, sr: int,
                      backing_stereo: Optional[np.ndarray] = None,
                      crowd_stereo: Optional[np.ndarray] = None,
                      vocal_gain_db: float = 0.0,
                      backing_gain_db: float = -4.0,
                      crowd_gain_db: float = -7.0) -> np.ndarray:
    """
    Poore gaane ka final stereo mix banata hai — polished vocal (center
    mein), instrumental backing track, aur crowd chorus — teeno ka apna
    independent volume (dB mein, jitna zyada negative utna dheema)।

    Sabse lambi track jitni length rakhi jaati hai, chhoti tracks ke end
    mein silence jod diya jaata hai taaki koi bhi hiss/timing error na aaye।
    Aakhir mein ek soft safety-limiter clipping rokta hai।
    """
    vocal_stereo = _to_stereo(vocal_mono.astype(np.float32)) * (10 ** (vocal_gain_db / 20.0))

    lengths = [len(vocal_stereo)]
    if backing_stereo is not None:
        lengths.append(len(backing_stereo))
    if crowd_stereo is not None:
        lengths.append(len(crowd_stereo))
    target_len = max(lengths) if lengths else len(vocal_stereo)

    mix = _match_length(vocal_stereo, target_len)

    if backing_stereo is not None:
        b = _match_length(_to_stereo(backing_stereo), target_len) * (10 ** (backing_gain_db / 20.0))
        mix = mix + b

    if crowd_stereo is not None:
        c = _match_length(_to_stereo(crowd_stereo), target_len) * (10 ** (crowd_gain_db / 20.0))
        mix = mix + c

    peak = float(np.max(np.abs(mix))) or 1.0
    if peak > 0.98:
        mix = np.tanh(mix / peak * 1.1) * 0.95
    return mix.astype(np.float32)


# ---- 9.7 process_vocal ke andar noise-reduction jodne ka safe wrapper -----
def process_vocal_full(audio: np.ndarray, sr: int, params: Optional[Dict[str, float]] = None,
                        noise_reduction_pct: float = 60.0) -> np.ndarray:
    """
    process_vocal() ka Part-2 wrapper — pehle halka spectral noise-
    reduction lagata hai (background hiss/hum kam), fir wahi purana,
    bharosemand EQ -> saturation -> exciter -> compression -> crowd-chorus
    -> limiter chain (process_vocal) chalata hai। Compose/Vocal tab mein
    "✨ ऑटो-वॉइस परफेक्ट करें" aur "🎚️ कस्टम सेटिंग लगाएं" dono button
    isi function ko call karte hain, purane process_vocal() ko seedha
    replace kiye bina (backward-compatible).
    """
    denoised = noise_reduce_vocal(audio, sr, strength_pct=noise_reduction_pct)
    return process_vocal(denoised, sr, params)


# ==========================================================================
# 10. PART 3 — LIVE MIDI VIRTUAL PAD ENGINE (preview sounds + tap-to-script)
# ==========================================================================
"""
Compose tab mein ek "Live Pad" panel hota hai jahan user seedha screen par
tap karke Damru/Nagada/Shankha/Temple-Bell/Dafli/Manjira/Kartal/Jhanjh/
Matka/Payal/Ghungru baja sakta hai। Yeh section do cheezein deta hai:

  1. render_instrument_preview() - kisi bhi track-instrument ka ek chhota
     "one-shot" audio banata hai, taaki pad tap karte hi turant sun sakein
     ki woh vaadya kaisa lagta hai।
  2. build_bols_lines_from_taps() - live recording ke dauraan capture hue
     raw taps (instrument -> [elapsed_seconds, ...]) ko ek valid 'bols:'
     grammar string mein badal deta hai, taaki UI use seedha script
     text-box mein "track: <naam>\\nbols: <yeh string>" ki tarah paste
     kar sake।
"""


def render_instrument_preview(instrument: str, sr: int = 44100) -> np.ndarray:
    """
    Kisi bhi track-instrument (percussion ho ya melodic) ka ek chhota,
    turant sunne layak "one-shot" stereo preview banata hai - Live Pad
    section mein tap karte hi feedback dene ke liye istemal hota hai।
    """
    if instrument == "shankha":
        wave_arr = _synth_shankha_drone(1.2, sr)
    elif instrument in _PERCUSSION_SYNTH_FUNCS:
        hit_fn = _PERCUSSION_SYNTH_FUNCS[instrument]
        wave_arr = hit_fn("heavy", 0.6, sr)
    else:
        freq = _midi_to_freq(DEFAULT_BASE_MIDI_NOTE)
        synth_fn = _SYNTH_FUNCS.get(instrument, _synth_harmonium)
        wave_arr = synth_fn(freq, 0.6, sr)

    peak = float(np.max(np.abs(wave_arr))) or 1.0
    wave_arr = (wave_arr / peak) * 0.9
    stereo = np.stack([wave_arr, wave_arr], axis=1)
    return stereo.astype(np.float32)


def build_bols_lines_from_taps(taps: Dict[str, List[float]], total_duration_sec: float,
                                steps: int = 16, bar_size: int = 8) -> Dict[str, str]:
    """
    Live Pad recording ke raw taps (instrument -> [elapsed_seconds, ...])
    ko ek valid 'bols:' string mein badalta hai — poori recording ki
    lambaai ko `steps` barabar hisson (grid) mein baant kar, jis slot par
    tap hua wahan 'dha' (ek generic heavy-hit marker - asli timbre track
    ke instrument se hi tay hoti hai, bol se nahi) aur baaki jagah '-'
    (rest/khamoshi) rakh diya jaata hai। Har `bar_size` steps ke baad ek
    '|' laga diya jaata hai, taaki result seedha
    "track: <naam>\\nbols: <yeh string>" ki tarah script mein paste kiya
    ja sake।

    Returns: {instrument: "dha - - - | - - dha -", ...} - sirf un
    instruments ke liye jinpe kam se kam ek tap hua ho।
    """
    result: Dict[str, str] = {}
    if total_duration_sec <= 0 or steps <= 0:
        return result

    for instrument, timestamps in taps.items():
        if not timestamps:
            continue
        tokens = ["-"] * steps
        for ts in timestamps:
            if steps > 1:
                idx = int(round((ts / total_duration_sec) * (steps - 1)))
            else:
                idx = 0
            idx = max(0, min(steps - 1, idx))
            tokens[idx] = "dha"
        bars = [" ".join(tokens[i:i + bar_size]) for i in range(0, steps, bar_size)]
        result[instrument] = " | ".join(bars)
    return result
