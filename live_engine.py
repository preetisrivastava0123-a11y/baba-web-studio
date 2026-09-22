"""
live_engine.py
Backend engine for the Live Broadcast Studio, restructured into 5 sections
per the product spec:

    Section 1 - Combined Background Media Canvas (video+image playlist,
                single-image infinite loop, auto aspect detection)
    Section 2 - Universal Audio Hub (song / instrumental / background-quiet)
    Section 3 - Live Ticker (large input, adjustable font size)
    Section 4 - Mantra Flash Hub (looping clip + animated flashing text PiP)
    Section 5 - Story/Document Hub (PDF/DOCX or typed script, TTS or
                voiceover, auto-generated background when Section 1 is empty)

--------------------------------------------------------------------------
ARCHITECTURE NOTE - why this is NOT one static FFmpeg filter_complex
--------------------------------------------------------------------------
The product spec suggested a single `-filter_complex` graph with 4 video
layers (background / mantra / story / ticker) composited inside FFmpeg.
That works well for STATIC inputs, but this spec also requires the ticker
text, the mantra flash animation, and the story caption to all be
adjustable WHILE LIVE. A static filter_complex graph is fixed the moment
FFmpeg starts - changing it means restarting the encoder (a visible
reconnect glitch on every platform).

So the video side keeps the architecture this file already used before:
Python (OpenCV + PIL) composites every frame - background canvas, webcam
PiP, mantra flash PiP, story caption, ticker - and pushes the finished
raw frame to FFmpeg over stdin. This is what makes ticker/mantra/story
text updatable live with zero interruption.

The AUDIO side is different: audio sources here are FILES (background
music, story voice-over/TTS), not something that needs live text updates
inside the render loop. So audio mixing uses a REAL FFmpeg
`-filter_complex ... amix` graph, per the product spec, via
TeeFFmpegPublisher._build_audio_pipeline().
--------------------------------------------------------------------------
"""

from __future__ import annotations

import os
import io
import math
import json
import asyncio
import tempfile
import subprocess
import threading
import time
import shutil
import logging
import collections
import uuid
import re
from dataclasses import dataclass, field
from typing import List, Optional, Callable

logger = logging.getLogger("live_engine")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")

# ---------------------------------------------------------------------------
# Optional heavy dependencies
# ---------------------------------------------------------------------------
try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None
    logger.warning("OpenCV (cv2) not installed — camera/media capture will be unavailable.")

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None
    logger.warning("NumPy not installed — frame processing will be unavailable.")

try:
    import mediapipe as mp
except ImportError:  # pragma: no cover
    mp = None
    logger.warning("MediaPipe not installed — AI background removal will be unavailable.")

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = ImageDraw = ImageFont = None
    logger.warning("Pillow not installed — text overlays (ticker/mantra/story) will be unavailable.")

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover
    sd = None
    logger.warning("sounddevice not installed — mic audio capture will be unavailable.")

try:
    import pypdf as _pypdf
except ImportError:  # pragma: no cover
    _pypdf = None

try:
    import docx as _docx  # python-docx
except ImportError:  # pragma: no cover
    _docx = None

try:
    import edge_tts as _edge_tts
except ImportError:  # pragma: no cover
    _edge_tts = None
    logger.warning("edge_tts not installed — Section 5 AI voice (TTS) will be unavailable.")


# ---------------------------------------------------------------------------
# Hardcoded Devanagari + emoji fonts (per spec: must not render as boxes)
# ---------------------------------------------------------------------------
DEVANAGARI_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "C:\\Windows\\Fonts\\Nirmala.ttf",
    "C:\\Windows\\Fonts\\Mangal.ttf",
    "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # last resort, no Devanagari glyphs
]
EMOJI_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    "C:\\Windows\\Fonts\\seguiemj.ttf",
]


def _resolve_font(size: int, want_emoji: bool = False):
    """Returns a PIL ImageFont, trying Devanagari (or emoji) fonts first."""
    if ImageFont is None:
        return None
    candidates = EMOJI_FONT_CANDIDATES if want_emoji else DEVANAGARI_FONT_CANDIDATES
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            return ImageFont.truetype(path, size, layout_engine=ImageFont.LAYOUT_RAQM)
        except Exception:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Mixed Devanagari + emoji text rendering.
#
# WHY THIS WAS NEEDED: a single PIL font has ONE glyph set. Rendering the
# whole string with only the Devanagari font shows emoji as boxes (no
# glyph for those code points in that font) - EMOJI_FONT_CANDIDATES was
# defined but never actually used anywhere. The fix is to split the
# string into runs (emoji vs everything else), render each run with the
# matching font, and paste the runs side by side - this is what "font
# fallback" means in real text-shaping engines, done manually here.
# ---------------------------------------------------------------------------
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA70-\U0001FAFF"
    "\U00002190-\U000021FF"
    "\U0000FE0F"  # variation selector (emoji presentation)
    "]",
    flags=re.UNICODE,
)


def _split_text_runs(text: str):
    """Splits text into consecutive (segment, is_emoji) runs."""
    runs = []
    current = ""
    current_is_emoji = None
    for ch in text:
        is_emoji = bool(_EMOJI_PATTERN.match(ch))
        if current_is_emoji is None:
            current_is_emoji = is_emoji
            current = ch
        elif is_emoji == current_is_emoji:
            current += ch
        else:
            runs.append((current, current_is_emoji))
            current = ch
            current_is_emoji = is_emoji
    if current:
        runs.append((current, current_is_emoji))
    return runs


