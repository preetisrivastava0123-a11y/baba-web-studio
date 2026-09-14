"""
==============================================================
Baba Generative Web Studio -- engine.py (MoviePy 2.x safe version)
==============================================================
Core video compiler engine. Wires together voice.py, subtitle.py,
climax.py and the 4-track / live-loop UI data from app.py into a
single final video.

Fixed in this pass:
  1. All indentation is now strict 4 spaces, no tabs.
  2. Removed the duplicate `compile_cinematic_video` definition and the
     dead/unreachable code that used to sit after a `return`.
  3. `_compile_standard_mode` no longer has code accidentally sitting at
     module level (that was the root cause of the "return outside
     function" / "unexpected indent" errors) and now always returns,
     whether or not `outro_voice_active` is True.
  4. `_loop_audio_clip` was defined but called as
     `_loop_audio_clip_to_duration` elsewhere -- renamed consistently
     to `_loop_audio_clip_to_duration` everywhere, and `numpy` is now
     actually imported (it's used for `np.ceil`).
  5. All Hindi explanatory text that used to live inside function
     bodies as stray multi-line docstrings has been converted to
     single-line `#` comments so nothing can break the parser.
  6. `create_climax_layer(...)` is called with ONE consistent
     signature everywhere: it returns `(clip_layers, climax_duration_used)`
     and accepts `climax_duration_override`. This matches the CTA-voice
     addition further down the file (see ASSUMPTIONS below).
  7. `compile_cinematic_video` now actually calls `write_videofile()`
     and cleans up temp PNGs (that code used to sit unreachable after
     a `return`, referencing variables that didn't exist in scope).

ASSUMPTIONS (real files not available while patching this):
  - voice.py:    create_baba_audio(script_text, output_path=None) -> str
  - subtitle.py: render_subtitle_html_to_png(text_string, output_image_path,
                 canvas_width, text_color=None, font_size=None) -> str
  - climax.py:   create_climax_layer(video_duration, outro_text, aspect_ratio,
                 climax_duration_override=None) -> (list_of_clips, climax_duration_used)
                 Also exports: SUBSCRIBE_MESSAGE (str), CLIMAX_DURATION_SECONDS (float)
  - A default background music file "sitar_vadand_sfx.mp3" exists in the
    project root.
  - MoviePy 2.x: `from moviepy import vfx`, `clip.with_effects([vfx.CrossFadeIn(d)])`,
    `clip.with_volume_scaled(factor)`.

If your real function/file names differ, only the IMPORT/CONSTANT block
below needs to change -- the rest of the structure stays the same.
==============================================================
"""

# --------------------------------------------------------------
# Imports
# --------------------------------------------------------------
import os

import numpy as np
import moviepy.vfx as vfx
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_audioclips,
    concatenate_videoclips,
)

from voice import create_baba_audio
from subtitle import render_subtitle_html_to_png
from climax import create_climax_layer, SUBSCRIBE_MESSAGE, CLIMAX_DURATION_SECONDS


# --------------------------------------------------------------
# Constants
# --------------------------------------------------------------
SUBTITLE_TEMP_PNG = "temp_subtitle_overlay.png"
TICKER_TEMP_PNG = "temp_ticker_overlay.png"
CTA_TEMP_VOICE_MP3 = "temp_cta_voice.mp3"
SITAR_BACKGROUND_MUSIC_PATH = "sitar_vadand_sfx.mp3"

RENDER_FPS = 24
RENDER_THREADS = 8
RENDER_PRESET = "ultrafast"

# --- "virality" tuning ---
KEN_BURNS_ZOOM_RATE = 0.06
CROSSFADE_DURATION_SECONDS = 0.6
SHORTS_SLOT_SECONDS = 4
LONG_VIDEO_SLOT_SECONDS = 10
LIVE_LOOP_IMAGE_SLOT_SECONDS = 5.0

# --- news-ticker / outro scroller (live_loop mode only) ---
TICKER_SCROLL_SPEED_PX_PER_SEC = 220
TICKER_BANNER_WIDTH_MULTIPLIER = 2.2
TICKER_BOTTOM_MARGIN_PX = 40


# ================================================================
# 1. Export settings resolver
# ================================================================
def _resolve_export_settings(aspect_ratio: str = "9:16", quality: str = "1080p") -> tuple:
    # 16:9 landscape (YouTube long-form)
    if aspect_ratio == "16:9":
        target_width, target_height = (1920, 1080) if quality == "1080p" else (1280, 720)
    # 9:16 portrait (Shorts / Reels) default
    else:
        target_width, target_height = (1080, 1920) if quality == "1080p" else (720, 1280)

    export_bitrate = "8000k" if quality == "1080p" else "4000k"

    return target_width, target_height, export_bitrate


