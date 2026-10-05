"""Configuration layer.

Design rule enforced here: **no model name is ever hardcoded in this project.**
Every model identifier is read from ``.env`` at runtime. If a model name is
missing, we raise a :class:`ConfigError` that names the exact key to fill in --
we never silently fall back to a guessed model, because free-tier model IDs
rotate every few months and a stale guess is worse than an error.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from utils import ConfigError

PROJECT_ROOT = Path(__file__).resolve().parent

# Where the user should look when a model name is missing. Kept as a single
# dict so the error text stays consistent and easy to update.
_MODEL_HELP = {
    "GEMINI_MODEL": (
        "Set GEMINI_MODEL in .env to a model ID that is free *right now*. "
        "Check https://ai.google.dev/gemini-api/docs/pricing then copy the "
        "exact ID (use `python smoke_tests/test_gemini.py` to list the IDs "
        "your key can actually see)."
    ),
    "GROQ_MODEL": (
        "Set GROQ_MODEL in .env to a current model ID. Check "
        "https://console.groq.com/docs/models then copy the exact ID "
        "(`python smoke_tests/test_groq.py` lists them)."
    ),
    "CF_IMAGE_MODEL": (
        "Set CF_IMAGE_MODEL in .env to a Workers AI image model ID from "
        "https://developers.cloudflare.com/workers-ai/models/"
    ),
}


def _as_int(raw: str | None, key: str, default: int) -> int:
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(float(raw))
    except ValueError as exc:
        raise ConfigError(f"{key} must be a whole number, got {raw!r}.") from exc


def _as_float(raw: str | None, key: str, default: float) -> float:
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}.") from exc


def _clean(raw: str | None) -> str:
    """Return a stripped env value, treating blank/whitespace as absent."""
    return (raw or "").strip()


def _mask(secret: str) -> str:
    if not secret:
        return "<unset>"
    if len(secret) <= 4:
        return "****"
    return f"...{secret[-4:]}"


@dataclass
class Settings:
    """Resolved runtime configuration."""

    # --- provider credentials (raw strings; emptiness == not configured) ---
    gemini_api_key: str = ""
    gemini_model: str = ""
    groq_api_key: str = ""
    groq_model: str = ""
    pollinations_model: str = ""
    cf_account_id: str = ""
    cf_api_token: str = ""
    cf_image_model: str = ""

    # --- voice ---
    edge_tts_voice: str = "en-US-JennyNeural"
    edge_tts_rate: str = "+0%"
    edge_tts_volume: str = "+0%"
    edge_tts_pitch: str = "+0Hz"

    # --- slideshow shape ---
    scene_count: int = 5
    min_total_seconds: float = 30.0
    max_total_seconds: float = 45.0
    video_width: int = 1280
    video_height: int = 720
    video_fps: int = 30
    kenburns_upscale: int = 2
    scene_tail_pad_seconds: float = 0.35

    # --- network ---
    http_connect_timeout: float = 10.0
    http_read_timeout: float = 120.0
    http_max_retries: int = 3
    tts_max_attempts: int = 4
    pollinations_min_interval: float = 15.0

    # --- misc ---
    log_level: str = "INFO"
    cache_dir: Path = field(default_factory=lambda: PROJECT_ROOT / ".cache")
    output_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "output")

    # ------------------------------------------------------------------
    # Capability checks. These require BOTH credential and model name,
    # because a credential with no model name cannot produce a request.
    # ------------------------------------------------------------------
    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_model)

    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key and self.groq_model)

    @property
    def has_cloudflare(self) -> bool:
        return bool(self.cf_account_id and self.cf_api_token and self.cf_image_model)

    # ------------------------------------------------------------------
    # Accessors that raise actionable errors instead of defaulting.
    # ------------------------------------------------------------------
    def require_model(self, key: str) -> str:
        value = _clean(getattr(self, key.lower(), ""))
        if not value:
            raise ConfigError(
                f"{key} is not set in .env. {_MODEL_HELP.get(key, '')}".strip()
            )
        return value

    def require(self, attr: str, env_key: str) -> str:
        value = _clean(getattr(self, attr, ""))
        if not value:
            raise ConfigError(f"{env_key} is not set in .env.")
        return value

    def readiness_report(self) -> list[tuple[str, str, str]]:
        """(stage, status, note) rows for `python main.py --check`."""
        rows: list[tuple[str, str, str]] = []

        rows.append(_row("Script / Gemini (primary)", self.has_gemini,
                         f"key={_mask(self.gemini_api_key)} model={self.gemini_model or '<unset>'}"))
        rows.append(_row("Script / Groq (fallback)", self.has_groq,
                         f"key={_mask(self.groq_api_key)} model={self.groq_model or '<unset>'}"))
        rows.append(_row("Images / Pollinations (primary)", True,
                         f"keyless; model={self.pollinations_model or '<server default>'}"))
        rows.append(_row("Images / Cloudflare (fallback)", self.has_cloudflare,
                         f"account={_mask(self.cf_account_id)} token={_mask(self.cf_api_token)} "
                         f"model={self.cf_image_model or '<unset>'}"))
        rows.append(_row("Voice / Edge TTS", True,
                         f"voice={self.edge_tts_voice} rate={self.edge_tts_rate}"))

        if not (self.has_gemini or self.has_groq):
            rows.append((
                "Script writing", "BLOCKED",
                "neither Gemini nor Groq is configured; the pipeline cannot start.",
            ))
        return rows


def _row(stage: str, ok: bool, note: str) -> tuple[str, str, str]:
    return (stage, "OK" if ok else "not configured", note)


def load_settings(env_file: str | Path | None = None) -> Settings:
    """Read ``.env`` (if present) plus the real environment, and validate types.

    Real environment variables win over ``.env``, which is the usual convention
    and lets CI override values without editing files.
    """
    env_path = Path(env_file) if env_file else PROJECT_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)

    env = os.environ
    settings = Settings(
        gemini_api_key=_clean(env.get("GEMINI_API_KEY")),
        gemini_model=_clean(env.get("GEMINI_MODEL")),
        groq_api_key=_clean(env.get("GROQ_API_KEY")),
        groq_model=_clean(env.get("GROQ_MODEL")),
        pollinations_model=_clean(env.get("POLLINATIONS_MODEL")),
        cf_account_id=_clean(env.get("CF_ACCOUNT_ID")),
        cf_api_token=_clean(env.get("CF_API_TOKEN")),
        cf_image_model=_clean(env.get("CF_IMAGE_MODEL")),
        # A voice name is not a model name; the user picked this default
        # deliberately, and it is overridable in .env.
        edge_tts_voice=_clean(env.get("EDGE_TTS_VOICE")) or "en-US-JennyNeural",
        edge_tts_rate=_clean(env.get("EDGE_TTS_RATE")) or "+0%",
        edge_tts_volume=_clean(env.get("EDGE_TTS_VOLUME")) or "+0%",
        edge_tts_pitch=_clean(env.get("EDGE_TTS_PITCH")) or "+0Hz",
        scene_count=_as_int(env.get("SCENE_COUNT"), "SCENE_COUNT", 5),
        min_total_seconds=_as_float(env.get("MIN_TOTAL_SECONDS"), "MIN_TOTAL_SECONDS", 30.0),
        max_total_seconds=_as_float(env.get("MAX_TOTAL_SECONDS"), "MAX_TOTAL_SECONDS", 45.0),
        video_width=_as_int(env.get("VIDEO_WIDTH"), "VIDEO_WIDTH", 1280),
        video_height=_as_int(env.get("VIDEO_HEIGHT"), "VIDEO_HEIGHT", 720),
        video_fps=_as_int(env.get("VIDEO_FPS"), "VIDEO_FPS", 30),
        kenburns_upscale=_as_int(env.get("KENBURNS_UPSCALE"), "KENBURNS_UPSCALE", 2),
        scene_tail_pad_seconds=_as_float(
            env.get("SCENE_TAIL_PAD_SECONDS"), "SCENE_TAIL_PAD_SECONDS", 0.35
        ),
        http_connect_timeout=_as_float(
            env.get("HTTP_CONNECT_TIMEOUT_SECONDS"), "HTTP_CONNECT_TIMEOUT_SECONDS", 10.0
        ),
        http_read_timeout=_as_float(
            env.get("HTTP_READ_TIMEOUT_SECONDS"), "HTTP_READ_TIMEOUT_SECONDS", 120.0
        ),
        http_max_retries=_as_int(env.get("HTTP_MAX_RETRIES"), "HTTP_MAX_RETRIES", 3),
        tts_max_attempts=_as_int(env.get("TTS_MAX_ATTEMPTS"), "TTS_MAX_ATTEMPTS", 4),
        pollinations_min_interval=_as_float(
            env.get("POLLINATIONS_MIN_INTERVAL_SECONDS"),
            "POLLINATIONS_MIN_INTERVAL_SECONDS",
            15.0,
        ),
        log_level=(_clean(env.get("LOG_LEVEL")) or "INFO").upper(),
        cache_dir=Path(_clean(env.get("CACHE_DIR")) or PROJECT_ROOT / ".cache"),
        output_dir=Path(_clean(env.get("OUTPUT_DIR")) or PROJECT_ROOT / "output"),
    )

    _validate(settings)
    return settings


def _validate(settings: Settings) -> None:
    if settings.scene_count < 2:
        raise ConfigError("SCENE_COUNT must be at least 2 to build a slideshow.")
    if settings.scene_count > 20:
        raise ConfigError("SCENE_COUNT above 20 will not fit in a short video.")
    if settings.min_total_seconds >= settings.max_total_seconds:
        raise ConfigError("MIN_TOTAL_SECONDS must be less than MAX_TOTAL_SECONDS.")
    if settings.video_width % 2 or settings.video_height % 2:
        raise ConfigError("VIDEO_WIDTH and VIDEO_HEIGHT must be even (H.264 yuv420p).")
    if settings.video_fps <= 0:
        raise ConfigError("VIDEO_FPS must be positive.")
    if settings.kenburns_upscale < 1:
        raise ConfigError("KENBURNS_UPSCALE must be >= 1 (2 is recommended).")
    if settings.scene_tail_pad_seconds < 0:
        raise ConfigError("SCENE_TAIL_PAD_SECONDS cannot be negative.")
    if settings.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError(
            f"LOG_LEVEL must be one of DEBUG/INFO/WARNING/ERROR/CRITICAL, got {settings.log_level!r}."
        )
