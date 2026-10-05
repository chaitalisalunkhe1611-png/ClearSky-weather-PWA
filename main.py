#!/usr/bin/env python3
"""Build a narrated slideshow from a text premise.

    python main.py "a lighthouse keeper who teaches a seagull to read"
    python main.py --check
    python main.py "..." --scenes 6

What this produces: N still images with a slow Ken Burns pan/zoom over each,
narrated, stitched into ``output/final_video.mp4`` at 1280x720, plus
``output/metadata.txt`` to paste into YouTube Studio.

This is a slideshow of still images with narration. It is not animation, and no
video-generation model is involved anywhere.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Make `python main.py` and `python smoke_tests/test_x.py` both work regardless
# of the caller's working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402

from animation_engine import ensure_tools, render_scene  # noqa: E402
from config import PROJECT_ROOT, Settings, load_settings  # noqa: E402
from image_generator import generate_images  # noqa: E402
from script_generator import generate_script  # noqa: E402
from tts_generator import generate_narration  # noqa: E402
from utils import (  # noqa: E402
    AssetCache,
    ConfigError,
    PipelineError,
    ToolMissingError,
    setup_logging,
)
from video_assembler import assemble_video  # noqa: E402

LOG = logging.getLogger("slideshow.main")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Generate a narrated slideshow (still images + Ken Burns motion + "
            "TTS voiceover) from a text premise. Output: final_video.mp4 and "
            "metadata.txt for a manual YouTube upload."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "premise",
        nargs="?",
        help="What the video is about, in one or two sentences.",
    )
    parser.add_argument(
        "--premise-file",
        type=Path,
        help="Read the premise from a text file instead of the command line.",
    )
    parser.add_argument(
        "--scenes", type=int, help="Override SCENE_COUNT from .env."
    )
    parser.add_argument(
        "--out", type=Path, help="Output directory (default: ./output)."
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore .cache/ and regenerate every asset. Costs free-tier quota.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report configuration and tool readiness, then exit.",
    )
    parser.add_argument(
        "--env-file", type=Path, help="Path to a specific .env file."
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def run_check(settings: Settings) -> int:
    print("\nNarrated slideshow generator -- readiness check\n")
    print(f"Project root : {PROJECT_ROOT}")
    print(f"Cache dir    : {settings.cache_dir}")
    print(f"Output dir   : {settings.output_dir}\n")

    print("FFmpeg")
    try:
        print(f"  OK           {ensure_tools()}")
        from animation_engine import ffprobe_available

        print(
            f"  {'OK          ' if ffprobe_available() else 'WARNING     '} "
            f"ffprobe {'found' if ffprobe_available() else 'NOT found (fallback parsing will be used)'}"
        )
    except ToolMissingError as exc:
        print(f"  MISSING      {exc}")

    print("\nProviders")
    for stage, status, note in settings.readiness_report():
        print(f"  {status:<15} {stage:<32} {note}")

    print(
        "\nSlideshow shape\n"
        f"  scenes       {settings.scene_count}\n"
        f"  duration     {settings.min_total_seconds:.0f}-{settings.max_total_seconds:.0f}s target\n"
        f"  video        {settings.video_width}x{settings.video_height} @ {settings.video_fps}fps\n"
        f"  voice        {settings.edge_tts_voice}"
    )

    blocked = (
        not settings.has_gemini and not settings.has_groq
    )
    print()
    if blocked:
        print(
            "BLOCKED: no script provider is configured. Fill in GEMINI_MODEL and\n"
            "GEMINI_API_KEY (or the Groq pair) in .env, then run the smoke tests.\n"
        )
        return 2
    print("Ready. Next: python smoke_tests/test_ffmpeg.py\n")
    return 0


# ---------------------------------------------------------------------------
# metadata.txt for a manual YouTube upload
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "it", "its", "this", "that", "these",
    "those", "as", "at", "by", "from", "into", "about", "who", "what", "when",
    "where", "why", "how", "his", "her", "their", "they", "she", "he", "them",
    "we", "you", "i", "my", "our", "your", "one", "two", "day", "story",
}


def build_tags(title: str, premise: str, limit: int = 15) -> list[str]:
    words = re.findall(r"[a-z0-9]+", f"{title} {premise}".lower())
    tags: list[str] = []
    for word in words:
        if len(word) < 3 or word in _STOPWORDS or word in tags:
            continue
        tags.append(word)
        if len(tags) >= limit:
            break
    for fixed in ("narrated story", "short story", "audio story"):
        if len(tags) < limit:
            tags.append(fixed)
    return tags


def _timestamp(seconds: float) -> str:
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes:02d}:{secs:02d}"


def write_metadata(
    out_path: Path,
    *,
    title: str,
    premise: str,
    scenes: list,
    scene_durations: list[float],
    settings: Settings,
    total_duration: float,
    script_provider: str,
    script_model: str,
    fallback_reason: str | None,
    final_video: Path,
) -> Path:
    tags = build_tags(title, premise)

    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("YOUTUBE UPLOAD METADATA")
    lines.append("=" * 70)
    lines.append(f"Generated      : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Video file     : {final_video.name}")
    lines.append(f"Duration       : {_timestamp(total_duration)} ({total_duration:.2f}s)")
    lines.append(f"Resolution     : {settings.video_width}x{settings.video_height} @ {settings.video_fps}fps")
    lines.append(f"Voice          : {settings.edge_tts_voice} (Edge TTS)")
    lines.append(f"Script model   : {script_provider} / {script_model}")
    if fallback_reason:
        lines.append(f"NOTE           : a fallback provider was used. Reason: {fallback_reason}")
    lines.append("")
    lines.append("This is a narrated slideshow: still images with a slow pan/zoom and a")
    lines.append("voiceover. It is not animation.")
    lines.append("")

    lines.append("-" * 70)
    lines.append("TITLE")
    lines.append("-" * 70)
    lines.append(title)
    lines.append("")

    lines.append("-" * 70)
    lines.append("DESCRIPTION  (paste into YouTube Studio -> Details -> Description)")
    lines.append("-" * 70)
    lines.append(f"{title}")
    lines.append("")
    lines.append(f"An original short narrated story about: {premise.strip().rstrip('.')}.")
    lines.append("")
    lines.append("Scene list:")
    elapsed = 0.0
    for scene, duration in zip(scenes, scene_durations):
        lines.append(f"{_timestamp(elapsed)}  Scene {scene.scene_number}")
        elapsed += duration
    lines.append("")
    lines.append(
        "Narration by a text-to-speech voice. Images are AI-generated. "
        "Every character name in this story is original."
    )
    lines.append("")
    lines.append("#narratedstory #shortstory #audiostory #bedtimestory")
    lines.append("")

    lines.append("-" * 70)
    lines.append("TAGS  (paste into YouTube Studio -> Show more -> Tags)")
    lines.append("-" * 70)
    tag_line = ", ".join(tags)
    lines.append(tag_line)
    lines.append(f"({len(tag_line)} characters, {len(tags)} tags)")
    lines.append("")

    lines.append("-" * 70)
    lines.append("BEFORE YOU UPLOAD")
    lines.append("-" * 70)
    lines.append(
        "This project does not upload for you, on purpose:\n"
        "  * An unaudited Google Cloud project can only upload videos as PRIVATE\n"
        "    until it passes Google's audit, so an automated upload would not go\n"
        "    live anyway.\n"
        "  * OAuth refresh tokens for an app left in 'Testing' mode expire after\n"
        "    about 7 days, so an uploader would need re-authentication constantly.\n"
        "  * Bulk, repetitive, machine-generated uploads risk YouTube's\n"
        "    monetization and spam policies.\n"
        "Uploading this file yourself takes about a minute and keeps you in\n"
        "control of what gets published.\n"
    )
    lines.append("-" * 70)
    lines.append("SCENE NOTES (for your reference; not for pasting)")
    lines.append("-" * 70)
    for scene, duration in zip(scenes, scene_durations):
        lines.append(f"Scene {scene.scene_number} ({duration:.2f}s)")
        lines.append(f"  dialogue    : {scene.dialogue}")
        lines.append(f"  image_prompt: {scene.image_prompt}")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run_pipeline(args: argparse.Namespace, settings: Settings) -> int:
    started = time.monotonic()

    premise = args.premise
    if args.premise_file:
        premise = args.premise_file.read_text(encoding="utf-8").strip()
    if not premise or not premise.strip():
        raise ConfigError(
            "No premise given. Pass it as an argument:\n"
            '  python main.py "a lighthouse keeper who teaches a seagull to read"'
        )
    premise = " ".join(premise.split())

    if args.scenes:
        if args.scenes < 2:
            raise ConfigError("--scenes must be at least 2.")
        settings.scene_count = args.scenes

    output_dir = args.out or settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    cache = AssetCache(settings.cache_dir, enabled=not args.no_cache)
    if args.no_cache:
        LOG.warning("--no-cache was passed: every asset will be regenerated and quota re-spent.")

    print(f"\nPremise: {premise}")
    print(f"Scenes : {settings.scene_count}\n")

    LOG.info("Checking FFmpeg before doing any network work.")
    ffmpeg_version = ensure_tools()
    LOG.info("Using %s", ffmpeg_version)

    # --- 1. script -------------------------------------------------------
    LOG.info("Step 1/5: writing the script")
    script = generate_script(premise, settings)
    print(f"\nTitle: {script.title}")
    print(f"Script: {script.provider} ({script.model})\n")
    for scene in script.scenes:
        print(f"  Scene {scene.scene_number}: {scene.dialogue}")

    # --- 2. images -------------------------------------------------------
    LOG.info("Step 2/5: generating %d images", len(script.scenes))
    print(
        "\nGenerating images. On the keyless Pollinations tier this is throttled "
        f"to about one request every {settings.pollinations_min_interval:.0f}s, so "
        "expect a few minutes.\n"
    )
    session = requests.Session()
    try:
        image_paths = generate_images(
            [scene.image_prompt for scene in script.scenes], settings, cache, session
        )
    finally:
        session.close()

    # --- 3. narration ----------------------------------------------------
    LOG.info("Step 3/5: synthesising narration")
    audio_clips = generate_narration(
        [scene.dialogue for scene in script.scenes], settings, cache
    )

    narration_total = sum(a.duration for a in audio_clips)
    print(f"\nNarration: {narration_total:.2f}s of speech across {len(audio_clips)} scenes")
    if not (settings.min_total_seconds <= narration_total <= settings.max_total_seconds):
        LOG.warning(
            "Total narration is %.1fs, outside the configured %.0f-%.0fs window. "
            "The finished video will be about %.1fs. To fix, adjust "
            "MIN_TOTAL_SECONDS/MAX_TOTAL_SECONDS or SCENE_COUNT in .env and re-run "
            "(cached assets are reused, so this costs almost no quota).",
            narration_total,
            settings.min_total_seconds,
            settings.max_total_seconds,
            narration_total + settings.scene_tail_pad_seconds * len(audio_clips),
        )

    # --- 4. Ken Burns clips ---------------------------------------------
    LOG.info("Step 4/5: rendering Ken Burns clips")
    work_dir = output_dir / "scenes"
    scene_clips = []
    for scene, image_path, audio in zip(script.scenes, image_paths, audio_clips):
        print(f"  Rendering scene {scene.scene_number}/{len(script.scenes)}")
        clip = render_scene(
            image_path=image_path,
            audio_path=audio.path,
            scene_number=scene.scene_number,
            out_path=work_dir / f"scene_{scene.scene_number:02d}.mp4",
            settings=settings,
        )
        scene_clips.append(clip)

    # --- 5. assemble -----------------------------------------------------
    LOG.info("Step 5/5: joining clips")
    final_path = output_dir / "final_video.mp4"
    final = assemble_video(
        [clip.path for clip in scene_clips],
        final_path,
        settings,
        expected_duration=sum(clip.duration for clip in scene_clips),
    )

    metadata_path = write_metadata(
        output_dir / "metadata.txt",
        title=script.title,
        premise=premise,
        scenes=script.scenes,
        scene_durations=[clip.duration for clip in scene_clips],
        settings=settings,
        total_duration=final.duration,
        script_provider=script.provider,
        script_model=script.model,
        fallback_reason=script.fallback_reason,
        final_video=final.path,
    )

    elapsed = time.monotonic() - started
    print("\n" + "=" * 62)
    print("DONE")
    print("=" * 62)
    print(f"Video    : {final.path}")
    print(
        f"           {final.duration:.2f}s, {final.width}x{final.height}, "
        f"{final.video_codec} + {final.audio_codec}, "
        f"{final.size_bytes / 1_048_576:.1f} MB, joined by {final.joined_by}"
    )
    print(f"Metadata : {metadata_path}")
    print(f"Elapsed  : {elapsed:.1f}s")
    print(
        "\nUpload manually: open YouTube Studio, create a video, and copy the "
        "title, description and tags out of metadata.txt.\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        settings = load_settings(args.env_file)
    except ConfigError as exc:
        # Logging is not configured yet; go straight to stderr.
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    setup_logging(settings.log_level)

    if args.check:
        return run_check(settings)

    try:
        return run_pipeline(args, settings)
    except ConfigError as exc:
        LOG.error("Configuration problem:\n%s", exc)
        return 2
    except ToolMissingError as exc:
        LOG.error("Missing tool:\n%s", exc)
        return 3
    except PipelineError as exc:
        LOG.error("Pipeline failed:\n%s", exc)
        return 1
    except KeyboardInterrupt:
        LOG.error("Interrupted. Cached images and audio are kept -- re-run to resume.")
        return 130
    except Exception as exc:  # pragma: no cover - last-resort guard
        LOG.error("Unexpected failure (%s): %s", type(exc).__name__, exc, exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
