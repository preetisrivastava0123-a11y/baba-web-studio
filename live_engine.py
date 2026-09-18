"""
live_engine.py
Heavy-duty backend processing engine for multi-destination RTMP live streaming.

Responsibilities:
    - Capture webcam / audio-only visuals via OpenCV.
    - Apply AI background processing (blur, virtual background, green-screen key)
      via MediaPipe Selfie Segmentation.
    - Composite a Picture-in-Picture (PIP) layout: background media + webcam + ticker.
    - Push the composited frames + audio to one or more RTMP destinations
      simultaneously (YouTube, Facebook, Instagram, or any custom RTMP URL)
      using a SINGLE non-blocking FFmpeg process with the `tee` muxer.
    - Expose a clean start_stream(stream_configs) / stop_stream() API so that
      live_app.py (the Streamlit UI) can drive it without knowing any internals.

This module has no Streamlit dependency — it is a pure backend engine and can
be imported and driven from live_app.py:

    from live_engine import start_stream, stop_stream, StreamConfig, Destination

    configs = StreamConfig(
        destinations=[
            Destination(platform="YouTube", rtmp_url="rtmp://a.rtmp.youtube.com/live2/KEY1", enabled=True),
            Destination(platform="Facebook", rtmp_url="rtmps://live-api-s.facebook.com:443/rtmp/KEY2", enabled=True),
        ],
        webcam_on=True,
        background_mode="blur",         # "none" | "blur" | "virtual" | "green_screen"
        virtual_bg_path=None,
        background_audio_path="/tmp/bhajan.mp3",  # looping music mixed into the stream
        mic_enabled=True,               # capture real microphone audio
        ticker_text="Breaking news...",
        pip_position="bottom-right",
    )
    start_stream(configs)
    ...
    stop_stream()

NOTE: Running this for real requires `ffmpeg` on PATH plus `opencv-python`
and `mediapipe` installed. Import failures for optional deps (cv2, numpy,
mediapipe, PIL, sounddevice) are handled gracefully so the module can still
be imported (e.g. for unit testing the config/plumbing) on machines that
don't have them installed yet.

--------------------------------------------------------------------------
WHAT CHANGED IN THIS VERSION (found while reviewing the original file)
--------------------------------------------------------------------------
(1) AUDIO WAS ALWAYS SILENT - every push used `anullsrc` (pure silence),
    with no way to send real audio at all. Now there are three audio
    sources, picked automatically from the config:
        - background_audio_path set -> FFmpeg loops that file itself
          (`-stream_loop -1 -i <path>`) - e.g. a bhajan/music track for
          audio-only broadcasts. No Python-side looping needed.
        - mic_enabled=True (and `sounddevice` is installed) -> real
          microphone audio is captured and streamed via a named pipe
          (Unix only - gracefully falls back to silence on Windows or
          when sounddevice isn't installed).
        - neither -> falls back to the original silent `anullsrc`.

(2) ONE FFMPEG PROCESS PER DESTINATION WAS WASTEFUL - the original
    MultiDestinationPublisher spawned a whole separate encoder per
    platform, multiplying CPU usage and making a single shared audio
    source impossible (multiple readers on one pipe corrupt each
    other's stream). This is replaced by TeeFFmpegPublisher: ONE ffmpeg
    process encodes video+audio once and fans out to every enabled
    destination using FFmpeg's `tee` muxer. MultiDestinationPublisher is
    kept as a thin backward-compatible wrapper around it.

(3) TICKER TEXT WAS NOT DEVANAGARI-SAFE - cv2.putText() cannot shape
    Hindi/Devanagari conjuncts/matras at all (same limitation noted in
    engine.py for the main video pipeline). TickerOverlay now pre-renders
    the ticker text once via PIL (+ RAQM when available) into a scrolling
    strip, the same technique engine.py uses for the ticker in the
    generated video, then blends a scrolling window of that strip onto
    each live frame with OpenCV (fast - no per-frame PIL rendering).
--------------------------------------------------------------------------
"""

from __future__ import annotations

import os
import tempfile
import subprocess
import threading
import time
import shutil
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Callable

logger = logging.getLogger("live_engine")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")

# ---------------------------------------------------------------------------
# Optional heavy dependencies (OpenCV / MediaPipe / NumPy / PIL / sounddevice)
# ---------------------------------------------------------------------------
try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None
    logger.warning("OpenCV (cv2) not installed — camera capture / compositing will be unavailable.")

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
    logger.warning("Pillow not installed — Devanagari-safe ticker rendering will be unavailable "
                    "(ticker will be skipped rather than shown broken).")

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover
    sd = None
    logger.warning("sounddevice not installed — mic audio capture will be unavailable "
                    "(mic_enabled will silently fall back to no mic audio).")