# ================================================================
# 2. Audio loop helper
# ================================================================
def _loop_audio_clip_to_duration(audio_clip, target_duration: float):
    if audio_clip is None or target_duration <= 0:
        return None

    if audio_clip.duration >= target_duration:
        return audio_clip.with_duration(target_duration)

    loop_count = int(np.ceil(target_duration / audio_clip.duration))
    repeated_clips = [audio_clip] * loop_count
    looped_clip = concatenate_audioclips(repeated_clips)

    return looped_clip.with_duration(target_duration)


# --------------------------------------------------------------
# 3) Voiceover -- AI TTS or a custom uploaded audio file
# --------------------------------------------------------------
def _build_voice_or_silence_audio(script_text, voiceover_mode, custom_audio_path):
    # Generates a voiceover clip. Returns (None, 0.0) safely if there's no text/audio.
    try:
        if custom_audio_path and os.path.exists(custom_audio_path):
            audio_clip = AudioFileClip(custom_audio_path)
            return audio_clip, audio_clip.duration

        if script_text and script_text.strip():
            voice_file = create_baba_audio(script_text)
            if voice_file and os.path.exists(voice_file):
                audio_clip = AudioFileClip(voice_file)
                return audio_clip, audio_clip.duration

        return None, 0.0
    except Exception as e:
        print(f"Voice generation note: {e}")
        return None, 0.0


# --------------------------------------------------------------
# 4) Fit a clip to the target canvas (crop-to-fill), shared helper
# --------------------------------------------------------------
def _fit_clip_to_canvas(raw_clip, target_width: int, target_height: int):
    # Scales the larger edge first, then center-crops to the exact target
    # size, so the original aspect ratio is preserved while filling the frame.
    original_width, original_height = raw_clip.size
    target_aspect_ratio = target_width / target_height
    original_aspect_ratio = original_width / original_height

    if original_aspect_ratio > target_aspect_ratio:
        resized_clip = raw_clip.resized(height=target_height)
    else:
        resized_clip = raw_clip.resized(width=target_width)

    cropped_clip = resized_clip.cropped(
        x_center=resized_clip.w / 2,
        y_center=resized_clip.h / 2,
        width=target_width,
        height=target_height,
    )
    return cropped_clip


# ================================================================
# Standard studio mode (mode == "standard") helpers
# ================================================================

# --------------------------------------------------------------
# 5a) Track 1 (warehouse) main background visual track
# --------------------------------------------------------------
def _load_single_visual_clip_track1(item: dict, target_width: int, target_height: int, remaining_duration: float):
    # Prepares one Track 1 item {"path","is_image","start","end"} for its own
    # "natural" slot length:
    #   image: item["end"] (default 5s), with a Ken Burns zoom-in
    #   video: its own full length (item["end"]==0.0 means "whole clip") --
    #          never looped/stretched, only trimmed to the remaining duration
    if item["is_image"]:
        slot_duration = min(item["end"] if item["end"] > 0 else 5.0, remaining_duration)
        raw_clip = ImageClip(item["path"]).with_duration(slot_duration)
    else:
        raw_clip = VideoFileClip(item["path"])
        slot_duration = min(raw_clip.duration, remaining_duration)
        raw_clip = raw_clip.subclipped(0, slot_duration)

    prepared_clip = _fit_clip_to_canvas(raw_clip, target_width, target_height)

    if item["is_image"]:
        prepared_clip = prepared_clip.resized(
            lambda t: 1 + KEN_BURNS_ZOOM_RATE * (t / max(slot_duration, 0.001))
        )

    return prepared_clip, slot_duration


