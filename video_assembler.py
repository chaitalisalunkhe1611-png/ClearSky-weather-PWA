"""Concatenate the per-scene clips into the final MP4.

Because every scene is rendered by :mod:`animation_engine` with identical
encoder settings, the clips share the same codec parameters and can be joined
with the concat demuxer in stream-copy mode -- no re-encoding, so no generation
loss. If that ever fails (mismatched clips, unusual build), we fall back to a
re-encoding join and say so at WARNING level.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from animation_engine import FFMPEG, ffprobe_available, probe_duration
from config import Settings
from utils import PipelineError, run_command

LOG = logging.getLogger("slideshow.assemble")

DURATION_TOLERANCE_SECONDS = 0.75


@dataclass
class FinalVideo:
    path: Path
    duration: float
    size_bytes: int
    video_codec: str
    audio_codec: str
    width: int
    height: int
    joined_by: str


def _concat_line(path: Path) -> str:
    """One ``file '...'`` line for the concat demuxer.

    Paths are made absolute and forward-slashed so the same list file works on
    Windows and POSIX. Single quotes are escaped the way the demuxer expects.
    """
    resolved = str(path.resolve()).replace("\\", "/").replace("'", "'\\''")
    return f"file '{resolved}'"


def write_concat_list(clips: list[Path], out_path: Path) -> Path:
    if not clips:
        raise PipelineError("Cannot assemble a video from zero clips.")
    for clip in clips:
        if not clip.is_file() or clip.stat().st_size == 0:
            raise PipelineError(f"Scene clip is missing or empty: {clip}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(_concat_line(c) for c in clips) + "\n", encoding="utf-8")
    return out_path


def _probe_streams(path: Path) -> dict:
    """Return codec/resolution info. Empty dict if ffprobe is unavailable."""
    if not ffprobe_available():
        return {}
    completed = run_command(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,codec_name,width,height",
            "-of", "json",
            str(path),
        ],
        what=f"inspect {path}",
        check=False,
    )
    if completed.returncode != 0:
        return {}
    try:
        return json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def _describe_streams(probe: dict) -> tuple[str, str, int, int]:
    video_codec = audio_codec = "unknown"
    width = height = 0
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video" and video_codec == "unknown":
            video_codec = str(stream.get("codec_name", "unknown"))
            width = int(stream.get("width") or 0)
            height = int(stream.get("height") or 0)
        elif stream.get("codec_type") == "audio" and audio_codec == "unknown":
            audio_codec = str(stream.get("codec_name", "unknown"))
    return video_codec, audio_codec, width, height


def _run_concat(concat_list: Path, out_path: Path, *, copy: bool, what: str) -> bool:
    if copy:
        codec_args = ["-c", "copy"]
    else:
        codec_args = [
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-profile:v", "high", "-level", "4.0", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        ]

    completed = run_command(
        [
            FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            *codec_args,
            "-movflags", "+faststart",
            str(out_path),
        ],
        what=what,
        timeout=1800,
        check=False,
    )
    if completed.returncode != 0:
        LOG.debug("concat (%s) failed: %s", what, (completed.stderr or "").strip()[-800:])
        return False
    return out_path.is_file() and out_path.stat().st_size > 0


def assemble_video(
    clips: list[Path],
    out_path: Path,
    settings: Settings,
    *,
    expected_duration: float | None = None,
) -> FinalVideo:
    """Join scene clips into ``out_path`` and verify the result."""
    concat_list = write_concat_list(clips, out_path.parent / "concat_list.txt")

    if expected_duration is None:
        expected_duration = sum(probe_duration(c) for c in clips)

    LOG.info(
        "Joining %d clips (expected duration %.2fs) -> %s",
        len(clips), expected_duration, out_path,
    )

    if out_path.exists():
        out_path.unlink()

    joined_by = "stream copy"
    ok = _run_concat(concat_list, out_path, copy=True, what="concatenate scene clips")

    if ok:
        actual = probe_duration(out_path, required=False)
        if abs(actual - expected_duration) > DURATION_TOLERANCE_SECONDS:
            LOG.warning(
                "Stream-copy join produced %.2fs but %.2fs was expected "
                "(tolerance %.2fs). The clips probably differ in codec "
                "parameters. Re-joining with a re-encode.",
                actual, expected_duration, DURATION_TOLERANCE_SECONDS,
            )
            ok = False

    if not ok:
        LOG.warning(
            "FALLBACK ENGAGED [assemble]: the lossless stream-copy join failed, "
            "so the video is being re-encoded instead. Output quality is slightly "
            "lower and the join takes longer, but the result is correct."
        )
        joined_by = "re-encode"
        if out_path.exists():
            out_path.unlink()
        if not _run_concat(concat_list, out_path, copy=False, what="re-encode scene clips"):
            raise PipelineError(
                "Both the stream-copy join and the re-encode join failed. Run the "
                "command manually to see the full FFmpeg error:\n"
                f"  ffmpeg -f concat -safe 0 -i {concat_list} -c copy {out_path}"
            )

    probe = _probe_streams(out_path)
    video_codec, audio_codec, width, height = _describe_streams(probe)
    duration = probe_duration(out_path, required=False)

    if not probe:
        # ffprobe is unavailable, so we genuinely do not know what is in the
        # file. Say that, rather than reporting a problem we have not observed.
        LOG.info(
            "ffprobe is unavailable, so the final stream parameters were not "
            "verified. The video was assembled at %dx%d from %d clips.",
            settings.video_width, settings.video_height, len(clips),
        )
    else:
        if width and height and (width, height) != (settings.video_width, settings.video_height):
            LOG.warning(
                "Final video is %dx%d but the configured size is %dx%d.",
                width, height, settings.video_width, settings.video_height,
            )
        if audio_codec == "unknown":
            LOG.warning(
                "No audio stream was detected in the final video. If narration is "
                "missing, check that the scene clips contain audio."
            )

    return FinalVideo(
        path=out_path,
        duration=duration,
        size_bytes=out_path.stat().st_size,
        video_codec=video_codec,
        audio_codec=audio_codec,
        width=width,
        height=height,
        joined_by=joined_by,
    )