_DEVANAGARI_FONT_CANDIDATES = [
    "C:\\Windows\\Fonts\\Nirmala.ttf",
    "C:\\Windows\\Fonts\\Mangal.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # last resort, no Devanagari glyphs
]


# ---------------------------------------------------------------------------
# Configuration data classes
# ---------------------------------------------------------------------------

@dataclass
class Destination:
    """A single RTMP push target."""
    platform: str            # "YouTube" | "Facebook" | "Instagram" | "Custom RTMP"
    rtmp_url: str            # full RTMP URL including stream key
    enabled: bool = True


@dataclass
class StreamConfig:
    """Full configuration bundle handed in from live_app.py."""
    destinations: List[Destination] = field(default_factory=list)
    webcam_on: bool = True
    background_mode: str = "none"          # none | blur | virtual | green_screen
    virtual_bg_path: Optional[str] = None
    background_media_path: Optional[str] = None   # looping VIDEO when webcam is off
    background_audio_path: Optional[str] = None   # looping AUDIO (music/bhajan) mixed in
    mic_enabled: bool = False                      # capture real microphone audio
    ticker_text: str = ""
    pip_position: str = "bottom-right"     # bottom-right | bottom-left | top-right
    width: int = 1280
    height: int = 720
    fps: int = 30


# ---------------------------------------------------------------------------
# (2) SINGLE-ENCODE, MULTI-DESTINATION PUBLISHER (FFmpeg `tee` muxer)
# ---------------------------------------------------------------------------
class TeeFFmpegPublisher:
    """
    Owns ONE FFmpeg subprocess that reads raw BGR video frames from stdin,
    reads audio from whichever source is configured (looping background
    file, live mic, or silence), encodes ONCE, and fans the resulting
    stream out to every enabled destination via the `tee` muxer.

    This replaces spawning one full encoder per destination: cheaper on
    CPU, and it means there is exactly one audio source to manage instead
    of needing to duplicate a live mic feed across N separate processes.
    """

    def __init__(self, config: StreamConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self._mic_thread: Optional[threading.Thread] = None
        self._mic_stop_event = threading.Event()
        self._audio_fifo_path: Optional[str] = None

    # -- audio source selection ------------------------------------------------
    def _build_audio_input_args(self):
        """
        Returns a list of FFmpeg args for the audio INPUT, and sets
        self._audio_fifo_path if a mic FIFO needs to be fed by a
        background thread after the process starts.
        """
        if self.config.background_audio_path and os.path.exists(self.config.background_audio_path):
            logger.info("Audio source: looping background file (%s).", self.config.background_audio_path)
            return ["-stream_loop", "-1", "-i", self.config.background_audio_path]

        if self.config.mic_enabled:
            if sd is None:
                logger.warning("mic_enabled=True lekin sounddevice installed nahi hai - silence use hogi.")
            elif not hasattr(os, "mkfifo"):
                logger.warning("mic_enabled=True lekin is OS par named pipes (mkfifo) support nahi hai "
                                "(Windows?) - silence use hogi.")
            else:
                fifo_path = os.path.join(tempfile.gettempdir(), f"live_mic_{os.getpid()}.pcm")
                try:
                    if os.path.exists(fifo_path):
                        os.remove(fifo_path)
                    os.mkfifo(fifo_path)
                    self._audio_fifo_path = fifo_path
                    logger.info("Audio source: live microphone via FIFO %s.", fifo_path)
                    return ["-f", "s16le", "-ar", "44100", "-ac", "2", "-i", fifo_path]
                except OSError as e:
                    logger.warning("Mic FIFO banane mein fail (%s) - silence use hogi.", e)

        logger.info("Audio source: silence (koi mic/background audio configure nahi kiya gaya).")
        return ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    def _start_mic_feeder(self):
        """Background thread: captures mic audio via sounddevice and writes
        raw PCM into the FIFO that FFmpeg is reading as its audio input."""
        if not self._audio_fifo_path or sd is None:
            return

        def _worker():
            try:
                # Opening the FIFO for writing blocks until FFmpeg opens it
                # for reading (that's how named pipes work) - fine, it's a
                # background thread.
                fifo_fd = open(self._audio_fifo_path, "wb")
            except Exception:
                logger.exception("Mic FIFO open (write mode) fail hui.")
                return

            def _callback(indata, frames, time_info, status):
                if status:
                    logger.debug("sounddevice status: %s", status)
                try:
                    fifo_fd.write(indata.tobytes())
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

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> bool:
        if shutil.which("ffmpeg") is None:
            logger.error("ffmpeg binary PATH par nahi mila - streaming shuru nahi ho sakti.")
            return False

        active = [d for d in self.config.destinations if d.enabled and (d.rtmp_url or "").strip()]
        if not active:
            logger.error("Koi bhi enabled destination ke paas valid RTMP URL nahi hai - kuch bhi push nahi hoga.")
            return False

        audio_args = self._build_audio_input_args()
        tee_targets = "|".join(f"[f=flv]{d.rtmp_url}" for d in active)

        command = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{self.config.width}x{self.config.height}",
            "-r", str(self.config.fps),
            "-i", "-",                 # video frames from stdin
            *audio_args,                # audio: background file loop, mic FIFO, or silence
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-map", "0:v",
            "-map", "1:a",
            "-shortest",
            "-f", "tee",
            tee_targets,
        ]

        logger.info("Single-encode FFmpeg push shuru: %d destination(s) -> %s",
                    len(active), [d.platform for d in active])
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if self._audio_fifo_path:
            self._mic_stop_event.clear()
            self._start_mic_feeder()

        return True

    def write_frame(self, frame_bytes: bytes):
        if self.process is None or self.process.stdin is None:
            return
        try:
            self.process.stdin.write(frame_bytes)
        except (BrokenPipeError, OSError):
            logger.warning("Publisher pipe toot gayi - stream stop kiya ja raha hai.")
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
        logger.info("TeeFFmpegPublisher stopped.")

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def update_destinations(self, destinations: List[Destination]):
        """
        The `tee` target list is fixed at FFmpeg process start, so
        changing destinations means restarting the encoder. This causes
        a brief (sub-second) reconnect glitch on every enabled platform,
        which is an acceptable trade-off for a much cheaper single-encode
        pipeline the rest of the time.
        """
        was_running = self.is_running
        if was_running:
            logger.info("Destinations badal rahe hain - encoder restart ho raha hai.")
            self.stop()
        self.config.destinations = destinations
        if was_running:
            self.start()