def _build_track1_looped_visual_track(visual_clips: list, total_duration: float, target_width: int, target_height: int):
    # Joins Track 1 (warehouse) items in order; once the list runs out it
    # cycles back to the first file, until total_duration is filled. Every
    # cut is joined with a crossfade.
    if not visual_clips:
        raise ValueError("At least one Track 1 visual is required.")

    visual_clips_sequence = []
    elapsed_duration = 0.0
    cycle_index = 0
    total_items = len(visual_clips)

    while elapsed_duration < total_duration - 0.01:
        item = visual_clips[cycle_index % total_items]
        remaining_duration = total_duration - elapsed_duration
        prepared_clip, slot_duration = _load_single_visual_clip_track1(
            item, target_width, target_height, remaining_duration,
        )
        if slot_duration <= 0:
            break

        if visual_clips_sequence:
            prepared_clip = prepared_clip.with_effects([vfx.CrossFadeIn(CROSSFADE_DURATION_SECONDS)])

        visual_clips_sequence.append(prepared_clip)
        elapsed_duration += slot_duration
        cycle_index += 1

    combined_visual_track = concatenate_videoclips(
        visual_clips_sequence, method="compose", padding=-CROSSFADE_DURATION_SECONDS,
    )

    # Safety net: Ken Burns zoom can push the frame slightly outside the
    # canvas, so re-crop to the exact target size at the end so later
    # subtitle/climax layers always match.
    combined_visual_track = combined_visual_track.cropped(
        x_center=combined_visual_track.w / 2,
        y_center=combined_visual_track.h / 2,
        width=target_width,
        height=target_height,
    ).with_duration(total_duration)

    return combined_visual_track


# --------------------------------------------------------------
# 5b) Track 2 -- video clip timeline: each clip overlays at its own start/end
# --------------------------------------------------------------
def _build_track2_overlay_clips(video_clips_timeline: list, target_width: int, target_height: int):
    # Turns each Track 2 item {"path","start","end"} into an independent
    # overlay clip that appears at its own Start Second and disappears at
    # its End Second -- these composite on top of the Track 1 background.
    overlay_clips = []
    for item in video_clips_timeline:
        raw_clip = VideoFileClip(item["path"])
        start_time = max(item["start"], 0.0)
        window_duration = item["end"] - start_time if item["end"] > start_time else raw_clip.duration
        window_duration = min(window_duration, raw_clip.duration)
        if window_duration <= 0:
            continue

        trimmed_clip = raw_clip.subclipped(0, window_duration)
        prepared_clip = _fit_clip_to_canvas(trimmed_clip, target_width, target_height)
        prepared_clip = prepared_clip.with_start(start_time)
        overlay_clips.append(prepared_clip)

    return overlay_clips


# --------------------------------------------------------------
# 5c) Music layer -- Track 4 (time-synced clips) takes priority, then
#     Track 3 (warehouse), then the default sitar background music
# --------------------------------------------------------------
def _build_music_layer_for_standard_mode(music_clips_timeline: list, music_files_pool: list, master_music_volume: float, total_video_duration: float):
    layered_music_clips = []

    if music_clips_timeline:
        # Track 4: each clip starts at its own Start Second. "order" is only
        # for the user's own understanding/ordering -- all layers mix together anyway.
        for music_item in sorted(music_clips_timeline, key=lambda m: m["order"]):
            raw_clip = AudioFileClip(music_item["path"])
            segment_start = max(music_item["start"], 0.0)
            segment_duration = music_item["end"] - segment_start if music_item["end"] > segment_start else raw_clip.duration
            segment_duration = min(segment_duration, raw_clip.duration)
            if segment_duration <= 0:
                continue
            trimmed_clip = raw_clip.subclipped(0, segment_duration).with_start(segment_start)
            layered_music_clips.append(trimmed_clip)

    elif music_files_pool:
        # No time-synced music clips given -- join Track 3 (warehouse) tracks
        # in order and loop them across the full video length.
        pool_clips = [AudioFileClip(path) for path in music_files_pool]
        concatenated_pool_clip = concatenate_audioclips(pool_clips)
        looped_pool_clip = _loop_audio_clip_to_duration(concatenated_pool_clip, total_video_duration)
        layered_music_clips.append(looped_pool_clip)

    else:
        # Nothing uploaded -- fall back to the default sitar background music.
        sitar_bg_clip = AudioFileClip(SITAR_BACKGROUND_MUSIC_PATH)
        looped_sitar_clip = _loop_audio_clip_to_duration(sitar_bg_clip, total_video_duration)
        layered_music_clips.append(looped_sitar_clip)

    if not layered_music_clips:
        return None

    combined_music_layer = CompositeAudioClip(layered_music_clips).with_duration(total_video_duration)
    return combined_music_layer.with_volume_scaled(master_music_volume)


