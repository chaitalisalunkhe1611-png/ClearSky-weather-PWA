"""Generate one still image per scene.

Primary provider: Pollinations (keyless).
Fallback provider: Cloudflare Workers AI.

Both endpoints are called directly over HTTP with explicit timeouts, and every
image is content-addressed in ``.cache/images`` so a failed rerun never re-spends
free-tier quota on an image that already exists.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import secrets
import time
from pathlib import Path
from urllib.parse import quote

import requests

from config import Settings
from utils import (
    AssetCache,
    ConfigError,
    ExternalServiceError,
    content_hash,
    log_fallback,
    request_with_retry,
    response_error_snippet,
)

LOG = logging.getLogger("slideshow.images")

POLLINATIONS_ENDPOINT = "https://image.pollinations.ai/prompt"
CLOUDFLARE_ENDPOINT = "https://api.cloudflare.com/client/v4/accounts"

# Magic-number sniffing. A keyless endpoint that is rate-limiting you will
# happily return HTML or JSON with HTTP 200, so the status code alone proves
# nothing -- the bytes have to look like an image.
_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)


def sniff_image_suffix(data: bytes) -> str | None:
    for magic, suffix in _MAGIC:
        if data.startswith(magic):
            return suffix
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _new_seed() -> int:
    """A fresh random seed per request.

    This is deliberately NOT a fixed seed. A fixed seed does not preserve
    character identity across prompts -- that claim is false -- and reusing one
    only makes the provider serve the same cached image for every scene.
    A random seed exists here for one reason: to avoid getting a stale CDN
    entry back for a prompt we have not successfully generated before.
    """
    return secrets.randbelow(2**31 - 1)


class _Throttle:
    """Enforce a minimum spacing between requests to one host.

    Pollinations' anonymous tier is rate limited to roughly one request every
    15 seconds. Hammering it produces HTTP 429s and, worse, silent failures.
    """

    def __init__(self, min_interval: float):
        self.min_interval = max(0.0, min_interval)
        self._last: float | None = None

    def wait(self) -> None:
        if self.min_interval <= 0 or self._last is None:
            self._last = time.monotonic()
            return
        elapsed = time.monotonic() - self._last
        remaining = self.min_interval - elapsed
        if remaining > 0:
            LOG.info(
                "Waiting %.1fs to respect the Pollinations anonymous rate limit "
                "(about one request every %.0fs).",
                remaining,
                self.min_interval,
            )
            time.sleep(remaining)
        self._last = time.monotonic()


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def _pollinations_fetch(prompt: str, settings: Settings, session: requests.Session) -> bytes:
    params = {
        "width": str(settings.video_width),
        "height": str(settings.video_height),
        "nologo": "true",
        "seed": str(_new_seed()),
        # Identifies the caller without needing an account.
        "referrer": "local-slideshow-generator",
    }
    if settings.pollinations_model:
        params["model"] = settings.pollinations_model
    else:
        LOG.debug("POLLINATIONS_MODEL is empty; the server will pick its default model.")

    url = f"{POLLINATIONS_ENDPOINT}/{quote(prompt, safe='')}"

    response = request_with_retry(
        "GET",
        url,
        provider="Pollinations",
        connect_timeout=settings.http_connect_timeout,
        read_timeout=settings.http_read_timeout,
        max_retries=settings.http_max_retries,
        session=session,
        params=params,
        headers={"Accept": "image/*"},
    )

    if response.status_code != 200:
        raise ExternalServiceError(
            "Pollinations",
            f"image request failed. Body: {response_error_snippet(response)}",
            status=response.status_code,
        )

    data = response.content
    suffix = sniff_image_suffix(data)

    if suffix is None:
        content_type = response.headers.get("Content-Type", "unknown")
        raise ExternalServiceError(
            "Pollinations",
            "returned HTTP 200 but the body is not an image "
            f"(Content-Type={content_type}, {len(data)} bytes). The keyless tier "
            "may be rate-limiting this IP or requiring sign-in now. Body: "
            f"{data[:200]!r}",
        )

    if len(data) < 1024:
        raise ExternalServiceError(
            "Pollinations", f"image body is implausibly small ({len(data)} bytes)"
        )

    LOG.info(
        "Pollinations returned %s (%d KB, Content-Type=%s)",
        suffix, len(data) // 1024, response.headers.get("Content-Type", "unknown"),
    )
    return data


def _cloudflare_fetch(prompt: str, settings: Settings, session: requests.Session) -> bytes:
    account_id = settings.require("cf_account_id", "CF_ACCOUNT_ID")
    model = settings.require_model("CF_IMAGE_MODEL")

    model_path = model.lstrip("/")
    url = f"{CLOUDFLARE_ENDPOINT}/{account_id}/ai/run/{model_path}"

    response = request_with_retry(
        "POST",
        url,
        provider="Cloudflare",
        connect_timeout=settings.http_connect_timeout,
        read_timeout=settings.http_read_timeout,
        max_retries=settings.http_max_retries,
        session=session,
        headers={
            "Authorization": f"Bearer {settings.cf_api_token}",
            "Content-Type": "application/json",
        },
        json={
            "prompt": prompt,
            "seed": _new_seed(),
            "width": settings.video_width,
            "height": settings.video_height,
        },
    )

    # Some Workers AI image models stream raw bytes back.
    content_type = response.headers.get("Content-Type", "")
    if response.status_code == 200 and content_type.startswith("image/"):
        suffix = sniff_image_suffix(response.content)
        if suffix is None:
            raise ExternalServiceError(
                "Cloudflare", "claimed an image Content-Type but the body is not a known image"
            )
        return response.content

    if response.status_code != 200:
        raise ExternalServiceError(
            "Cloudflare",
            f"ai/run failed. Body: {response_error_snippet(response)}",
            status=response.status_code,
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise ExternalServiceError(
            "Cloudflare",
            f"response was not JSON. Body: {response_error_snippet(response)}",
        ) from exc

    if not body.get("success", True):
        errors = body.get("errors") or body.get("messages") or body
        raise ExternalServiceError(
            "Cloudflare", f"API reported failure: {json.dumps(errors)[:400]}"
        )

    result = body.get("result") or {}
    encoded = result.get("image") or result.get("data")
    if not encoded:
        raise ExternalServiceError(
            "Cloudflare",
            "no image in the response. Keys present: "
            f"{sorted(result) if isinstance(result, dict) else type(result).__name__}",
        )

    if isinstance(encoded, str) and encoded.startswith("data:"):
        encoded = encoded.split(",", 1)[-1]

    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ExternalServiceError("Cloudflare", f"image field was not valid base64: {exc}") from exc

    if sniff_image_suffix(data) is None:
        raise ExternalServiceError(
            "Cloudflare", "decoded payload is not a recognised image format"
        )
    return data


# ---------------------------------------------------------------------------
# Cache-aware single image generation
# ---------------------------------------------------------------------------


def _cache_key(prompt: str, settings: Settings, provider: str) -> str:
    model = {
        "pollinations": settings.pollinations_model or "<server-default>",
        "cloudflare": settings.cf_image_model,
    }[provider]
    return content_hash(provider, model, prompt, settings.video_width, settings.video_height)


def generate_image(
    prompt: str,
    scene_number: int,
    settings: Settings,
    cache: AssetCache,
    throttle: _Throttle,
    session: requests.Session,
) -> Path:
    """Return a path to a still image for one scene, using the cache when possible."""
    errors: list[str] = []

    # --- primary: Pollinations ---
    key = _cache_key(prompt, settings, "pollinations")
    cached = cache.lookup_any("images", key)
    if cached:
        LOG.info("Scene %d: reusing cached image %s", scene_number, cached.name)
        return cached

    throttle.wait()
    try:
        data = _pollinations_fetch(prompt, settings, session)
        suffix = sniff_image_suffix(data) or ".png"
        path = cache.store_bytes(
            "images",
            key,
            suffix,
            data,
            meta={"provider": "pollinations", "scene": scene_number, "prompt": prompt},
        )
        LOG.info("Scene %d: image generated via Pollinations -> %s", scene_number, path.name)
        return path
    except (ExternalServiceError, ConfigError) as exc:
        errors.append(f"Pollinations: {exc}")
        LOG.warning("Scene %d: Pollinations failed: %s", scene_number, exc)

    # --- fallback: Cloudflare ---
    if settings.has_cloudflare:
        reason = errors[-1]
        log_fallback("image", "Pollinations", "Cloudflare Workers AI", reason)

        key = _cache_key(prompt, settings, "cloudflare")
        cached = cache.lookup_any("images", key)
        if cached:
            LOG.info("Scene %d: reusing cached image %s", scene_number, cached.name)
            return cached

        try:
            data = _cloudflare_fetch(prompt, settings, session)
            suffix = sniff_image_suffix(data) or ".png"
            path = cache.store_bytes(
                "images",
                key,
                suffix,
                data,
                meta={"provider": "cloudflare", "scene": scene_number, "prompt": prompt},
            )
            LOG.info("Scene %d: image generated via Cloudflare -> %s", scene_number, path.name)
            return path
        except (ExternalServiceError, ConfigError) as exc:
            errors.append(f"Cloudflare: {exc}")
            LOG.warning("Scene %d: Cloudflare failed: %s", scene_number, exc)
    else:
        errors.append(
            "Cloudflare fallback is unavailable because CF_ACCOUNT_ID, CF_API_TOKEN "
            "and CF_IMAGE_MODEL are not all set in .env"
        )
        LOG.warning(
            "Scene %d: no image fallback available -- Cloudflare is not fully "
            "configured in .env.", scene_number,
        )

    raise ExternalServiceError(
        "images",
        f"could not generate an image for scene {scene_number}. Tried:\n  - "
        + "\n  - ".join(errors),
    )


def generate_images(
    prompts: list[str],
    settings: Settings,
    cache: AssetCache,
    session: requests.Session | None = None,
) -> list[Path]:
    """Generate one image per prompt, in order."""
    owns_session = session is None
    session = session or requests.Session()
    throttle = _Throttle(settings.pollinations_min_interval)

    try:
        paths: list[Path] = []
        for index, prompt in enumerate(prompts, start=1):
            LOG.info("Image %d/%d", index, len(prompts))
            paths.append(
                generate_image(prompt, index, settings, cache, throttle, session)
            )
        return paths
    finally:
        if owns_session:
            session.close()