# Backward-compatible alias: earlier versions of this module exposed
# MultiDestinationPublisher (one-encoder-per-destination). Keep the name
# importable so any external code doesn't break, but back it with the
# cheaper single-encode implementation.
MultiDestinationPublisher = TeeFFmpegPublisher


# ---------------------------------------------------------------------------
# AI background processing (MediaPipe Selfie Segmentation)
# ---------------------------------------------------------------------------

class BackgroundProcessor:
    """Applies blur / virtual-background / green-screen keying to a webcam frame."""

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
        """Return a processed copy of `frame` according to self.mode."""
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
            green[:] = (0, 255, 0)  # pure green (BGR)
            return np.where(condition, frame, green)

        return frame


# ---------------------------------------------------------------------------
# (3) TICKER OVERLAY — now Devanagari-safe (PIL/RAQM strip, scrolled via numpy)
# ---------------------------------------------------------------------------

class TickerOverlay:
    """
    Renders a horizontally scrolling ticker banner at the bottom of a frame.

    Hindi/Devanagari text is pre-rendered ONCE (whenever the text changes)
    into a wide strip image using PIL (+RAQM shaping when available) - the
    same approach engine.py uses for the generated video's ticker. Each
    live frame then just blends a scrolling window of that pre-rendered
    strip via numpy/OpenCV, which is fast enough for real-time use (no
    per-frame text shaping).
    """

    def __init__(self, text: str = "", speed_px_per_frame: int = 4, bar_height: int = 50,
                canvas_width: int = 1280):
        self.text = text
        self.speed = speed_px_per_frame
        self.bar_height = bar_height
        self.canvas_width = canvas_width
        self._strip = None       # np.ndarray (bar_height, strip_w, 3) BGR, or None
        self._strip_w = 0
        self._scroll_x = 0
        self._rebuild_strip()

    def set_text(self, text: str):
        if text != self.text:
            self.text = text
            self._scroll_x = 0
            self._rebuild_strip()

    @staticmethod
    def _resolve_font(size):
        if ImageFont is None:
            return None
        for path in _DEVANAGARI_FONT_CANDIDATES:
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

    def _rebuild_strip(self):
        self._strip = None
        self._strip_w = 0
        if not self.text or Image is None or np is None:
            return

        font_size = max(14, int(self.bar_height * 0.55))
        font = self._resolve_font(font_size)
        if font is None:
            logger.warning("Koi font resolve nahi hua - ticker skip kiya ja raha hai.")
            return

        spacer = "      •      "
        repeated = (self.text + spacer) * 4

        dummy = Image.new("RGB", (10, 10))
        draw = ImageDraw.Draw(dummy)
        bbox = draw.textbbox((0, 0), repeated, font=font)
        text_w = max(1, bbox[2] - bbox[0])
        strip_w = max(self.canvas_width * 2, text_w + 40)

        img = Image.new("RGB", (strip_w, self.bar_height), (20, 20, 20))
        draw = ImageDraw.Draw(img)
        text_h = bbox[3] - bbox[1]
        y = max(0, (self.bar_height - text_h) // 2)
        draw.text((20, y), repeated, font=font, fill=(255, 255, 255))

        # PIL is RGB, OpenCV frames are BGR.
        self._strip = np.array(img)[:, :, ::-1].copy()
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
        frame[bar_top:bar_top + band_h, 0:w] = cv2.addWeighted(window, 0.85, region, 0.15, 0)
        return frame


# ---------------------------------------------------------------------------
# PIP compositor
# ---------------------------------------------------------------------------

class Compositor:
    """Combines a full-frame background (video loop or virtual backdrop) with a
    smaller webcam feed placed in a corner (Picture-in-Picture)."""

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

    def composite(self, background_frame, webcam_frame=None, pip_scale: float = 0.3):
        """
        background_frame: full-canvas-sized frame (looping video, static image,
                           or black canvas in audio-only mode).
        webcam_frame: optional smaller feed to overlay as PIP. If None, the
                      background frame is returned as-is (audio-only mode).
        """
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

        # Simple border around the PIP window for visual separation.
        cv2.rectangle(canvas, (x - 2, y - 2), (x + pip_w + 2, y + pip_h + 2), (255, 255, 255), 2)
        canvas[y:y + pip_h, x:x + pip_w] = pip_frame
        return canvas


# ---------------------------------------------------------------------------
# Main capture / processing loop
# ---------------------------------------------------------------------------

class LiveStreamEngine:
    """
    Owns the capture -> process -> composite -> publish loop and runs it on
    a background thread so it never blocks the calling UI (live_app.py).
    """

    def __init__(self, config: StreamConfig):
        self.config = config
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self._camera = None
        self._bg_media = None  # looping background video capture, if provided

        self._bg_processor = BackgroundProcessor(config.background_mode, config.virtual_bg_path)
        self._ticker = TickerOverlay(config.ticker_text, canvas_width=config.width)
        self._compositor = Compositor(config.width, config.height, config.pip_position)
        self._publisher = TeeFFmpegPublisher(config)

        self._frames_pushed = 0
        self._start_time: Optional[float] = None
        self.on_status_change: Optional[Callable[[str], None]] = None

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> bool:
        if self._running:
            logger.info("Engine already running.")
            return True
        if cv2 is None or np is None:
            logger.error("OpenCV/NumPy not available — cannot start capture loop.")
            self._notify("error: opencv/numpy missing")
            return False

        if not self._publisher.start():
            logger.error("Publisher start nahi hui (ffmpeg missing ya koi valid destination nahi) - engine start nahi kiya ja raha.")
            self._notify("error: publisher failed to start")
            return False

        if self.config.webcam_on:
            self._camera = cv2.VideoCapture(0)
            self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
            self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
            if not self._camera.isOpened():
                logger.warning("Webcam open nahi hui - audio-only/blank-visual mode mein chalu rahega.")

        if self.config.background_media_path:
            self._bg_media = cv2.VideoCapture(self.config.background_media_path)

        self._running = True
        self._frames_pushed = 0
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._run_loop, name="LiveStreamEngineLoop", daemon=True)
        self._thread.start()
        self._notify("live")
        logger.info("Live stream engine started.")
        return True

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

        if self._camera is not None:
            self._camera.release()
            self._camera = None

        if self._bg_media is not None:
            self._bg_media.release()
            self._bg_media = None

        self._publisher.stop()
        self._notify("stopped")
        logger.info("Live stream engine stopped. Frames pushed: %d", self._frames_pushed)

    def _notify(self, status: str):
        if self.on_status_change:
            try:
                self.on_status_change(status)
            except Exception:
                logger.exception("on_status_change callback raised.")

    # -- status ---------------------------------------------------------------

    def get_status(self) -> dict:
        uptime = (time.time() - self._start_time) if (self._running and self._start_time) else 0
        return {
            "running": self._running,
            "publisher_alive": self._publisher.is_running,
            "frames_pushed": self._frames_pushed,
            "uptime_sec": round(uptime, 1),
            "webcam_active": self._camera is not None and self._camera.isOpened() if self._camera else False,
        }

    # -- dynamic updates (called live from the UI) ---------------------------

    def update_ticker(self, text: str):
        self._ticker.set_text(text)

    def update_background_mode(self, mode: str, virtual_bg_path: Optional[str] = None):
        self._bg_processor.set_mode(mode, virtual_bg_path)

    def update_pip_position(self, position: str):
        self._compositor.set_position(position)

    def update_destinations(self, destinations: List[Destination]):
        """Enable/disable individual platforms (YouTube/Facebook/Instagram) live.
        Note: this briefly restarts the encoder (see TeeFFmpegPublisher.update_destinations)."""
        self._publisher.update_destinations(destinations)

    # -- internals ------------------------------------------------------------

    def _next_background_frame(self):
        """Fetch the next frame of the looping background media, image, or a blank canvas."""
        blank = np.zeros((self.config.height, self.config.width, 3), dtype="uint8")

        if self._bg_media is not None:
            ok, frame = self._bg_media.read()
            if not ok:  # loop back to start
                self._bg_media.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self._bg_media.read()
            return frame if ok else blank

        return blank

    def _run_loop(self):
        frame_interval = 1.0 / max(self.config.fps, 1)

        while self._running:
            loop_start = time.time()

            webcam_frame = None
            if self.config.webcam_on and self._camera is not None and self._camera.isOpened():
                ok, raw = self._camera.read()
                if ok:
                    webcam_frame = self._bg_processor.process(raw)

            background_frame = self._next_background_frame()
            composited = self._compositor.composite(background_frame, webcam_frame)
            final_frame = self._ticker.apply(composited)

            self._publisher.write_frame(final_frame.tobytes())
            self._frames_pushed += 1

            elapsed = time.time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Module-level singleton API — what live_app.py actually calls