# --------------------------------------------------------------
# 5d) SFX layer -- conch/damru etc events, each at its own start/end
# --------------------------------------------------------------
def _build_sfx_layer(sfx_events: list, total_video_duration: float):
    sfx_audio_clips = []
    for sfx_item in sfx_events:
        if not sfx_item.get("path"):
            # Built-in preset sound (e.g. "Shankhnaad") isn't a real file yet --
            # TODO: add a preset-sound library and map it by sfx_name.
            continue
        raw_sfx_clip = AudioFileClip(sfx_item["path"])
        sfx_start = max(sfx_item["start"], 0.0)
        sfx_duration = sfx_item["end"] - sfx_start if sfx_item["end"] > sfx_start else raw_sfx_clip.duration
        sfx_duration = min(sfx_duration, raw_sfx_clip.duration)
        if sfx_duration <= 0:
            continue
        trimmed_sfx_clip = (
            raw_sfx_clip.subclipped(0, sfx_duration)
            .with_start(sfx_start)
            .with_volume_scaled(sfx_item["volume"])
        )
        sfx_audio_clips.append(trimmed_sfx_clip)

    if not sfx_audio_clips:
        return None
    return CompositeAudioClip(sfx_audio_clips).with_duration(total_video_duration)


def _combine_all_audio_layers(voice_clip, music_layer, sfx_layer, total_video_duration: float):
    active_layers = [layer for layer in (voice_clip, music_layer, sfx_layer) if layer is not None]
    if not active_layers:
        return None
    return CompositeAudioClip(active_layers).with_duration(total_video_duration)


# --------------------------------------------------------------
# 5e) Hindi subtitle overlay layer (via subtitle.py)
# --------------------------------------------------------------
def _build_subtitle_overlay_clip(script_text: str, video_duration: float, canvas_width: int, text_color: str, font_size_px: int):
    # Renders a transparent PNG via subtitle.py (Playwright) and overlays it
    # at the bottom of the screen. If script_text is empty (e.g. live_loop
    # mode), no subtitle is shown -- returns None.
    if not script_text or not script_text.strip():
        return None

    rendered_subtitle_png_path = render_subtitle_html_to_png(
        text_string=script_text,
        output_image_path=SUBTITLE_TEMP_PNG,
        canvas_width=canvas_width,
        text_color=text_color,
        # subtitle.py's real parameter name is "font_size", not "font_size_px" --
        # forward our internal font_size_px value under the correct name.
        font_size=font_size_px,
    )

    subtitle_clip = (
        ImageClip(rendered_subtitle_png_path)
        .with_duration(video_duration)
        # MoviePy 2.x wants with_position() to get a LIST [x, y], not a tuple.
        .with_position(["center", "bottom"])
    )
    return subtitle_clip


# --------------------------------------------------------------
# 5f) CTA voice + hard-cut ducking (used by the climax step below)
# --------------------------------------------------------------
def _build_cta_voice_audio(outro_text: str) -> tuple:
    # Builds the real spoken CTA audio via voice.py's create_baba_audio():
    # "Channel ko like, subscribe karein" + the user's outro_text together.
    # Never crashes -- returns (None, 0.0) on any failure so the rest of the
    # video can still render (visual-only climax, no CTA voice).
    cta_spoken_text = SUBSCRIBE_MESSAGE
    if outro_text and outro_text.strip():
        cta_spoken_text = f"{SUBSCRIBE_MESSAGE}. {outro_text.strip()}"

    try:
        cta_audio_path = create_baba_audio(cta_spoken_text, CTA_TEMP_VOICE_MP3)
        cta_audio_clip = AudioFileClip(cta_audio_path)
        return cta_audio_clip, cta_audio_clip.duration
    except Exception as cta_voice_error:
        print(f"[auto-skip] Could not build CTA voice -- climax will be visual-only: {cta_voice_error}")
        return None, 0.0


def _duck_audio_hard_cut(background_audio_clip, duck_start_time: float, total_duration: float, duck_volume: float = 0.5):
    # Hard-cut ducking: split the background audio in two and change volume
    # directly -- no fade-in/out effect chain. Stacking a fade AND a volume
    # change at the same time makes the transition sound "warped"; a clean
    # hard-cut is the standard broadcast/YouTube approach.
    if background_audio_clip is None:
        return None
    if duck_start_time <= 0 or duck_start_time >= background_audio_clip.duration:
        return background_audio_clip

    try:
        main_part = background_audio_clip.subclipped(0, duck_start_time).with_volume_scaled(1.0)
        end_part = background_audio_clip.subclipped(
            duck_start_time, min(background_audio_clip.duration, total_duration)
        ).with_volume_scaled(duck_volume)
        return concatenate_audioclips([main_part, end_part])
    except Exception as duck_error:
        print(f"[auto-skip] CTA ducking failed, background music stays at normal volume: {duck_error}")
        return background_audio_clip


