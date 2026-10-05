"""Narrate each scene with Edge TTS.

Edge TTS is free and needs no key, but it is an *unofficial, reverse-engineered*
client for Microsoft's Edge "Read Aloud" endpoint. It can break without warning,
and Microsoft frequently rejects requests from datacenter IPs and VPNs. Every
call here therefore retries with backoff and, when it finally fails, explains
what to check.

Audio is content-addressed in ``.cache/tts`` so a rerun never re-synthesises a
line that already exists.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from animation_engine import probe_duration
from config import Settings
from utils import AssetCache, PipelineError, ToolMissingError, content_hash

LOG = logging.getLogger("slideshow.tts")

try:  # edge-tts pulls in aiohttp; keep the failure friendly rather than a traceback.
    import edge_tts  # type: ignore

    _IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - depends on environment
    edge_tts = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc


_TROUBLESHOOTING = (
    "Edge TTS failed. This is an unofficial endpoint, so the usual causes are:\n"
    "  1. You are on a datacenter IP, a VPS or a VPN. Microsoft blocks these.\n"
    "     Run this project from a normal home/office connection.\n"
    "  2. The endpoint's anti-abuse token changed. Upgrade the client:\n"
    "     pip install --upgrade edge-tts\n"
    "  3. The service is briefly down or rate limiting you. Wait a minute and retry.\n"
    "  4. A firewall or proxy is blocking websockets to speech.platform.bing.com."
)


@dataclass
class SceneAudio:
    scene_number: int
    path: Path
    duration: float
    text: str
    cached: bool = False


def _require_edge_tts() -> None:
    if edge_tts is None:
        raise ToolMissingError(
            "The 'edge-tts' package is not importable "
            f"({type(_IMPORT_ERROR).__name__}: {_IMPORT_ERROR}).\n"
            "Install the pinned dependencies first:\n"
            "  pip install -r requirements.txt"
        )


async def _synthesize_async(
    text: str, voice: str, rate: str, volume: str, pitch: str, out_path: Path
) -> None:
    communicate = edge_tts.Communicate(  # type: ignore[union-attr]
        text=text,
        voice=voice,
        rate=rate,
        volume=volume,
        pitch=pitch,
    )
    await communicate.save(str(out_path))


def _synthesize_once(text: str, settings: Settings, out_path: Path) -> None:
    asyncio.run(
        _synthesize_async(
            text=text,
            voice=settings.edge_tts_voice,
            rate=settings.edge_tts_rate,
            volume=settings.edge_tts_volume,
            pitch=settings.edge_tts_pitch,
            out_path=out_path,
        )
    )


def generate_scene_audio(
    text: str,
    scene_number: int,
    settings: Settings,
    cache: AssetCache,
) -> SceneAudio:
    """Synthesise one scene's narration and return its path and duration."""
    _require_edge_tts()

    key = content_hash(
        "edge-tts",
        text,
        settings.edge_tts_voice,
        settings.edge_tts_rate,
        settings.edge_tts_volume,
        settings.edge_tts_pitch,
    )
    cached = cache.lookup("tts", key, ".mp3")
    if cached:
        duration = probe_duration(cached)
        LOG.info(
            "Scene %d: reusing cached narration %s (%.2fs)", scene_number, cached.name, duration
        )
        return SceneAudio(scene_number, cached, duration, text, cached=True)

    directory = settings.cache_dir / "tts"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{key}.mp3"
    scratch = directory / f"{key}.part.mp3"

    attempts = max(1, settings.tts_max_attempts)
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            if scratch.exists():
                scratch.unlink()
            _synthesize_once(text, settings, scratch)

            if not scratch.is_file() or scratch.stat().st_size == 0:
                raise PipelineError("Edge TTS produced an empty file")

            duration = probe_duration(scratch)
            if duration <= 0:
                raise PipelineError(f"Edge TTS produced unreadable audio (duration {duration}s)")

            os.replace(scratch, target)

            LOG.info(
                "Scene %d: narrated %.2fs with voice %s",
                scene_number, duration, settings.edge_tts_voice,
            )
            return SceneAudio(scene_number, target, duration, text, cached=False)

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            sleep_for = min(2 ** (attempt - 1) * 3, 30)
            LOG.warning(
                "Scene %d: Edge TTS attempt %d/%d failed (%s: %s). Retrying in %ss.",
                scene_number, attempt, attempts, type(exc).__name__, exc, sleep_for,
            )
            time.sleep(sleep_for)

    if scratch.exists():
        try:
            scratch.unlink()
        except OSError:  # pragma: no cover - best effort cleanup
            pass

    raise PipelineError(
        f"Scene {scene_number}: {_TROUBLESHOOTING}\n"
        f"Last error: {type(last_error).__name__}: {last_error}"
    )


def generate_narration(
    dialogues: list[str],
    settings: Settings,
    cache: AssetCache,
) -> list[SceneAudio]:
    """Synthesise every scene's narration, in order."""
    results: list[SceneAudio] = []
    for index, text in enumerate(dialogues, start=1):
        LOG.info("Narration %d/%d", index, len(dialogues))
        results.append(generate_scene_audio(text, index, settings, cache))
    return results


async def _list_voices_async() -> list[dict]:
    return await edge_tts.list_voices()  # type: ignore[union-attr]


def list_voices() -> list[dict]:
    """Return the voices the endpoint currently advertises."""
    _require_edge_tts()
    return asyncio.run(_list_voices_async())
