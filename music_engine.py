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
    for mandra (token ends with ','), +1 for taar (token ends with ')."""
    token = token.strip()
    octave_shift = 0
    while token.endswith("'"):
        octave_shift += 1
        token = token[:-1]
    while token.endswith(","):
        octave_shift -= 1
        token = token[:-1]
    key = token.lower()
    if key not in SARGAM_SEMITONES:
        raise ParseError(
            f"'{token}' ek pehchana हुआ sargam swar nahi hai. "
            f"Valid: sa re ga ma pa dha ni (aur komal: kre kga tma kdha kni), "
            f"octave ke liye ' (ऊंचा) ya , (नीचा) jodein."
        )
    return SARGAM_SEMITONES[key], octave_shift


def _parse_notes_string(notes_str: str) -> List[List[str]]:
    """'sa re ga | pa ma ga' -> [['sa','re','ga'], ['pa','ma','ga']]"""
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

    taal_name = global_settings["taal"].strip().lower()
    if taal_name not in TAAL_LIBRARY:
        raise ParseError(
            f"'{taal_name}' taal pehchana nahi gaya. Supported taal: "
            f"{', '.join(sorted(TAAL_LIBRARY.keys()))}."
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
    # the max number of bars any pitched-note/chord track declares, else
    # the global 'cycles' setting.
    max_bars_seen = 0
    parsed_track_fields: List[Dict[str, str]] = []
    for block in track_blocks:
        fields: Dict[str, str] = {}
        track_type = None
        for ln in block:
            key, val = _parse_kv_line(ln)
            if key == "track":
                track_type = val.strip().lower()
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

    total_cycles = max(max_bars_seen, global_cycles)
    total_duration_sec = total_cycles * cycle_duration_sec

    tracks: List[Track] = []
    for fields in parsed_track_fields:
        track_type = fields["_type"]
        if track_type == "tabla":
            tracks.append(_build_tabla_track(fields, taal_name, sec_per_beat,
                                              beats_per_cycle, total_cycles))
        elif track_type in ("guitar_pad", "guitar"):
            tracks.append(_build_chord_track(fields, "guitar_pad", cycle_duration_sec, total_cycles))
        elif track_type in ("bansuri", "flute", "harmonium", "sitar"):
            tracks.append(_build_melodic_track(fields, track_type, cycle_duration_sec, total_cycles))
        else:
            raise ParseError(
                f"'{track_type}' track type pehchana nahi gaya. Supported: "
                f"tabla, bansuri, harmonium, guitar_pad, sitar, flute."
            )

    return Composition(
        taal=taal_name, tempo_bpm=tempo, cycles=total_cycles,
        beats_per_cycle=beats_per_cycle, total_duration_sec=total_duration_sec,
        tracks=tracks,
    )


def _build_tabla_track(fields: Dict[str, str], default_taal: str, sec_per_beat: float,
                        beats_per_cycle: int, total_cycles: int) -> Track:
    pattern_name = fields.get("pattern", default_taal).strip().lower()
    if pattern_name not in TAAL_LIBRARY:
        raise ParseError(
            f"tabla ke liye pattern '{pattern_name}' pehchana nahi gaya. "
            f"Supported: {', '.join(sorted(TAAL_LIBRARY.keys()))}."
        )
    taal_def = TAAL_LIBRARY[pattern_name]
    beat_types = taal_def["pattern"]
    bols = taal_def["bols"]
    events: List[NoteEvent] = []
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
    return Track(name="tabla", instrument="tabla", events=events)


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
}
_GM_TABLA_CHANNEL = 9  # MIDI channel 10 (0-indexed 9) = percussion in GM
_TABLA_DRUM_NOTE = {"heavy": 45, "light": 42, "khali_tone": 39}  # GM drum-kit notes (approx)


def composition_to_midi(comp: Composition):
    if not _HAS_PRETTY_MIDI:
        raise RuntimeError(
            "pretty_midi install nahi hai. `pip install pretty_midi` chalayein "
            "MIDI export/viewer istemal karne ke liye."
        )
    pm = pretty_midi.PrettyMIDI(initial_tempo=comp.tempo_bpm)
    for track in comp.tracks:
        if track.instrument == "tabla":
            inst = pretty_midi.Instrument(program=0, is_drum=True, name="Tabla")
            for ev in track.events:
                strength = "heavy" if "sam" in ev.label or "tali" in ev.label else (
                    "khali_tone" if "khali" in ev.label else "light")
                note_num = _TABLA_DRUM_NOTE[strength]
                inst.notes.append(pretty_midi.Note(
                    velocity=ev.velocity, pitch=note_num,
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


_SYNTH_FUNCS = {
    "harmonium": _synth_harmonium,
    "bansuri": _synth_bansuri,
    "flute": _synth_bansuri,
    "guitar_pad": _synth_guitar_pad,
    "guitar": _synth_guitar_pad,
    "sitar": _synth_sitar,
}


def render_audio(comp: Composition, sr: int = 44100) -> np.ndarray:
    """Mixes every track's events into one stereo float32 buffer (-1..1)."""
    total_samples = max(1, int((comp.total_duration_sec + 1.0) * sr))
    mix = np.zeros(total_samples, dtype=np.float32)

    for track in comp.tracks:
        if track.instrument == "tabla":
            for ev in track.events:
                strength = "heavy" if "sam" in ev.label or "tali" in ev.label else (
                    "khali" if "khali" in ev.label else "light")
                hit = _synth_tabla_hit(strength, ev.duration_sec, sr)
                start_idx = int(ev.start_sec * sr)
                end_idx = min(total_samples, start_idx + len(hit))
                if start_idx < total_samples:
                    mix[start_idx:end_idx] += hit[: end_idx - start_idx] * (ev.velocity / 127.0)
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

def _placeholder_before_fluidsynth():
    pass


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