def _build_climax_with_cta_voice(
    total_video_duration: float,
    outro_text: str,
    aspect_ratio: str,
    outro_voice_active: bool,
    combined_audio,
):
    # Builds the visual climax layers AND the CTA voice, plus hard-cut
    # ducking of the background audio during the CTA window. Returns
    # (climax_visual_layers, final_combined_audio, total_video_duration_updated)
    # -- the updated duration may grow if the CTA voice runs long, so a long
    # CTA line never gets cut off at the end of the video.
    if not outro_voice_active:
        return [], combined_audio, total_video_duration

    # Step A: build the real spoken CTA audio and measure its real duration.
    cta_audio_clip, cta_audio_duration = _build_cta_voice_audio(outro_text)

    # Step B: decide climax_duration -- default 5.5s, or as long as the CTA voice needs.
    required_climax_duration = max(CLIMAX_DURATION_SECONDS, cta_audio_duration + 0.4)

    # Step C: if the CTA voice made climax_duration grow, grow the whole
    # video length too so nothing gets cut off mid-line.
    total_video_duration_updated = max(total_video_duration, required_climax_duration + 1.0)

    # Step D: visual climax layers (feathers + particle blast + text).
    climax_visual_layers, climax_duration_used = create_climax_layer(
        video_duration=total_video_duration_updated,
        outro_text=outro_text,
        aspect_ratio=aspect_ratio,
        climax_duration_override=required_climax_duration,
    )
    climax_start_time = total_video_duration_updated - climax_duration_used

    # Step E: hard-cut duck the background audio during the CTA window.
    final_combined_audio = _duck_audio_hard_cut(
        combined_audio, climax_start_time, total_video_duration_updated, duck_volume=0.5,
    )

    # Step F: mix the real CTA voice in at the right time.
    if cta_audio_clip is not None:
        cta_audio_clip = cta_audio_clip.with_start(climax_start_time)
        if final_combined_audio is not None:
            final_combined_audio = CompositeAudioClip(
                [final_combined_audio, cta_audio_clip]
            ).with_duration(total_video_duration_updated)
        else:
            final_combined_audio = cta_audio_clip

    return climax_visual_layers, final_combined_audio, total_video_duration_updated


# --------------------------------------------------------------
# 5g) Only keep real MoviePy clip objects out of a nested list/tuple
# --------------------------------------------------------------
def _extract_only_clips(element, flat_layers):
    if isinstance(element, (list, tuple)):
        for sub_element in element:
            _extract_only_clips(sub_element, flat_layers)
    elif element is not None and hasattr(element, "duration"):
        flat_layers.append(element)


# --------------------------------------------------------------
# 5h) Full standard-mode compiler
# --------------------------------------------------------------
def _compile_standard_mode(
    visual_clips, video_clips_timeline, music_files_pool, music_clips_timeline,
    master_music_volume, sfx_events, script_text, outro_text, aspect_ratio,
    duration_seconds, target_width, target_height, sub_color, sub_size,
    voiceover_mode, custom_audio_path, outro_voice_active,
):
    # Step 1: voiceover
    voice_clip, voice_duration = _build_voice_or_silence_audio(script_text, voiceover_mode, custom_audio_path)

    # Step 2: decide total video length
    total_images = len(visual_clips) if visual_clips else 1
    min_visuals_time = total_images * 5.0

    if duration_seconds and float(duration_seconds) > 0:
        total_video_duration = float(duration_seconds)
    elif voice_duration > 0:
        total_video_duration = max(voice_duration, min_visuals_time)
    else:
        total_video_duration = max(min_visuals_time, 30.0)

    # Step 3: Track 1 (warehouse) main background visual track
    background_visual_track = _build_track1_looped_visual_track(
        visual_clips=visual_clips, total_duration=total_video_duration,
        target_width=target_width, target_height=target_height,
    )

    # Step 4: Track 2 overlay clips at their own start/end seconds
    track2_overlay_clips = _build_track2_overlay_clips(video_clips_timeline, target_width, target_height)

    # Step 5: audio -- music (Track 3/4) + SFX + voice, all mixed
    music_layer = _build_music_layer_for_standard_mode(
        music_clips_timeline, music_files_pool, master_music_volume, total_video_duration,
    )
    sfx_layer = _build_sfx_layer(sfx_events, total_video_duration)
    combined_audio = _combine_all_audio_layers(voice_clip, music_layer, sfx_layer, total_video_duration)

    # Step 6: Hindi subtitle overlay
    subtitle_overlay_clip = _build_subtitle_overlay_clip(
        script_text=script_text, video_duration=total_video_duration,
        canvas_width=target_width, text_color=sub_color, font_size_px=sub_size,
    )

    # Step 7: climax visual layers + AI outro/CTA voice + hard-cut ducking.
    # This also may grow total_video_duration if the CTA voice runs long.
    climax_layers, combined_audio, total_video_duration = _build_climax_with_cta_voice(
        total_video_duration=total_video_duration,
        outro_text=outro_text,
        aspect_ratio=aspect_ratio,
        outro_voice_active=outro_voice_active,
        combined_audio=combined_audio,
    )

    if combined_audio is not None:
        background_visual_track = background_visual_track.with_duration(total_video_duration).with_audio(combined_audio)
    else:
        background_visual_track = background_visual_track.with_duration(total_video_duration)

    # Step 8: flatten every layer into real MoviePy clip objects only
    raw_layers = [background_visual_track]
    for layer_item in (track2_overlay_clips, subtitle_overlay_clip, climax_layers):
        if layer_item is not None:
            raw_layers.append(layer_item)

    flat_layers = []
    for item in raw_layers:
        _extract_only_clips(item, flat_layers)

    final_composed_video = CompositeVideoClip(
        flat_layers, size=(target_width, target_height)
    ).with_duration(total_video_duration)

    return final_composed_video, total_video_duration


