"""Ken Burns motion over still images, rendered with FFmpeg.

This is *pan and zoom on a still image*. It is not animation, and nothing here
calls a video-generation model.

Two things were verified by hand against FFmpeg 7.0.2 before this module was
written, because both are easy to get wrong:

1. ``zoompan`` with ``d=1`` does NOT accumulate the classic
   ``z='min(zoom+0.0012,1.5)'`` expression. ``zoom`` is reset for every output
   frame, so that filter chain produces a nearly static clip that merely looks
   like it works. Measured: first frame vs last frame differed by ~71 dB PSNR,
   i.e. basically identical. Driving the zoom from ``on`` (the output frame
   index) instead produces real, evenly spaced motion (~25 dB between adjacent
   frames, ~11 dB end to end).

2. The source must be upscaled before ``zoompan``, otherwise the zoom resamples
   the original pixels and the motion shimmers.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from shutil import which

from config import Settings
from utils import PipelineError, ToolMissingError, run_command

LOG = logging.getLogger("slideshow.animation")

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

# Duration of one output frame, as reported by `ffprobe`/`ffmpeg -i`.
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")

# Motion patterns, cycled across scenes so consecutive clips do not all move
# the same way. All of them keep the frame filled -- no letterboxing.
PATTERNS = ("zoom_in", "pan_right", "zoom_out", "pan_left")

# How far we push in, as a fraction of the frame. 0.14 is a gentle push that
# stays clean at 720p; much more and soft AI edges start to smear.
ZOOM_AMOUNT = 0.14
# Constant zoom used for the pure pan patterns. A pan needs zoom > 1, otherwise
# the crop window already fills the frame and there is nothing to move.
PAN_ZOOM = 1.16


@dataclass
class SceneClip:
    scene_number: int
    path: Path
    duration: float
    frames: int
    pattern: str
    audio_duration: float


# ---------------------------------------------------------------------------
# Tool discovery and probing
# ---------------------------------------------------------------------------


def ensure_tools() -> str:
    """Verify ffmpeg is present. Returns the version banner."""
    if which(FFMPEG) is None:
        raise ToolMissingError(
            "ffmpeg was not found on PATH. Install it and re-run:\n"
            "  Windows : winget install Gyan.FFmpeg     (or: choco install ffmpeg)\n"
            "  macOS   : brew install ffmpeg\n"
            "  Debian  : sudo apt install ffmpeg\n"
            "  Fedora  : sudo dnf install ffmpeg\n"
            "Then confirm with: ffmpeg -version"
        )
    completed = run_command([FFMPEG, "-hide_banner", "-version"], what="check ffmpeg")
    return completed.stdout.splitlines()[0] if completed.stdout else "ffmpeg (version unknown)"


_FFPROBE_WARNED = False


def _warn_ffprobe_missing_once() -> None:
    """Warn about a missing ffprobe once per process, not once per probe."""
    global _FFPROBE_WARNED
    if _FFPROBE_WARNED:
        return
    _FFPROBE_WARNED = True
    LOG.warning(
        "ffprobe is not on PATH, so durations are being parsed out of `ffmpeg -i` "
        "output instead. This works, but install ffprobe for the documented path."
    )


def ffprobe_available() -> bool:
    return which(FFPROBE) is not None


def probe_duration(media_path: str | Path, *, required: bool = True) -> float:
    """Return the duration of a media file in seconds.

    ``ffprobe`` is the documented path. On hosts where ffmpeg is installed
    without it (some static builds ship ffmpeg only) we fall back to parsing
    ``ffmpeg -i``, which reports the same Duration line on stderr. That fallback
    is logged at WARNING because it is a workaround, not the intended route.
    """
    path = str(media_path)

    if ffprobe_available():
        completed = run_command(
            [
                FFPROBE, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            what=f"read the duration of {path}",
            check=False,
        )
        if completed.returncode == 0:
            try:
                duration = float(completed.stdout.strip())
            except ValueError:
                duration = -1.0
            if duration > 0:
                return duration
        LOG.warning(
            "ffprobe could not read a duration from %s (exit %s); falling back to "
            "parsing `ffmpeg -i` output.",
            path, completed.returncode,
        )
    else:
        _warn_ffprobe_missing_once()

    completed = run_command([FFMPEG, "-hide_banner", "-i", path], what=f"probe {path}", check=False)
    match = _DURATION_RE.search(completed.stderr or "")
    if not match:
        if required:
            raise PipelineError(
                f"Could not determine the duration of {path}. The file may be "
                "corrupt or not a media file.\n"
                + "\n".join((completed.stderr or "").strip().splitlines()[-8:])
            )
        return 0.0

    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


# ---------------------------------------------------------------------------
# Filter construction
# ---------------------------------------------------------------------------


def build_kenburns_filter(
    pattern: str,
    frames: int,
    settings: Settings,
) -> str:
    """Build the scale -> crop -> zoompan -> format chain for one scene.

    Comma escaping note: ffmpeg's filtergraph parser treats a bare comma as a
    filter separator, so the comma inside ``min(on,N)`` must be escaped as
    ``\\,``. These strings are handed to ffmpeg as an argv entry (never through a
    shell), so the backslash survives to the filter parser intact.
    """
    frames = max(1, frames)
    denominator = max(frames - 1, 1)

    width, height = settings.video_width, settings.video_height
    upscale = max(1, settings.kenburns_upscale)
    big_w, big_h = width * upscale, height * upscale

    # Progress runs 0.0 -> 1.0 across the clip and reaches exactly 1.0 on the
    # final frame, which keeps the motion evenly spaced.
    progress = f"min(on\\,{denominator})/{denominator}"
    centre_x = f"iw/2-(iw/zoom/2)"
    centre_y = f"ih/2-(ih/zoom/2)"

    if pattern == "zoom_in":
        zoom = f"1+{ZOOM_AMOUNT}*{progress}"
        x_expr, y_expr = centre_x, centre_y
    elif pattern == "zoom_out":
        zoom = f"1+{ZOOM_AMOUNT}-{ZOOM_AMOUNT}*{progress}"
        x_expr, y_expr = centre_x, centre_y
    elif pattern == "pan_right":
        zoom = f"{PAN_ZOOM}"
        x_expr = f"(iw-iw/zoom)*{progress}"
        y_expr = centre_y
    elif pattern == "pan_left":
        zoom = f"{PAN_ZOOM}"
        x_expr = f"(iw-iw/zoom)*(1-{progress})"
        y_expr = centre_y
    else:
        raise PipelineError(
            f"Unknown motion pattern {pattern!r}. Known patterns: {', '.join(PATTERNS)}"
        )

    # force_original_aspect_ratio=increase guarantees the frame is fully covered
    # whatever aspect ratio the image model returned, then crop trims the
    # overflow. Images are never stretched or letterboxed.
    return (
        f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={big_w}:{big_h},"
        f"zoompan=z='{zoom}':x='{x_expr}':y='{y_expr}':d=1:s={width}x{height}:fps={settings.video_fps},"
        f"format=yuv420p,setsar=1"
    )


def pick_pattern(scene_number: int) -> str:
    return PATTERNS[(scene_number - 1) % len(PATTERNS)]


# ---------------------------------------------------------------------------
# Scene rendering
# ---------------------------------------------------------------------------


def render_scene(
    image_path: Path,
    audio_path: Path,
    scene_number: int,
    out_path: Path,
    settings: Settings,
) -> SceneClip:
    """Render one Ken Burns clip whose length follows that scene's narration.

    The clip length is derived from the measured TTS audio duration, plus a
    short tail pad so the final word is never chopped off mid-syllable.
    """
    audio_duration = probe_duration(audio_path)
    if audio_duration <= 0:
        raise PipelineError(f"TTS audio {audio_path} reports a duration of {audio_duration}s.")

    pad = max(0.0, settings.scene_tail_pad_seconds)
    target_duration = audio_duration + pad
    frames = max(2, int(round(target_duration * settings.video_fps)))

    pattern = pick_pattern(scene_number)
    video_filter = build_kenburns_filter(pattern, frames, settings)

    audio_chain = f"aresample=44100"
    if pad > 0:
        audio_chain = f"apad=pad_dur={pad:.3f},aresample=44100"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    args = [
        FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", str(settings.video_fps), "-i", str(image_path),
        "-i", str(audio_path),
        "-filter_complex", f"[0:v]{video_filter}[v];[1:a]{audio_chain}[a]",
        "-map", "[v]", "-map", "[a]",
        # Pinning the frame count makes the output length exact regardless of
        # container timing quirks in the audio stream.
        "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-profile:v", "high", "-level", "4.0", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        str(out_path),
    ]

    run_command(
        args,
        what=f"render scene {scene_number} ({pattern}, {frames} frames)",
        timeout=900,
    )

    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise PipelineError(f"FFmpeg reported success but {out_path} is missing or empty.")

    rendered = probe_duration(out_path)
    LOG.info(
        "Scene %d: %.2fs narration + %.2fs pad -> %d frames (%.2fs) using '%s'",
        scene_number, audio_duration, pad, frames, rendered, pattern,
    )
    return SceneClip(
        scene_number=scene_number,
        path=out_path,
        duration=rendered,
        frames=frames,
        pattern=pattern,
        audio_duration=audio_duration,
    )


# ---------------------------------------------------------------------------
# Convenience for the FFmpeg smoke test
# ---------------------------------------------------------------------------


def make_test_image(out_path: Path, width: int = 1280, height: int = 720) -> Path:
    """Generate a synthetic test image with ffmpeg (no network, no assets)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
            "-f", "lavfi",
            "-i", f"testsrc2=size={width}x{height}",
            "-frames:v", "1",
            str(out_path),
        ],
        what="create a synthetic test image",
        timeout=120,
    )
    return out_path