# ---------------------------------------------------------------------------

_engine: Optional[LiveStreamEngine] = None
_engine_lock = threading.Lock()


def start_stream(stream_configs: StreamConfig) -> bool:
    """
    Start (or restart) the live stream engine with the given configuration.
    Non-blocking — returns immediately once the background thread is launched.
    Returns True if the engine was started, False if one was already running
    or if startup failed (e.g. ffmpeg missing, no valid destination).
    """
    global _engine
    with _engine_lock:
        if _engine is not None:
            logger.warning("A stream is already running. Call stop_stream() first.")
            return False
        engine = LiveStreamEngine(stream_configs)
        if not engine.start():
            return False
        _engine = engine
        return True


def stop_stream() -> bool:
    """Stop the currently-running stream engine, if any."""
    global _engine
    with _engine_lock:
        if _engine is None:
            logger.info("No active stream to stop.")
            return False
        _engine.stop()
        _engine = None
        return True


def update_live_ticker(text: str):
    """Update the scrolling ticker text on an already-running stream."""
    if _engine is not None:
        _engine.update_ticker(text)


def update_live_destinations(destinations: List[Destination]):
    """Enable/disable individual platform destinations on an already-running stream."""
    if _engine is not None:
        _engine.update_destinations(destinations)


def update_live_background(mode: str, virtual_bg_path: Optional[str] = None):
    """Change AI background mode (none/blur/virtual/green_screen) live."""
    if _engine is not None:
        _engine.update_background_mode(mode, virtual_bg_path)


def get_stream_status() -> Optional[dict]:
    """Returns a status dict (running/frames_pushed/uptime/...) or None if offline."""
    if _engine is not None:
        return _engine.get_status()
    return None


def is_streaming() -> bool:
    return _engine is not None


def check_ffmpeg_available() -> bool:
    """Quick pre-flight check the UI can call before even trying to start."""
    return shutil.which("ffmpeg") is not None


# ---------------------------------------------------------------------------
# Manual smoke test (does not require a real camera or ffmpeg to import)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    demo_config = StreamConfig(
        destinations=[
            Destination(platform="YouTube", rtmp_url="rtmp://a.rtmp.youtube.com/live2/REPLACE_ME", enabled=True),
            Destination(platform="Facebook", rtmp_url="rtmps://live-api-s.facebook.com:443/rtmp/REPLACE_ME", enabled=False),
        ],
        webcam_on=True,
        background_mode="blur",
        ticker_text="This is a live demo ticker...",
        pip_position="bottom-right",
    )
    print("StreamConfig built successfully:", demo_config)
    print("ffmpeg available:", check_ffmpeg_available())
    print("Run start_stream(demo_config) with real RTMP keys, a webcam, and ffmpeg installed to go live.")