# ================================================================
# Live loop studio mode (mode == "live_loop") helpers
# ================================================================
def _load_single_visual_clip_live_loop(media_item: dict, target_width: int, target_height: int, remaining_duration: float, style_variant_index: int):
    # Live loop mode gives each slot a different cinematic style in turn so a
    # long repeating video doesn't feel boring:
    #   0 -> zoom-in (Ken Burns) + crossfade into next clip
    #   1 -> slight zoom-out, hard-cut (no crossfade)
    #   2 -> zoom-in (heavier crossfade)
    #   3 -> static frame (no zoom), hard-cut
    if media_item["is_image"]:
        slot_duration = min(LIVE_LOOP_IMAGE_SLOT_SECONDS, remaining_duration)
        raw_clip = ImageClip(media_item["path"]).with_duration(slot_duration)
    else:
        raw_clip = VideoFileClip(media_item["path"])
        slot_duration = min(raw_clip.duration, remaining_duration)
        raw_clip = raw_clip.subclipped(0, slot_duration)

    prepared_clip = _fit_clip_to_canvas(raw_clip, target_width, target_height)

    if media_item["is_image"] and style_variant_index == 1:
        prepared_clip = prepared_clip.resized(
            lambda t: (1 + KEN_BURNS_ZOOM_RATE) - KEN_BURNS_ZOOM_RATE * (t / max(slot_duration, 0.001))
        )
    elif media_item["is_image"] and style_variant_index in (0, 2):
        prepared_clip = prepared_clip.resized(
            lambda t: 1 + KEN_BURNS_ZOOM_RATE * (t / max(slot_duration, 0.001))
        )
    # style_variant_index == 3 (or a video item): no zoom, static/natural frame.

    return prepared_clip, slot_duration


def _build_live_loop_visual_track(visual_clips: list, video_clips_timeline: list, total_duration: float, target_width: int, target_height: int):
    # Track 1 (warehouse) + Track 2 (timeline slots -- here only used as a
    # media source, their own start/end aren't used in this mode) are merged
    # into a shared pool, then a while-loop cycles through it -- each time
    # with a different style -- until total_duration is filled.
    combined_media_pool = [
        {"path": item["path"], "is_image": item["is_image"]} for item in visual_clips
    ] + [
        {"path": item["path"], "is_image": False} for item in video_clips_timeline
    ]

    if not combined_media_pool:
        raise ValueError("Live loop mode needs at least one Track 1 visual or Track 2 video clip.")

    visual_clips_sequence = []
    elapsed_duration = 0.0
    cycle_index = 0
    total_items = len(combined_media_pool)

    while elapsed_duration < total_duration - 0.01:
        media_item = combined_media_pool[cycle_index % total_items]
        remaining_duration = total_duration - elapsed_duration
        style_variant_index = cycle_index % 4

        prepared_clip, slot_duration = _load_single_visual_clip_live_loop(
            media_item, target_width, target_height, remaining_duration, style_variant_index,
        )
        if slot_duration <= 0:
            break

        use_crossfade = style_variant_index in (0, 2)
        if visual_clips_sequence and use_crossfade:
            prepared_clip = prepared_clip.with_effects([vfx.CrossFadeIn(CROSSFADE_DURATION_SECONDS)])

        visual_clips_sequence.append(prepared_clip)
        elapsed_duration += slot_duration
        cycle_index += 1

    combined_visual_track = concatenate_videoclips(
        visual_clips_sequence, method="compose", padding=-CROSSFADE_DURATION_SECONDS,
    )
    combined_visual_track = combined_visual_track.cropped(
        x_center=combined_visual_track.w / 2,
        y_center=combined_visual_track.h / 2,
        width=target_width,
        height=target_height,
    ).with_duration(total_duration)

    return combined_visual_track


