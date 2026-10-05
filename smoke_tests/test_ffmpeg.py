#!/usr/bin/env python3
"""Smoke test: FFmpeg Ken Burns rendering.

Builds a 3-second pan/zoom clip from a synthetic test image plus a synthetic
3-second tone, using the exact production code path in animation_engine.

It does not just check that a file appeared. It also measures how different the
first and last frames are, because a broken zoompan expression produces a clip
that looks fine at a glance and does not move at all.

    python smoke_tests/test_ffmpeg.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    OUTPUT_DIR,
    banner,
    describe_exception,
    fail,
    load_settings_or_fail,
    pass_,
    run,
)

# A clip with real motion scores far below this; a frozen clip sits around 70 dB.
MOTION_PSNR_CEILING_DB = 45.0


def _psnr_between(frame_a: Path, frame_b: Path) -> float | None:
    """Compare two PNGs. Returns average PSNR in dB, or None if unrecognised."""
    from animation_engine import FFMPEG
    from utils import run_command

    completed = run_command(
        [
            FFMPEG, "-hide_banner", "-loglevel", "info",
            "-i", str(frame_a), "-i", str(frame_b),
            "-lavfi", "psnr=stats_file=-",
            "-f", "null", "-",
        ],
        what="compare the first and last frames",
        check=False,
        timeout=120,
    )
    match = re.search(r"average:([0-9.]+|inf)", completed.stderr or "")
    if not match:
        return None
    if match.group(1) == "inf":
        return float("inf")
    return float(match.group(1))


def _extract_frame(clip: Path, frame_index: int, dest: Path) -> bool:
    from animation_engine import FFMPEG
    from utils import run_command

    # The comma inside the select() expression must be escaped for ffmpeg's
    # filtergraph parser.
    completed = run_command(
        [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(clip),
            "-vf", f"select=eq(n\\,{frame_index})",
            "-frames:v", "1",
            str(dest),
        ],
        what=f"extract frame {frame_index}",
        check=False,
        timeout=120,
    )
    return completed.returncode == 0 and dest.is_file() and dest.stat().st_size > 0


def test() -> int:
    from animation_engine import (
        FFMPEG,
        build_kenburns_filter,
        ensure_tools,
        make_test_image,
        probe_duration,
        render_scene,
    )
    from utils import run_command

    banner("FFmpeg Ken Burns smoke test")

    settings, code = load_settings_or_fail()
    if settings is None:
        return code

    try:
        version = ensure_tools()
    except Exception as exc:  # noqa: BLE001
        return fail(describe_exception(exc) + "\n        FFmpeg is mandatory for this project.")

    print(f"ffmpeg : {version}\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- inputs ---------------------------------------------------------
    image_path = OUTPUT_DIR / "ffmpeg_test_image.png"
    make_test_image(image_path, settings.video_width, settings.video_height)
    print(f"image  : {image_path.name} ({image_path.stat().st_size // 1024} KB, synthetic)")

    audio_path = OUTPUT_DIR / "ffmpeg_test_tone.mp3"
    run_command(
        [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3.0",
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(audio_path),
        ],
        what="create a 3 second test tone",
        timeout=120,
    )
    print(f"audio  : {audio_path.name} (synthetic 440 Hz tone)\n")

    # --- render through the real production path ------------------------
    original_pad = settings.scene_tail_pad_seconds
    settings.scene_tail_pad_seconds = 0.0  # so the clip is exactly the 3s tone
    clip_path = OUTPUT_DIR / "ffmpeg_test_clip.mp4"

    try:
        clip = render_scene(
            image_path=image_path,
            audio_path=audio_path,
            scene_number=1,
            out_path=clip_path,
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001
        return fail(describe_exception(exc))
    finally:
        settings.scene_tail_pad_seconds = original_pad

    print(f"pattern: {clip.pattern}")
    print(f"filter : {build_kenburns_filter(clip.pattern, clip.frames, settings)}")
    print(f"frames : {clip.frames}")
    print(f"output : {clip_path.name} ({clip_path.stat().st_size // 1024} KB)")
    print(f"length : {clip.duration:.3f}s (ffprobe reports)\n")

    # --- assertions -----------------------------------------------------
    # Expectations are derived from the *measured* tone, not from the 3.0 we
    # asked lavfi for. MP3 frames are 1152 samples, so a nominal 3.000s tone
    # actually decodes to ~3.030s. The pipeline is supposed to follow the real
    # audio length, so the test must too.
    measured_tone = probe_duration(audio_path)
    expected_frames = max(2, int(round(measured_tone * settings.video_fps)))

    if not (2.9 <= clip.duration <= 3.2):
        return fail(
            f"expected a clip of about 3s from the 3s tone, got {clip.duration:.3f}s"
        )

    if clip.frames != expected_frames:
        return fail(
            f"expected {expected_frames} frames ({measured_tone:.3f}s tone at "
            f"{settings.video_fps}fps), got {clip.frames}"
        )

    first = OUTPUT_DIR / "ffmpeg_test_first.png"
    last = OUTPUT_DIR / "ffmpeg_test_last.png"
    if not (_extract_frame(clip_path, 0, first) and _extract_frame(clip_path, clip.frames - 1, last)):
        return fail("could not extract the first/last frames to verify that the clip moves")

    psnr = _psnr_between(first, last)
    if psnr is None:
        return fail("could not measure the difference between the first and last frames")

    print(f"motion : first vs last frame PSNR = {psnr:.2f} dB")
    print(f"         (frozen clip ~70 dB, real motion well under {MOTION_PSNR_CEILING_DB:.0f} dB)\n")

    if psnr >= MOTION_PSNR_CEILING_DB:
        return fail(
            f"the clip is effectively static (PSNR {psnr:.2f} dB >= "
            f"{MOTION_PSNR_CEILING_DB:.0f} dB). The zoompan expression is not "
            "accumulating. Do not trust a zoompan that uses 'zoom+...' with d=1; "
            "drive the zoom from 'on' instead."
        )

    duration_check = probe_duration(clip_path)
    if abs(duration_check - clip.duration) > 0.05:
        return fail(
            f"duration changed between measurements ({clip.duration:.3f}s vs "
            f"{duration_check:.3f}s) - the file may be still being written"
        )

    return pass_(
        f"FFmpeg rendered a real {clip.duration:.2f}s Ken Burns clip "
        f"({clip.frames} frames, pattern '{clip.pattern}', first/last frame PSNR "
        f"{psnr:.2f} dB) at {clip_path}"
    )


if __name__ == "__main__":
    raise SystemExit(run(test))