def render_mixed_text_image(text: str, font_size: int, color_rgb, emoji_font_size: Optional[int] = None):
    """
    Renders one line of text with automatic per-character font fallback:
    Devanagari font for regular text, the dedicated color-emoji font for
    emoji runs (with Pillow's embedded_color=True where supported).
    Returns an RGBA PIL Image sized to fit the string, or None if there
    is nothing to render.

    NOTE: color-emoji rendering depends on Pillow's build having color
    font support (Pillow >= 9.2 AND a color-capable font file like
    NotoColorEmoji.ttf actually present at one of EMOJI_FONT_CANDIDATES).
    Without both, emoji fall back to whatever plain outline glyph the
    font provides - never a box, but not always colorful.
    """
    if not text or Image is None or ImageDraw is None:
        return None

    dev_font = _resolve_font(font_size, want_emoji=False)
    emoji_font = _resolve_font(emoji_font_size or font_size, want_emoji=True)
    if dev_font is None:
        return None

    runs = _split_text_runs(text)
    dummy = Image.new("RGB", (10, 10))
    ddraw = ImageDraw.Draw(dummy)

    segments = []  # (seg_text, font, is_emoji, w, h)
    total_w = 0
    max_h = font_size + 10
    for seg_text, is_emoji in runs:
        font = emoji_font if (is_emoji and emoji_font is not None) else dev_font
        try:
            bbox = ddraw.textbbox((0, 0), seg_text, font=font)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            w, h = len(seg_text) * font_size, font_size
        w = max(w, 1)
        segments.append((seg_text, font, is_emoji, w, h))
        total_w += w
        max_h = max(max_h, h)

    if not segments:
        return None

    canvas = Image.new("RGBA", (total_w + 20, max_h + 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    x = 10
    for seg_text, font, is_emoji, w, h in segments:
        try:
            if is_emoji:
                draw.text((x, 5), seg_text, font=font, embedded_color=True)
            else:
                draw.text((x, 5), seg_text, font=font, fill=color_rgb + (255,),
                          stroke_width=max(1, font_size // 20), stroke_fill=(0, 0, 0, 255))
        except TypeError:
            # This Pillow build doesn't support embedded_color= - fall
            # back to a plain (monochrome) glyph draw instead of crashing.
            try:
                draw.text((x, 5), seg_text, font=font, fill=color_rgb + (255,))
            except Exception:
                pass
        except Exception:
            pass
        x += w
    return canvas


# ---------------------------------------------------------------------------
# Last-start-error tracker
# ---------------------------------------------------------------------------
_last_error: Optional[str] = None


def _set_last_error(msg: Optional[str]):
    global _last_error
    _last_error = msg
    if msg:
        logger.error(msg)


def get_last_error() -> Optional[str]:
    return _last_error


# ---------------------------------------------------------------------------
# Configuration data classes
# ---------------------------------------------------------------------------

@dataclass
class Destination:
    platform: str
    rtmp_url: str
    enabled: bool = True


@dataclass
class MediaItem:
    """Section 1: one entry of the combined video/image playlist."""
    path: str
    media_type: str  # "video" | "image"
    order: int = 0
    # When True (default for video items) and media_type == "video", this
    # item's own embedded audio track is mixed into the live stream's
    # audio automatically - no need to separately re-upload the same
    # music in Section 2. Ignored for images (no audio track to use).
    use_own_audio: bool = True


AUDIO_MODE_SONG = "song"
AUDIO_MODE_INSTRUMENTAL = "instrumental"
AUDIO_MODE_BACKGROUND = "background"

# Section 2: real FFmpeg audio filters per mode (applied to the background
# music input specifically before it goes into the amix graph).
AUDIO_MODE_FILTERS = {
    AUDIO_MODE_SONG: None,
    # Standard center-channel-cancellation trick: mostly cancels whatever
    # is panned dead-center (often the lead vocal) - an approximation,
    # not true AI stem separation.
    AUDIO_MODE_INSTRUMENTAL: "pan=stereo|c0=0.5*c0+-0.5*c1|c1=-0.5*c0+0.5*c1",
    AUDIO_MODE_BACKGROUND: "volume=0.2",
}

MANTRA_TEXT_STYLES = ["Flash Pop", "Rainbow Cycle", "Neon Glow", "Bounce Scale"]


@dataclass
class StreamConfig:
    destinations: List[Destination] = field(default_factory=list)

    # Webcam (kept from before - optional, composited as its own PiP)
    webcam_on: bool = False
    background_mode: str = "none"          # none | blur | virtual | green_screen
    virtual_bg_path: Optional[str] = None
    mic_enabled: bool = False

    # Live Handover - keeps the SAME FFmpeg/RTMP connection open the whole
    # time and just switches which video/audio SOURCE feeds it (media
    # canvas -> this device's own webcam+mic), instead of stopping one
    # encoder and starting another. See LiveStreamEngine.perform_handover().
    enable_handover: bool = False

    # Section 1 - Combined Background Media Canvas
    media_items: List[MediaItem] = field(default_factory=list)
    image_hold_seconds: float = 6.0        # how long each image shows before advancing

    # Section 2 - Universal Audio Hub
    background_audio_path: Optional[str] = None
    audio_mode: str = AUDIO_MODE_SONG

    # Section 3 - Live Ticker
    ticker_text: str = ""
    ticker_font_size: int = 32
    ticker_bg_color: str = "#141414"

    # Section 4 - Mantra Flash Hub
    mantra_clip_path: Optional[str] = None     # small looping video/PiP clip
    mantra_text: str = ""
    mantra_text_style: str = "Flash Pop"

    # Section 5 - Story / Document Hub
    story_text: str = ""                        # resolved (typed or extracted)
    story_voice_path: Optional[str] = None       # TTS output or uploaded voiceover

    pip_position: str = "bottom-right"     # webcam PiP position
    width: int = 1280
    height: int = 720
    fps: int = 30


# ---------------------------------------------------------------------------
# Section 5 helper - PDF/DOCX extraction + TTS generation (standalone
# functions so live_app.py can call them directly for a "generate voice
# now" button, without needing a running engine).
# ---------------------------------------------------------------------------

def extract_text_from_pdf(path: str) -> str:
    if _pypdf is None:
        logger.warning("pypdf install nahi hai - PDF text extract nahi ho sakta.")
        return ""
    try:
        reader = _pypdf.PdfReader(path)
        return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    except Exception:
        logger.exception("PDF text extract fail hui.")
        return ""


def extract_text_from_docx(path: str) -> str:
    if _docx is None:
        logger.warning("python-docx install nahi hai - DOCX text extract nahi ho sakta.")
        return ""
    try:
        doc = _docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs).strip()
    except Exception:
        logger.exception("DOCX text extract fail hui.")
        return ""


def resolve_story_text(typed_text: str, file_path: Optional[str]) -> str:
    """Direct-typed text always wins; else extract from the uploaded file."""
    typed_text = (typed_text or "").strip()
    if typed_text:
        return typed_text
    if not file_path or not os.path.exists(file_path):
        return ""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    if ext == ".docx":
        return extract_text_from_docx(file_path)
    return ""


async def _edge_tts_save(text: str, voice_short: str, out_path: str):
    communicate = _edge_tts.Communicate(text, voice_short)
    await communicate.save(out_path)


def generate_story_tts(text: str, voice_short: str = "hi-IN-MadhurNeural") -> Optional[str]:
    """
    Generates a one-off TTS audio file for the story text (called once
    when the user clicks "voice बनाएं" in the UI - NOT regenerated per
    frame). Returns the output path, or None on failure/unavailability.
    """
    if _edge_tts is None:
        _set_last_error("edge_tts install nahi hai - AI आवाज़ (TTS) generate nahi ho sakti. `pip install edge-tts` chalayein.")
        return None
    if not text or not text.strip():
        return None
    try:
        out_path = os.path.join(tempfile.gettempdir(), f"story_tts_{uuid.uuid4().hex}.mp3")
        asyncio.run(_edge_tts_save(text, voice_short, out_path))
        if os.path.exists(out_path):
            return out_path
    except Exception as e:
        logger.exception("Story TTS generation fail hui.")
        _set_last_error(f"AI आवाज़ (TTS) generate karne mein error: {e}")
    return None


# ---------------------------------------------------------------------------
# TeeFFmpegPublisher — single-encode, multi-destination push, with a REAL
# ffmpeg `amix` audio graph (Section 2 background music + Section 5
# story voice, per the product spec) plus mic/silence.
# ---------------------------------------------------------------------------
class TeeFFmpegPublisher:
    def __init__(self, config: StreamConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self._mic_thread: Optional[threading.Thread] = None
        self._mic_stop_event = threading.Event()
        self._audio_fifo_path: Optional[str] = None
        self._stderr_tail = collections.deque(maxlen=50)
        # Live Handover: the mic branch, once present, is ALWAYS feeding
        # ffmpeg something (real audio or silence) - this flag decides
        # which, and can be flipped mid-stream with zero ffmpeg restart.
        self._mic_live_active = threading.Event()
        if config.mic_enabled:
            self._mic_live_active.set()

    def set_mic_active(self, active: bool):
        if active:
            self._mic_live_active.set()
        else:
            self._mic_live_active.clear()

    # -- Section 2 + Section 5 audio pipeline (real ffmpeg amix) -----------
    def _build_audio_pipeline(self):
        """
        Builds however many audio file/device inputs are active
        (background music, mic-or-silence, story voice/TTS) and an
        `amix` filter_complex combining them into a single [aout]
        stream. Returns (input_args, filter_complex_str_or_None,
        output_audio_label).

        The mic branch is created whenever mic_enabled OR
        enable_handover is set - even if mic starts OFF, having the
        pipe already open means Live Handover can switch it on later
        with zero ffmpeg restart (the feeder thread just starts writing
        real samples instead of silence into the same pipe).
        """
        input_args: List[str] = []
        stream_labels: List[tuple] = []
        idx = 1  # ffmpeg input index 0 is the raw video on stdin

        if self.config.background_audio_path and os.path.exists(self.config.background_audio_path):
            input_args += ["-stream_loop", "-1", "-i", self.config.background_audio_path]
            stream_labels.append((f"{idx}:a", AUDIO_MODE_FILTERS.get(self.config.audio_mode)))
            idx += 1

        # Section 1 - any video item whose own soundtrack is toggled ON
        # gets pulled in as its own additional audio input, looped from
        # its own file. NOTE: since the playlist visual advance is timed
        # separately from these audio loops, if MULTIPLE videos in the
        # playlist all have use_own_audio=True, all of their soundtracks
        # play simultaneously mixed together (not swapped in sync with
        # whichever one is currently visible) - for a single-video
        # Section 1 playlist (the common case) this is exactly "its own
        # music auto-plays", with no extra upload needed in Section 2.
        for item in self.config.media_items:
            if item.media_type == "video" and item.use_own_audio and os.path.exists(item.path):
                input_args += ["-stream_loop", "-1", "-i", item.path]
                stream_labels.append((f"{idx}:a", None))
                idx += 1

        want_mic_branch = self.config.mic_enabled or self.config.enable_handover
        if want_mic_branch and sd is not None and hasattr(os, "mkfifo"):
            fifo_path = os.path.join(tempfile.gettempdir(), f"live_mic_{os.getpid()}.pcm")
            try:
                if os.path.exists(fifo_path):
                    os.remove(fifo_path)
                os.mkfifo(fifo_path)
                self._audio_fifo_path = fifo_path
                input_args += ["-f", "s16le", "-ar", "44100", "-ac", "2", "-i", fifo_path]
                stream_labels.append((f"{idx}:a", None))
                idx += 1
            except OSError as e:
                logger.warning("Mic FIFO banane mein fail (%s) - mic/handover audio skip kiya ja raha hai.", e)

        if self.config.story_voice_path and os.path.exists(self.config.story_voice_path):
            input_args += ["-stream_loop", "-1", "-i", self.config.story_voice_path]
            stream_labels.append((f"{idx}:a", None))
            idx += 1

        if not stream_labels:
            input_args += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
            stream_labels.append((f"{idx}:a", None))
            idx += 1

        if len(stream_labels) == 1 and not stream_labels[0][1]:
            # Single plain source, nothing to filter/mix - map it directly.
            return input_args, None, stream_labels[0][0]

        filter_parts = []
        mix_inputs = []
        for i, (label, flt) in enumerate(stream_labels):
            out_label = f"aud{i}"
            if flt:
                filter_parts.append(f"[{label}]{flt}[{out_label}]")
            else:
                filter_parts.append(f"[{label}]anull[{out_label}]")
            mix_inputs.append(f"[{out_label}]")

        if len(mix_inputs) == 1:
            filter_complex = filter_parts[0]
            final_label = "aud0"
        else:
            filter_parts.append(
                f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=longest:dropout_transition=2[aout]"
            )
            filter_complex = ";".join(filter_parts)
            final_label = "aout"

        return input_args, filter_complex, final_label

    def _start_mic_feeder(self):
        if not self._audio_fifo_path or sd is None:
            return

        def _worker():
            try:
                fifo_fd = open(self._audio_fifo_path, "wb")
            except Exception:
                logger.exception("Mic FIFO open (write mode) fail hui.")
                return

            def _callback(indata, frames, time_info, status):
                try:
                    if self._mic_live_active.is_set():
                        fifo_fd.write(indata.tobytes())
                    else:
                        # Keep ffmpeg fed with silence (same byte shape) so
                        # the pipe never starves - this is what lets mic be
                        # switched ON later (Live Handover) with zero
                        # ffmpeg restart, instead of the branch not
                        # existing at all until a reconnect.
                        fifo_fd.write(b"\x00" * (frames * 2 * 2))  # 2 channels * 16-bit
                except Exception:
                    pass

            try:
                with sd.InputStream(samplerate=44100, channels=2, dtype="int16", callback=_callback):
                    while not self._mic_stop_event.is_set():
                        time.sleep(0.1)
            except Exception:
                logger.exception("Mic capture stream mein error aayi.")
            finally:
                try:
                    fifo_fd.close()
                except Exception:
                    pass

        self._mic_thread = threading.Thread(target=_worker, name="LiveMicFeeder", daemon=True)
        self._mic_thread.start()

    def _drain_stderr(self):
        if self.process is None or self.process.stderr is None:
            return
        try:
            for line in iter(self.process.stderr.readline, b""):
                self._stderr_tail.append(line.decode("utf-8", errors="ignore").rstrip())
        except Exception:
            pass

    # -- lifecycle -----------------------------------------------------------
    def start(self) -> bool:
        if shutil.which("ffmpeg") is None:
            _set_last_error(
                "ffmpeg PATH mein nahi mila. Install karein: Windows -> ffmpeg.org se laakar PATH mein "
                "jodein; Mac -> `brew install ffmpeg`; Linux -> `sudo apt install ffmpeg`."
            )
            return False

        active = [d for d in self.config.destinations if d.enabled and (d.rtmp_url or "").strip()]
        skipped = [d.platform for d in self.config.destinations if not d.enabled or not (d.rtmp_url or "").strip()]
        if skipped:
            logger.info("OFF/incomplete destinations puri tarah skip ki gayin (koi connection attempt nahi): %s", skipped)
        if not active:
            _set_last_error("Koi bhi enabled destination ke paas valid RTMP URL nahi hai.")
            return False

        audio_inputs, filter_complex, audio_label = self._build_audio_pipeline()
        tee_targets = "|".join(f"[f=flv]{d.rtmp_url}" for d in active)

        command = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{self.config.width}x{self.config.height}",
            "-r", str(self.config.fps),
            "-i", "-",
            *audio_inputs,
        ]
        if filter_complex:
            command += ["-filter_complex", filter_complex]
        command += [
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-map", "0:v",
            "-map", f"[{audio_label}]" if filter_complex else audio_label,
            "-shortest",
            "-f", "tee",
            tee_targets,
        ]

        logger.info("Single-encode FFmpeg push shuru: %d destination(s), audio_label=%s",
                    len(active), audio_label)
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        self._stderr_tail = collections.deque(maxlen=50)
        threading.Thread(target=self._drain_stderr, name="FFmpegStderrDrain", daemon=True).start()

        if self._audio_fifo_path:
            self._mic_stop_event.clear()
            self._start_mic_feeder()

        time.sleep(0.7)
        if self.process.poll() is not None:
            tail = "\n".join(self._stderr_tail) or "(ffmpeg se koi stderr output nahi mila)"
            _set_last_error(
                "FFmpeg turant band ho gaya - RTMP URL galat ho sakta hai, stream key expire ho chuki "
                "ho sakti hai, ya destination server ne connection reject kar diya. Aakhri output:\n" + tail
            )
            self.process = None
            return False

        _set_last_error(None)
        return True

    def write_frame(self, frame_bytes: bytes):
        if self.process is None or self.process.stdin is None:
            return
        try:
            self.process.stdin.write(frame_bytes)
        except (BrokenPipeError, OSError):
            logger.warning("Publisher pipe toot gayi - stop kiya ja raha hai.")
            self.stop()

    def stop(self):
        self._mic_stop_event.set()
        if self._mic_thread is not None:
            self._mic_thread.join(timeout=3)
            self._mic_thread = None
        if self.process is not None:
            try:
                if self.process.stdin:
                    self.process.stdin.close()
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
            finally:
                self.process = None
        if self._audio_fifo_path and os.path.exists(self._audio_fifo_path):
            try:
                os.remove(self._audio_fifo_path)
            except OSError:
                pass
        self._audio_fifo_path = None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def update_destinations(self, destinations: List[Destination]):
        was_running = self.is_running
        if was_running:
            self.stop()
        self.config.destinations = destinations
        if was_running:
            self.start()


MultiDestinationPublisher = TeeFFmpegPublisher  # backward-compat alias


# ---------------------------------------------------------------------------
# AI background processing (webcam only)
# ---------------------------------------------------------------------------
class BackgroundProcessor:
    def __init__(self, mode: str = "none", virtual_bg_path: Optional[str] = None):
        self.mode = mode
        self.virtual_bg_image = None
        self._segmenter = None
        if mp is not None and mode in ("blur", "virtual", "green_screen"):
            self._segmenter = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1)
        if mode == "virtual" and virtual_bg_path and cv2 is not None:
            self.virtual_bg_image = cv2.imread(virtual_bg_path)

    def set_mode(self, mode: str, virtual_bg_path: Optional[str] = None):
        self.mode = mode
        if self._segmenter is None and mp is not None and mode in ("blur", "virtual", "green_screen"):
            self._segmenter = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1)
        if mode == "virtual" and virtual_bg_path and cv2 is not None:
            self.virtual_bg_image = cv2.imread(virtual_bg_path)

    def process(self, frame):
        if self.mode == "none" or self._segmenter is None or cv2 is None or np is None:
            return frame
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._segmenter.process(rgb)
        mask = result.segmentation_mask
        condition = np.stack((mask,) * 3, axis=-1) > 0.5
        if self.mode == "blur":
            blurred = cv2.GaussianBlur(frame, (55, 55), 0)
            return np.where(condition, frame, blurred)
        if self.mode == "virtual":
            bg = self.virtual_bg_image
            if bg is None:
                bg = np.zeros_like(frame)
            elif bg.shape[:2] != frame.shape[:2]:
                bg = cv2.resize(bg, (frame.shape[1], frame.shape[0]))
            return np.where(condition, frame, bg)
        if self.mode == "green_screen":
            green = np.zeros_like(frame)
            green[:] = (0, 255, 0)
            return np.where(condition, frame, green)
        return frame


# ---------------------------------------------------------------------------
# SECTION 1 — Combined Background Media Canvas
# ---------------------------------------------------------------------------
class MediaCanvas:
    """
    Combined video+image playlist forming the base layer of the stream.

    Rule from the spec: if there is only ONE item and it is a single
    image, it becomes an infinite static loop canvas (every other section
    - mantra flash, story, ticker - keeps running on top of it forever).
    A single video behaves the same way (loops back to frame 0 forever).
    Multiple items cycle through in `order`, each image held for
    `image_hold_seconds` before advancing; videos play to their natural
    end before advancing.
    """

    def __init__(self, media_items: List[MediaItem], width: int, height: int,
                image_hold_seconds: float = 6.0):
        self.items = sorted(media_items, key=lambda m: m.order)
        self.width = width
        self.height = height
        self.image_hold_seconds = image_hold_seconds
        self._current_idx = 0
        self._video_cap = None
        self._static_image = None
        self._item_start_time = None
        if self.items:
            self._load_current()

    @staticmethod
    def detect_orientation(first_item_path: str) -> str:
        """Returns 'shorts' (9:16) or 'long' (16:9) from the first file's
        own dimensions - used to auto-set the canvas mode."""
        if cv2 is None or not first_item_path or not os.path.exists(first_item_path):
            return "shorts"
        try:
            ext = os.path.splitext(first_item_path)[1].lower()
            if ext in (".mp4", ".mov", ".avi", ".mkv"):
                cap = cv2.VideoCapture(first_item_path)
                w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                cap.release()
            else:
                img = cv2.imread(first_item_path)
                if img is None:
                    return "shorts"
                h, w = img.shape[:2]
            return "long" if w > h else "shorts"
        except Exception:
            return "shorts"

    def _load_current(self):
        item = self.items[self._current_idx]
        if item.media_type == "image":
            self._static_image = cv2.imread(item.path) if cv2 is not None else None
            self._video_cap = None
        else:
            self._video_cap = cv2.VideoCapture(item.path) if cv2 is not None else None
            self._static_image = None
        self._item_start_time = time.time()

    def _advance(self):
        if len(self.items) <= 1:
            # Single item -> infinite loop of the same item.
            if self._video_cap is not None:
                self._video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self._item_start_time = time.time()
            return
        self._current_idx = (self._current_idx + 1) % len(self.items)
        self._load_current()

    def next_frame(self):
        if np is None:
            return None
        blank = np.zeros((self.height, self.width, 3), dtype="uint8")
        if not self.items or cv2 is None:
            return blank

        item = self.items[self._current_idx]
        if item.media_type == "image":
            if self._static_image is None:
                self._advance()
                return blank
            elapsed = time.time() - (self._item_start_time or time.time())
            if elapsed >= self.image_hold_seconds and len(self.items) > 1:
                self._advance()
            frame = self._static_image
        else:
            ok, frame = (self._video_cap.read() if self._video_cap is not None else (False, None))
            if not ok:
                self._advance()
                ok, frame = (self._video_cap.read() if self._video_cap is not None else (False, None))
            if not ok or frame is None:
                return blank

        return cv2.resize(frame, (self.width, self.height))

    def release(self):
        if self._video_cap is not None:
            self._video_cap.release()


def generate_default_background(width: int, height: int, theme_hex: str = "#1B1B2F"):
    """
    Section 5's "auto-screen generator": a clean solid/gradient themed
    background used when the user hasn't uploaded anything to Section 1,
    so the story text still has somewhere nice to sit.
    """
    if np is None:
        return None
    base = tuple(int(theme_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))  # RGB
    top = np.array(base, dtype=np.float32)
    bottom = np.array([max(0, c - 40) for c in base], dtype=np.float32)
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        t = y / max(1, height - 1)
        row_color = (top * (1 - t) + bottom * t).astype(np.uint8)
        canvas[y, :, :] = row_color[::-1]  # RGB -> BGR
    return canvas


# ---------------------------------------------------------------------------
# SECTION 4 — Mantra Flash Hub (looping clip + animated flashing text PiP)
# ---------------------------------------------------------------------------
class MantraFlashOverlay:
    """
    Box A: a small looping clip (video) shown as a PiP box.
    Box B: mantra text, rendered once via PIL (Devanagari+emoji fonts)
    then animated live every frame according to `style` - no per-frame
    PIL re-rendering, just cheap numpy/OpenCV transforms of the
    pre-rendered text image, so this is fast enough for real-time.
    """

    def __init__(self, clip_path: Optional[str] = None, text: str = "",
                style: str = "Flash Pop", canvas_width: int = 1280, canvas_height: int = 720,
                pip_size_pct: float = 0.30):
        self.clip_path = clip_path
        self.text = text
        self.style = style if style in MANTRA_TEXT_STYLES else MANTRA_TEXT_STYLES[0]
        self.pip_w = int(canvas_width * pip_size_pct)
        self.pip_h = int(self.pip_w * 0.62)
        self._cap = cv2.VideoCapture(clip_path) if (clip_path and cv2 is not None and os.path.exists(clip_path)) else None
        self._text_rgb = None   # np array (h, w, 3) - white silhouette
        self._text_alpha = None  # np array (h, w) 0-255
        self._start_time = time.time()
        self._rebuild_text()

    def set_text(self, text: str):
        if text != self.text:
            self.text = text
            self._rebuild_text()

    def set_style(self, style: str):
        if style in MANTRA_TEXT_STYLES:
            self.style = style

    def _rebuild_text(self):
        self._text_rgb = None
        self._text_alpha = None
        if not self.text or Image is None or np is None:
            return
        font_size = max(18, int(self.pip_h * 0.28))
        canvas_w, canvas_h = self.pip_w, int(self.pip_h * 0.4)

        rendered = render_mixed_text_image(self.text, font_size, (255, 255, 255))
        if rendered is None:
            return

        # Center the rendered (auto-sized) text image onto the fixed PiP
        # text canvas so positioning stays consistent regardless of length.
        img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        rw, rh = rendered.size
        x = max(0, (canvas_w - rw) // 2)
        y = max(0, (canvas_h - rh) // 2)
        img.paste(rendered, (x, y), rendered)

        arr = np.array(img)
        self._text_rgb = arr[:, :, 2::-1].copy()  # RGB->BGR (drop alpha for the color plane)
        self._text_alpha = arr[:, :, 3].copy()

    def _next_clip_frame(self):
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        return cv2.resize(frame, (self.pip_w, self.pip_h))

    def _animated_text_layer(self, t: float):
        """Returns (rgb, alpha) animated per `self.style`, or (None, None)."""
        if self._text_rgb is None:
            return None, None
        rgb = self._text_rgb
        alpha = self._text_alpha.astype(np.float32)

        if self.style == "Flash Pop":
            flash = abs(math.sin(t * 2 * math.pi * 1.2))  # ~1.2 Hz flash
            alpha = alpha * (0.35 + 0.65 * flash)

        elif self.style == "Rainbow Cycle":
            hue = int((t * 60) % 180)
            hsv_color = np.uint8([[[hue, 255, 255]]])
            bgr_color = cv2.cvtColor(hsv_color, cv2.COLOR_HSV2BGR)[0, 0]
            mask = (alpha > 10)
            rgb = rgb.copy()
            rgb[mask] = bgr_color

        elif self.style == "Neon Glow":
            glow_strength = 0.5 + 0.5 * abs(math.sin(t * 2 * math.pi * 0.8))
            blurred = cv2.GaussianBlur(rgb, (15, 15), 0)
            rgb = cv2.addWeighted(rgb, 1.0, blurred, glow_strength, 0)

        elif self.style == "Bounce Scale":
            scale = 1.0 + 0.15 * abs(math.sin(t * 2 * math.pi * 1.0))
            h, w = rgb.shape[:2]
            new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
            rgb = cv2.resize(rgb, (new_w, new_h))
            alpha = cv2.resize(alpha, (new_w, new_h))
            canvas_rgb = np.zeros((h, w, 3), dtype=rgb.dtype)
            canvas_alpha = np.zeros((h, w), dtype=alpha.dtype)
            y0 = max(0, (new_h - h) // 2)
            x0 = max(0, (new_w - w) // 2)
            y1 = min(new_h, y0 + h)
            x1 = min(new_w, x0 + w)
            oy = max(0, (h - new_h) // 2)
            ox = max(0, (w - new_w) // 2)
            ch, cw = y1 - y0, x1 - x0
            canvas_rgb[oy:oy + ch, ox:ox + cw] = rgb[y0:y1, x0:x1]
            canvas_alpha[oy:oy + ch, ox:ox + cw] = alpha[y0:y1, x0:x1]
            rgb, alpha = canvas_rgb, canvas_alpha

        return rgb, alpha

    def apply(self, frame):
        if not self.text and self._cap is None:
            return frame
        if cv2 is None or np is None:
            return frame

        h, w = frame.shape[:2]
        x = w - self.pip_w - 20
        y = 20
        if x < 0 or y + self.pip_h > h:
            return frame  # canvas too small for this PiP - skip rather than crash

        frame = frame.copy()
        pip_bg = self._next_clip_frame()
        if pip_bg is not None:
            frame[y:y + self.pip_h, x:x + self.pip_w] = pip_bg
        cv2.rectangle(frame, (x - 2, y - 2), (x + self.pip_w + 2, y + self.pip_h + 2), (255, 255, 255), 2)

        t = time.time() - self._start_time
        text_rgb, text_alpha = self._animated_text_layer(t)
        if text_rgb is not None:
            th, tw = text_rgb.shape[:2]
            ty = y + self.pip_h - th - 6
            tx = x + max(0, (self.pip_w - tw) // 2)
            if ty >= 0 and tx >= 0 and ty + th <= h and tx + tw <= w:
                region = frame[ty:ty + th, tx:tx + tw].astype(np.float32)
                a = (text_alpha[:, :, None] / 255.0)
                blended = region * (1 - a) + text_rgb.astype(np.float32) * a
                frame[ty:ty + th, tx:tx + tw] = blended.astype(np.uint8)

        return frame

    def release(self):
        if self._cap is not None:
            self._cap.release()


# ---------------------------------------------------------------------------
# SECTION 5 — Story / Document caption overlay
# ---------------------------------------------------------------------------
class StoryOverlay:
    """Renders the resolved story/script text as a readable on-screen
    caption block (word-wrapped, Devanagari-safe)."""

    def __init__(self, text: str = "", canvas_width: int = 1280, canvas_height: int = 720):
        self.text = text
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self._strip = None
        self._strip_pos = (0, 0)
        self._rebuild()

    def set_text(self, text: str):
        if text != self.text:
            self.text = text
            self._rebuild()

    def _rebuild(self):
        self._strip = None
        if not self.text or Image is None or np is None:
            return
        font_size = max(16, int(self.canvas_height * 0.035))

        import textwrap
        max_chars = max(10, int(self.canvas_width / max(1, int(font_size * 0.55))))
        lines = textwrap.wrap(self.text, width=max_chars)[:4]
        if not lines:
            return

        line_images = [render_mixed_text_image(line, font_size, (255, 255, 255)) for line in lines]
        line_images = [img for img in line_images if img is not None]
        if not line_images:
            return

        line_gap = 6
        max_w = max(img.width for img in line_images)
        total_h = sum(img.height for img in line_images) + line_gap * (len(line_images) - 1)
        band_w = min(self.canvas_width - 40, max_w + 40)
        band_h = total_h + 30

        img = Image.new("RGBA", (band_w, band_h), (0, 0, 0, 140))
        y = 15
        for line_img in line_images:
            x = max(0, (band_w - line_img.width) // 2)
            img.paste(line_img, (x, y), line_img)
            y += line_img.height + line_gap

        arr = np.array(img)
        self._strip = arr[:, :, [2, 1, 0, 3]]  # RGBA -> BGRA
        x = max(0, (self.canvas_width - band_w) // 2)
        y = max(0, self.canvas_height - band_h - 90)  # sits above the ticker band
        self._strip_pos = (x, y)

    def apply(self, frame):
        if self._strip is None or cv2 is None or np is None:
            return frame
        h, w = frame.shape[:2]
        x, y = self._strip_pos
        sh, sw = self._strip.shape[:2]
        if y + sh > h or x + sw > w or x < 0 or y < 0:
            return frame
        frame = frame.copy()
        region = frame[y:y + sh, x:x + sw].astype(np.float32)
        alpha = (self._strip[:, :, 3:4].astype(np.float32) / 255.0)
        rgb = self._strip[:, :, :3].astype(np.float32)
        blended = region * (1 - alpha) + rgb * alpha
        frame[y:y + sh, x:x + sw] = blended.astype(np.uint8)
        return frame


# ---------------------------------------------------------------------------
# SECTION 3 — Live Ticker (Devanagari+emoji safe, adjustable font size)
# ---------------------------------------------------------------------------
class TickerOverlay:
    def __init__(self, text: str = "", speed_px_per_frame: int = 4, font_size: int = 32,
                canvas_width: int = 1280, bg_color_hex: str = "#141414"):
        self.text = text
        self.speed = speed_px_per_frame
        self.font_size = font_size
        self.bar_height = max(36, int(font_size * 1.8))
        self.canvas_width = canvas_width
        self.bg_color = tuple(int(bg_color_hex.lstrip("#")[i:i + 2], 16) for i in (4, 2, 0)) if bg_color_hex else (20, 20, 20)
        self._strip = None
        self._strip_w = 0
        self._scroll_x = 0
        self._rebuild_strip()

    def set_text(self, text: str):
        if text != self.text:
            self.text = text
            self._scroll_x = 0
            self._rebuild_strip()

    def set_font_size(self, size: int):
        if size != self.font_size:
            self.font_size = size
            self.bar_height = max(36, int(size * 1.8))
            self._rebuild_strip()

    def _rebuild_strip(self):
        self._strip = None
        self._strip_w = 0
        if not self.text or Image is None or np is None:
            return

        spacer = "      •      "
        one_cycle_text = self.text + spacer
        segment_img = render_mixed_text_image(one_cycle_text, self.font_size, (255, 255, 255))
        if segment_img is None:
            return

        seg_w, seg_h = segment_img.size
        band_h = self.bar_height
        y = max(0, (band_h - seg_h) // 2)

        cycle_img = Image.new("RGB", (max(seg_w, 1), band_h), self.bg_color)
        cycle_img.paste(segment_img, (0, y), segment_img)

        repeat_count = max(2, (self.canvas_width * 2) // max(1, seg_w) + 2)
        strip_w = seg_w * repeat_count
        strip_img = Image.new("RGB", (strip_w, band_h), self.bg_color)
        for i in range(repeat_count):
            strip_img.paste(cycle_img, (i * seg_w, 0))

        self._strip = np.array(strip_img)[:, :, ::-1].copy()
        self._strip_w = strip_w

    def apply(self, frame):
        if self._strip is None or cv2 is None or np is None:
            return frame
        h, w = frame.shape[:2]
        bar_top = max(0, h - self.bar_height)
        band_h = min(self.bar_height, h - bar_top)

        self._scroll_x = (self._scroll_x + self.speed) % self._strip_w
        offset = self._scroll_x
        if offset + w <= self._strip_w:
            window = self._strip[:band_h, offset:offset + w]
        else:
            first = self._strip[:band_h, offset:]
            remaining = w - first.shape[1]
            second = self._strip[:band_h, :remaining]
            window = np.concatenate([first, second], axis=1)

        frame = frame.copy()
        region = frame[bar_top:bar_top + band_h, 0:w]
        frame[bar_top:bar_top + band_h, 0:w] = cv2.addWeighted(window, 0.9, region, 0.1, 0)
        return frame


# ---------------------------------------------------------------------------
# Webcam PiP compositor (kept from before - optional, separate corner
# from the Section 4 mantra PiP which defaults to top-right)
# ---------------------------------------------------------------------------
class Compositor:
    _POSITION_MAP = {
        "bottom-right": lambda w, h, pw, ph: (w - pw - 20, h - ph - 20),
        "bottom-left": lambda w, h, pw, ph: (20, h - ph - 20),
        "top-right": lambda w, h, pw, ph: (w - pw - 20, 20),
    }

    def __init__(self, canvas_width: int, canvas_height: int, pip_position: str = "bottom-right"):
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.pip_position = pip_position

    def set_position(self, position: str):
        self.pip_position = position

    def composite(self, background_frame, webcam_frame=None, pip_scale: float = 0.28):
        if cv2 is None or np is None:
            return background_frame
        canvas = cv2.resize(background_frame, (self.canvas_width, self.canvas_height))
        if webcam_frame is None:
            return canvas
        pip_w = int(self.canvas_width * pip_scale)
        pip_h = int(self.canvas_height * pip_scale)
        pip_frame = cv2.resize(webcam_frame, (pip_w, pip_h))
        position_fn = self._POSITION_MAP.get(self.pip_position, self._POSITION_MAP["bottom-right"])
        x, y = position_fn(self.canvas_width, self.canvas_height, pip_w, pip_h)
        cv2.rectangle(canvas, (x - 2, y - 2), (x + pip_w + 2, y + pip_h + 2), (255, 255, 255), 2)
        canvas[y:y + pip_h, x:x + pip_w] = pip_frame
        return canvas


# ---------------------------------------------------------------------------
# Main capture / composite / publish loop
# ---------------------------------------------------------------------------
class LiveStreamEngine:
    def __init__(self, config: StreamConfig):
        self.config = config
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._camera = None
        # Live Handover: "media" = Section 1 canvas (+ optional webcam PiP
        # if webcam_on); "webcam_full" = full-screen webcam takeover, the
        # actual handover moment. Overlays (mantra/story/ticker) still run
        # on top either way - only the base visual source changes.
        self._visual_source = "media"
        self._handed_over = False

        # Section 1 base canvas
        if not config.media_items:
            self._canvas = None
            self._default_bg = generate_default_background(config.width, config.height)
        else:
            self._canvas = MediaCanvas(config.media_items, config.width, config.height, config.image_hold_seconds)
            self._default_bg = None

        self._bg_processor = BackgroundProcessor(config.background_mode, config.virtual_bg_path)
        self._compositor = Compositor(config.width, config.height, config.pip_position)
        self._mantra = MantraFlashOverlay(
            config.mantra_clip_path, config.mantra_text, config.mantra_text_style,
            config.width, config.height,
        )
        self._story = StoryOverlay(config.story_text, config.width, config.height)
        self._ticker = TickerOverlay(
            config.ticker_text, font_size=config.ticker_font_size,
            canvas_width=config.width, bg_color_hex=config.ticker_bg_color,
        )
        self._publisher = TeeFFmpegPublisher(config)

        self._frames_pushed = 0
        self._start_time: Optional[float] = None
        self.on_status_change: Optional[Callable[[str], None]] = None

    def start(self) -> bool:
        if self._running:
            return True
        if cv2 is None or np is None:
            _set_last_error("OpenCV/NumPy install nahi hai - capture loop start nahi ho sakta.")
            self._notify("error: opencv/numpy missing")
            return False

        if not self._publisher.start():
            self._notify("error: publisher failed to start")
            return False

        # Open the camera up-front whenever webcam is on OR handover is
        # enabled, so it's already warmed up and ready the instant the
        # user triggers the handover (no cold-start delay mid-stream).
        if self.config.webcam_on or self.config.enable_handover:
            self._camera = cv2.VideoCapture(0)
            self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
            self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
            if not self._camera.isOpened():
                logger.warning("Webcam open nahi hui - is server/cloud par physical camera nahi hoga to yeh expected hai.")

        self._running = True
        self._frames_pushed = 0
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._run_loop, name="LiveStreamEngineLoop", daemon=True)
        self._thread.start()
        self._notify("live")
        return True

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        if self._camera is not None:
            self._camera.release()
            self._camera = None
        if self._canvas is not None:
            self._canvas.release()
        self._mantra.release()
        self._publisher.stop()
        self._notify("stopped")

    def _notify(self, status: str):
        if self.on_status_change:
            try:
                self.on_status_change(status)
            except Exception:
                logger.exception("on_status_change callback raised.")

    def get_status(self) -> dict:
        uptime = (time.time() - self._start_time) if (self._running and self._start_time) else 0
        return {
            "running": self._running,
            "publisher_alive": self._publisher.is_running,
            "frames_pushed": self._frames_pushed,
            "uptime_sec": round(uptime, 1),
            "handed_over": self._handed_over,
            "visual_source": self._visual_source,
        }

    # -- live updates (Section 3/4/5 text can change without restarting) ----
    def update_ticker(self, text: str):
        self._ticker.set_text(text)

    def update_ticker_font_size(self, size: int):
        self._ticker.set_font_size(size)

    def update_mantra_text(self, text: str):
        self._mantra.set_text(text)

    def update_mantra_style(self, style: str):
        self._mantra.set_style(style)

    def update_story_text(self, text: str):
        self._story.set_text(text)

    def update_background_mode(self, mode: str, virtual_bg_path: Optional[str] = None):
        self._bg_processor.set_mode(mode, virtual_bg_path)

    def update_pip_position(self, position: str):
        self._compositor.set_position(position)

    def update_destinations(self, destinations: List[Destination]):
        self._publisher.update_destinations(destinations)

    # -- Live Handover: switch source WITHOUT touching the RTMP connection --
    def perform_handover(self):
        """
        The actual "handover" moment: switches the base visual layer from
        the Section 1 media canvas to this device's own full-screen
        webcam, and turns the mic on - all while the SAME ffmpeg process
        keeps pushing to YouTube/etc the entire time, so the platform
        never sees a disconnect (no "stream interrupted", no chat/viewer
        drop). Requires enable_handover=True (so the camera + mic pipe
        were already warmed up at stream start) and a working webcam.
        """
        if not self.config.enable_handover:
            _set_last_error("Handover enable nahi kiya gaya tha (enable_handover=False) - stream start karte waqt yeh chalu karna zaroori hai.")
            return False
        if self._camera is None or not self._camera.isOpened():
            _set_last_error("Webcam available nahi hai is machine par - handover nahi ho sakta. (Cloud server par physical camera nahi hota.)")
            return False
        self._visual_source = "webcam_full"
        self._publisher.set_mic_active(True)
        self._handed_over = True
        logger.info("LIVE HANDOVER ho gaya: visual source ab webcam hai, mic ON hai - RTMP connection wahi purana chal raha hai.")
        return True

    def revert_handover(self):
        """Switches back to the Section 1 media canvas / mic off, same
        persistent connection - the reverse of perform_handover()."""
        self._visual_source = "media"
        self._publisher.set_mic_active(self.config.mic_enabled)
        self._handed_over = False

    def is_handed_over(self) -> bool:
        return self._handed_over

    def _next_background_frame(self):
        if self._canvas is not None:
            frame = self._canvas.next_frame()
            if frame is not None:
                return frame
        if self._default_bg is not None:
            return self._default_bg
        return np.zeros((self.config.height, self.config.width, 3), dtype="uint8")

    def _run_loop(self):
        frame_interval = 1.0 / max(self.config.fps, 1)
        while self._running:
            loop_start = time.time()
            try:
                webcam_frame = None
                if self._camera is not None and self._camera.isOpened() and (
                    self.config.webcam_on or self._visual_source == "webcam_full"
                ):
                    ok, raw = self._camera.read()
                    if ok:
                        webcam_frame = self._bg_processor.process(raw)

                if self._visual_source == "webcam_full" and webcam_frame is not None:
                    # Handover mode: the real camera feed IS the base
                    # layer (full screen), not a small PiP.
                    frame = cv2.resize(webcam_frame, (self.config.width, self.config.height))
                else:
                    background_frame = self._next_background_frame()
                    frame = self._compositor.composite(background_frame, webcam_frame)

                frame = self._mantra.apply(frame)
                frame = self._story.apply(frame)
                frame = self._ticker.apply(frame)

                self._publisher.write_frame(frame.tobytes())
                self._frames_pushed += 1
            except Exception:
                # A single bad frame must NEVER kill this background
                # thread (that would silently end the whole broadcast
                # even though the process is still alive) - log and
                # keep going.
                logger.exception("Frame compose/push mein error - skip karke agle frame par jaa rahe hain.")

            elapsed = time.time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Module-level singleton API
# ---------------------------------------------------------------------------
_engine: Optional[LiveStreamEngine] = None
_engine_lock = threading.Lock()


def start_stream(stream_configs: StreamConfig) -> bool:
    global _engine
    with _engine_lock:
        if _engine is not None:
            _set_last_error("Ek stream pehle se chal rahi hai. Pehle stop_stream() call karein.")
            return False
        engine = LiveStreamEngine(stream_configs)
        if not engine.start():
            return False
        _engine = engine
        return True


def stop_stream() -> bool:
    global _engine
    with _engine_lock:
        if _engine is None:
            return False
        _engine.stop()
        _engine = None
        return True


def update_live_ticker(text: str):
    if _engine is not None:
        _engine.update_ticker(text)


def perform_live_handover() -> bool:
    """The actual handover trigger - switches to real webcam+mic on the
    SAME running RTMP connection. Returns False (with get_last_error()
    explaining why) if handover wasn't enabled at start or no camera is
    available on this machine."""
    if _engine is None:
        _set_last_error("Koi stream chal hi nahi rahi - pehle Start Live karein.")
        return False
    return _engine.perform_handover()


def revert_live_handover():
    if _engine is not None:
        _engine.revert_handover()


def is_handed_over() -> bool:
    if _engine is not None:
        return _engine.is_handed_over()
    return False


def update_live_ticker_font_size(size: int):
    if _engine is not None:
        _engine.update_ticker_font_size(size)


def update_live_mantra_text(text: str):
    if _engine is not None:
        _engine.update_mantra_text(text)


def update_live_mantra_style(style: str):
    if _engine is not None:
        _engine.update_mantra_style(style)


def update_live_story_text(text: str):
    if _engine is not None:
        _engine.update_story_text(text)


def update_live_destinations(destinations: List[Destination]):
    if _engine is not None:
        _engine.update_destinations(destinations)


def update_live_background(mode: str, virtual_bg_path: Optional[str] = None):
    if _engine is not None:
        _engine.update_background_mode(mode, virtual_bg_path)


def get_stream_status() -> Optional[dict]:
    if _engine is not None:
        return _engine.get_status()
    return None


def is_streaming() -> bool:
    return _engine is not None


def check_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


# ---------------------------------------------------------------------------
# SCHEDULER — arms a background thread (independent of any browser
# session/tab) that automatically start_stream()'s at a future time and
# stop_stream()'s at another future time.
#
# IMPORTANT: this thread lives inside THIS Python server process. It
# keeps running whether or not any browser is connected - but if the
# underlying process itself is restarted or put to sleep (e.g. Streamlit
# Community Cloud's "sleep after inactivity" policy) BEFORE the
# scheduled time, the thread dies with it and the schedule silently
# never fires. Use an external uptime-ping service (UptimeRobot,
# cron-job.org, etc.) hitting the app's URL every few minutes if you
# need unattended scheduling to be reliable on a free host.
# ---------------------------------------------------------------------------
_scheduler_thread: Optional[threading.Thread] = None
_scheduler_stop_event = threading.Event()
_scheduler_info: dict = {}
_scheduler_lock = threading.Lock()


def schedule_stream(config: StreamConfig, start_at_epoch: Optional[float],
                    stop_at_epoch: Optional[float]) -> bool:
    """
    Arms the scheduler: waits (if needed) until start_at_epoch, then
    calls start_stream(config); if stop_at_epoch is given, later calls
    stop_stream() at that time too. Pass start_at_epoch=None to start
    immediately, and stop_at_epoch=None to run until manually stopped.
    Returns False (with get_last_error() explaining why) if a schedule
    is already armed.
    """
    global _scheduler_thread
    with _scheduler_lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            _set_last_error("Ek schedule pehle se armed hai - pehle use cancel karein.")
            return False

        _scheduler_stop_event.clear()
        _scheduler_info.clear()
        _scheduler_info.update({
            "start_at": start_at_epoch,
            "stop_at": stop_at_epoch,
            "armed": True,
            "fired_start": False,
            "fired_stop": False,
        })

        def _worker():
            try:
                if start_at_epoch:
                    while time.time() < start_at_epoch and not _scheduler_stop_event.is_set():
                        time.sleep(1)
                if _scheduler_stop_event.is_set():
                    return

                logger.info("Scheduler: start time aa gaya - stream start kar rahe hain.")
                start_stream(config)
                _scheduler_info["fired_start"] = True

                if stop_at_epoch:
                    while time.time() < stop_at_epoch and not _scheduler_stop_event.is_set():
                        time.sleep(1)
                    if not _scheduler_stop_event.is_set():
                        logger.info("Scheduler: stop time aa gaya - stream stop kar rahe hain.")
                        stop_stream()
                        _scheduler_info["fired_stop"] = True
            except Exception:
                logger.exception("Scheduler thread mein error aayi.")
            finally:
                _scheduler_info["armed"] = False

        _scheduler_thread = threading.Thread(target=_worker, name="LiveScheduler", daemon=True)
        _scheduler_thread.start()
        return True


def cancel_schedule() -> bool:
    """Cancels a pending (not-yet-fired) schedule. If the start already
    fired and the stream is live, this only cancels the scheduled STOP -
    stop the stream manually via stop_stream() instead."""
    global _scheduler_thread
    with _scheduler_lock:
        if _scheduler_thread is None or not _scheduler_thread.is_alive():
            return False
        _scheduler_stop_event.set()
        _scheduler_info["armed"] = False
        return True


def get_schedule_status() -> Optional[dict]:
    if not _scheduler_info:
        return None
    return dict(_scheduler_info)


# ---------------------------------------------------------------------------
# SELF-PING KEEP-ALIVE - lets the app keep ITSELF awake on free hosts like
# Streamlit Community Cloud, without needing an external service
# (UptimeRobot/cron-job.org). You enter your own app's public URL ONCE in
# the UI; from then on, arming a Schedule (or going live) automatically
# starts this background thread - zero extra effort after that one entry.
#
# HONEST LIMITATION: this is a best-effort mitigation, not a guarantee.
# It works by regularly requesting the app's own URL, which in practice
# keeps most free hosts (including Streamlit Community Cloud) from
# treating the app as inactive - but it CANNOT revive an app that has
# ALREADY fully gone to sleep (a sleeping process can't run a thread to
# wake itself up - that's a logical impossibility, not a limitation of
# this code). It only works if the ping interval stays comfortably
# shorter than the host's inactivity timeout, which is why the default
# below is a conservative 4 minutes.
# ---------------------------------------------------------------------------
_keepalive_thread: Optional[threading.Thread] = None
_keepalive_stop_event = threading.Event()
_keepalive_url: Optional[str] = None


def start_keepalive(app_url: str, interval_sec: float = 240.0) -> bool:
    """Starts (or, if already running for the same URL, leaves alone) the
    self-ping background thread. Safe to call repeatedly - e.g. every
    time a schedule is armed or the stream starts."""
    global _keepalive_thread, _keepalive_url
    if not app_url or not app_url.strip():
        return False

    if _keepalive_thread is not None and _keepalive_thread.is_alive() and _keepalive_url == app_url:
        return True  # already pinging this exact URL, nothing to do

    stop_keepalive()  # stop any previous ping loop (e.g. pinging an old URL)
    _keepalive_url = app_url.strip()
    _keepalive_stop_event.clear()

    def _worker():
        try:
            import requests
        except ImportError:
            logger.warning("`requests` install nahi hai - self-ping keep-alive kaam nahi karega. `pip install requests` chalayein.")
            return
        while not _keepalive_stop_event.is_set():
            try:
                requests.get(_keepalive_url, timeout=10)
                logger.info("Keep-alive self-ping bheja gaya: %s", _keepalive_url)
            except Exception as e:
                logger.warning("Keep-alive ping fail hui (%s) - agli baar phir try karenge.", e)
            _keepalive_stop_event.wait(interval_sec)

    _keepalive_thread = threading.Thread(target=_worker, name="KeepAlivePing", daemon=True)
    _keepalive_thread.start()
    logger.info("Self-ping keep-alive shuru: har %.0f second mein %s ko ping kiya jaayega.", interval_sec, _keepalive_url)
    return True


def stop_keepalive():
    _keepalive_stop_event.set()


def is_keepalive_running() -> bool:
    return _keepalive_thread is not None and _keepalive_thread.is_alive()


if __name__ == "__main__":
    demo_config = StreamConfig(
        destinations=[Destination(platform="YouTube", rtmp_url="rtmp://a.rtmp.youtube.com/live2/REPLACE_ME", enabled=True)],
        webcam_on=False,
        ticker_text="Demo ticker...",
        mantra_text="ॐ नमः शिवाय",
    )
    print("StreamConfig built successfully:", demo_config)
    print("ffmpeg available:", check_ffmpeg_available())