def _build_scrolling_ticker_overlay_clip(outro_text: str, video_duration: float, canvas_width: int, canvas_height: int):
    # Renders the news-ticker/outro text into a wide transparent banner PNG,
    # then scrolls it right-to-left across the whole video, looping
    # continuously (a "scrolling timeline loop").
    if not outro_text or not outro_text.strip():
        return None

    banner_width = int(canvas_width * TICKER_BANNER_WIDTH_MULTIPLIER)
    ticker_png_path = render_subtitle_html_to_png(
        text_string=outro_text,
        output_image_path=TICKER_TEMP_PNG,
        canvas_width=banner_width,
    )

    ticker_image_clip = ImageClip(ticker_png_path).with_duration(video_duration)
    banner_height = ticker_image_clip.h
    ticker_y_position = canvas_height - banner_height - TICKER_BOTTOM_MARGIN_PX
    cycle_distance = banner_width + canvas_width

    def _ticker_x_position(t):
        traveled_distance = (t * TICKER_SCROLL_SPEED_PX_PER_SEC) % cycle_distance
        return canvas_width - traveled_distance

    # MoviePy 2.x wants with_position() to get a LIST [x, y] even from a lambda.
    return ticker_image_clip.with_position(lambda t: [_ticker_x_position(t), ticker_y_position])


def _compile_live_loop_mode(
    visual_clips, video_clips_timeline, outro_text, duration_seconds,
    target_width, target_height, master_music_volume, outro_voice_active, aspect_ratio,
):
    if not duration_seconds:
        raise ValueError("Live loop mode requires duration_seconds to be given.")
    total_video_duration = float(duration_seconds)

    # Step 1: merge Track 1 + Track 2 into the while-loop, cycle by cycle.
    background_visual_track = _build_live_loop_visual_track(
        visual_clips=visual_clips, video_clips_timeline=video_clips_timeline,
        total_duration=total_video_duration, target_width=target_width, target_height=target_height,
    )

    # Step 2: background audio -- this mode has no separate music/SFX
    # tracks, so the default sitar music loops across the full duration.
    sitar_bg_clip = AudioFileClip(SITAR_BACKGROUND_MUSIC_PATH)
    looped_bg_audio = _loop_audio_clip_to_duration(sitar_bg_clip, total_video_duration)
    looped_bg_audio = looped_bg_audio.with_volume_scaled(master_music_volume)
    background_visual_track = background_visual_track.with_audio(looped_bg_audio)

    # Step 3: news-ticker/outro -- scrolls continuously across the whole video.
    scrolling_ticker_clip = _build_scrolling_ticker_overlay_clip(
        outro_text=outro_text, video_duration=total_video_duration,
        canvas_width=target_width, canvas_height=target_height,
    )

    # Step 4: climax layers -- feathers always in the last ~5.5s (even in long loop videos).
    if outro_voice_active:
        climax_layers, climax_duration_used = create_climax_layer(
            video_duration=total_video_duration, outro_text=outro_text, aspect_ratio=aspect_ratio,
        )
    else:
        climax_layers = []

    all_layers = [background_visual_track]
    if scrolling_ticker_clip is not None:
        all_layers.append(scrolling_ticker_clip)

    flat_climax_layers = []
    _extract_only_clips(climax_layers, flat_climax_layers)
    all_layers.extend(flat_climax_layers)

    final_composed_video = CompositeVideoClip(
        all_layers, size=(target_width, target_height),
    ).with_duration(total_video_duration)

    return final_composed_video, total_video_duration


