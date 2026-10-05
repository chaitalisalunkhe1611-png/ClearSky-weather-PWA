#!/usr/bin/env python3
"""Smoke test: Edge TTS voiceover.

Synthesises one sentence, prints the file path and its duration measured with
ffprobe.

Reminder: this is an unofficial endpoint. If it fails here with a 403 or with
"NoAudioReceived", that usually means you are on a datacenter IP or a VPN, which
Microsoft blocks - not that your code is wrong.

    python smoke_tests/test_edge_tts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    OUTPUT_DIR,
    banner,
    ensure_env_file,
    fail,
    load_settings_or_fail,
    pass_,
    run,
)

TEST_SENTENCE = (
    "This is a short test of the narration voice for the slideshow generator."
)


def test() -> int:
    banner("Edge TTS smoke test")

    if not ensure_env_file():
        print("note: continuing anyway - Edge TTS does not need a key.\n")

    settings, code = load_settings_or_fail()
    if settings is None:
        return code

    try:
        import edge_tts  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return fail(
            f"the 'edge-tts' package is not importable ({type(exc).__name__}: {exc}). "
            "Install the pinned dependencies:\n        pip install -r requirements.txt"
        )

    from animation_engine import ffprobe_available, probe_duration
    from tts_generator import generate_scene_audio

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"voice  : {settings.edge_tts_voice}")
    print(f"rate   : {settings.edge_tts_rate}")
    print(f"volume : {settings.edge_tts_volume}")
    print(f"pitch  : {settings.edge_tts_pitch}")
    print(f"text   : {TEST_SENTENCE!r}\n")
    print("synthesising (this usually takes 1-5 seconds)...\n")

    # Use the project's real cache so a successful run is reused by the pipeline.
    from utils import AssetCache

    cache = AssetCache(settings.cache_dir)

    try:
        audio = generate_scene_audio(TEST_SENTENCE, 1, settings, cache)
    except Exception as exc:  # noqa: BLE001
        from _common import describe_exception

        if "403" in str(exc) or "NoAudioReceived" in str(exc) or "handshake" in str(exc).lower():
            return fail(
                "synthesis failed with an endpoint-level rejection.\n"
                "        This is the well-known failure mode:\n"
                "          * Microsoft blocks datacenter IPs and VPNs. Run this\n"
                "            project from a normal home or office connection.\n"
                "          * The anti-abuse token the endpoint uses changes without\n"
                "            notice. Try: pip install --upgrade edge-tts\n"
                "        Raw error: " + describe_exception(exc)
            )
        return fail(describe_exception(exc))

    # Copy somewhere obvious too, so the user can just play the file.
    pretty = OUTPUT_DIR / "edge_tts_test.mp3"
    pretty.write_bytes(audio.path.read_bytes())

    duration = probe_duration(audio.path)
    size_kb = audio.path.stat().st_size // 1024

    print(f"cached  : {audio.cached}")
    print(f"path    : {audio.path}")
    print(f"copy    : {pretty.relative_to(pretty.parents[2])}")
    print(f"size    : {size_kb} KB")
    print(f"probe   : {'ffprobe' if ffprobe_available() else 'ffmpeg -i (ffprobe not found)'}")
    print(f"duration: {duration:.3f}s for {len(TEST_SENTENCE.split())} words")
    print(
        f"pace    : {len(TEST_SENTENCE.split()) / duration * 60:.0f} words per minute\n"
    )

    if duration <= 0:
        return fail(f"synthesised audio reports a duration of {duration}s")

    if duration < 0.5:
        return fail(
            f"audio is only {duration:.3f}s long, which is too short for the text. "
            "The synthesis was probably truncated."
        )

    return pass_(
        f"Edge TTS produced {duration:.2f}s of audio with voice "
        f"{settings.edge_tts_voice} at {audio.path}"
    )


if __name__ == "__main__":
    raise SystemExit(run(test))