# ================================================================
# 6. Main entry function -- called from app.py
# ================================================================
def compile_cinematic_video(
    mode="standard",
    visual_clips=None,
    video_clips_timeline=None,
    music_files_pool=None,
    music_clips_timeline=None,
    master_music_volume=0.3,
    sfx_events=None,
    script_text="",
    outro_text="",
    aspect_ratio="9:16",
    duration_seconds=None,
    quality="1080p",
    sub_color="yellow",
    sub_size=40,
    voiceover_mode="hi-IN-SwaraNeural",
    custom_audio_path=None,
    outro_voice_active=True,
    output_video_path="final_output.mp4",
    **kwargs,
):
    # 1. Resolve canvas size + bitrate for the chosen aspect ratio/quality.
    target_width, target_height, export_bitrate = _resolve_export_settings(aspect_ratio, quality)

    # 2. Call the right compiler for the chosen mode.
    if mode == "live_loop":
        final_composed_video, total_video_duration = _compile_live_loop_mode(
            visual_clips=visual_clips or [],
            video_clips_timeline=video_clips_timeline or [],
            outro_text=outro_text,
            duration_seconds=duration_seconds,
            target_width=target_width,
            target_height=target_height,
            master_music_volume=master_music_volume,
            outro_voice_active=outro_voice_active,
            aspect_ratio=aspect_ratio,
        )
    else:
        final_composed_video, total_video_duration = _compile_standard_mode(
            visual_clips=visual_clips or [],
            video_clips_timeline=video_clips_timeline or [],
            music_files_pool=music_files_pool or [],
            music_clips_timeline=music_clips_timeline or [],
            master_music_volume=master_music_volume,
            sfx_events=sfx_events or [],
            script_text=script_text,
            outro_text=outro_text,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            target_width=target_width,
            target_height=target_height,
            sub_color=sub_color,
            sub_size=sub_size,
            voiceover_mode=voiceover_mode,
            custom_audio_path=custom_audio_path,
            outro_voice_active=outro_voice_active,
        )

    # 3. Speed-locked final render, with quality-appropriate bitrate.
    final_composed_video.write_videofile(
        output_video_path,
        fps=RENDER_FPS,
        threads=RENDER_THREADS,
        preset=RENDER_PRESET,
        codec="libx264",
        audio_codec="aac",
        bitrate=export_bitrate,
    )

    # 4. Cleanup: remove temp subtitle/ticker/CTA-voice files.
    for temp_path in (SUBTITLE_TEMP_PNG, TICKER_TEMP_PNG, CTA_TEMP_VOICE_MP3):
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return output_video_path


# --------------------------------------------------------------
# Run this file directly to smoke-test it (optional)
# --------------------------------------------------------------
if __name__ == "__main__":
    # --- Example 1: standard studio mode ---
    standard_result_path = compile_cinematic_video(
        mode="standard",
        visual_clips=[
            {"path": "mandir_photo_1.jpg", "is_image": True, "start": 0.0, "end": 5.0},
            {"path": "mandir_visual.mp4", "is_image": False, "start": 0.0, "end": 0.0},
        ],
        video_clips_timeline=[],
        music_files_pool=[],
        music_clips_timeline=[],
        master_music_volume=0.8,
        sfx_events=[],
        script_text="This temple is centuries old and has its own unique story...",
        outro_text="Jai Baba ki! Next video coming soon.",
        output_video_path="final_output_standard.mp4",
        aspect_ratio="9:16",
        duration_seconds=None,
        quality="720p",
        sub_color="#FFD700",
        sub_size=65,
        voiceover_mode="ai_tts",
        custom_audio_path=None,
    )
    print(f"Final (standard mode) video saved to: {standard_result_path}")

    # --- Example 2: live loop mode ---
    live_loop_result_path = compile_cinematic_video(
        mode="live_loop",
        visual_clips=[
            {"path": "mandir_photo_1.jpg", "is_image": True, "start": 0.0, "end": 5.0},
            {"path": "mandir_photo_2.jpg", "is_image": True, "start": 0.0, "end": 5.0},
        ],
        video_clips_timeline=[
            {"path": "mandir_visual.mp4", "start": 0.0, "end": 0.0},
        ],
        outro_text="Jai Baba ki! Next darshan coming soon.",
        output_video_path="final_output_live_loop.mp4",
        aspect_ratio="16:9",
        duration_seconds=300,
        quality="720p",
        master_music_volume=0.8,
    )
    print(f"Final (live loop mode) video saved to: {live_loop_result_path}")
