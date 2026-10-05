"""Shared infrastructure: logging, error types, hashing, caching, safe I/O.

Nothing in here talks to a specific provider. Provider code lives in the
sibling modules and imports its helpers from here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import requests

LOG = logging.getLogger("slideshow")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"


class _LoudFormatter(logging.Formatter):
    """Make fallbacks impossible to miss in a wall of scrollback."""

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        if record.levelno == logging.WARNING:
            bar = "!" * 78
            return f"\n{bar}\n{text}\n{bar}"
        return text


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once. Safe to call multiple times."""
    root = logging.getLogger()
    if getattr(root, "_slideshow_configured", False):
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(_LoudFormatter(_FORMAT))
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root._slideshow_configured = True  # type: ignore[attr-defined]


def log_fallback(stage: str, primary: str, fallback: str, reason: str) -> None:
    """Mandatory loud WARNING whenever a fallback provider is used.

    Every fallback in this project funnels through here so the reason is always
    printed, never silently swallowed.
    """
    LOG.warning(
        "FALLBACK ENGAGED [%s]: primary=%s failed -> using fallback=%s | reason: %s",
        stage,
        primary,
        fallback,
        reason,
    )


# ---------------------------------------------------------------------------
# Errors -- every one of these carries a human-actionable message
# ---------------------------------------------------------------------------


class PipelineError(Exception):
    """Base class for anything a user can act on."""


class ConfigError(PipelineError):
    """Missing or unusable configuration. Message must name the .env key."""


class ToolMissingError(PipelineError):
    """A required external binary (ffmpeg/ffprobe) is not available."""


class ExternalServiceError(PipelineError):
    """A remote API returned an error or was unreachable."""

    def __init__(self, provider: str, message: str, status: int | None = None):
        self.provider = provider
        self.status = status
        detail = f"[{provider}] {message}"
        if status is not None:
            detail = f"[{provider}] HTTP {status}: {message}"
        super().__init__(detail)


class NetworkBlockedError(ExternalServiceError):
    """The host could not be reached at all (offline, firewall, proxy)."""


# ---------------------------------------------------------------------------
# Hashing / cache keys
# ---------------------------------------------------------------------------


def content_hash(*parts: Any) -> str:
    """Stable hex digest over arbitrary JSON-serialisable inputs.

    Used as the cache key so that identical prompts/text reuse the exact same
    on-disk asset instead of re-spending free-tier quota.
    """
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AssetCache:
    """Tiny content-addressed cache: .cache/<namespace>/<hash><suffix>.

    A sidecar ``.json`` records what produced the asset, which makes the cache
    inspectable and makes debugging a bad generation much easier.
    """

    def __init__(self, root: str | Path = ".cache", enabled: bool = True):
        self.root = Path(root)
        self.enabled = enabled

    def _paths(self, namespace: str, key: str, suffix: str) -> tuple[Path, Path]:
        directory = self.root / namespace
        return directory / f"{key}{suffix}", directory / f"{key}.json"

    def lookup(self, namespace: str, key: str, suffix: str) -> Path | None:
        if not self.enabled:
            return None
        asset, _ = self._paths(namespace, key, suffix)
        if asset.is_file() and asset.stat().st_size > 0:
            return asset
        return None

    def lookup_any(self, namespace: str, key: str) -> Path | None:
        """Find a cached asset regardless of its extension.

        Image providers are not consistent about the format they return (PNG,
        JPEG or WebP depending on load), so the extension cannot be part of the
        cache lookup -- only the content hash is.
        """
        if not self.enabled:
            return None
        directory = self.root / namespace
        if not directory.is_dir():
            return None
        for candidate in sorted(directory.glob(f"{key}.*")):
            if candidate.suffix in {".json", ".part"}:
                continue
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate
        return None

    def store_bytes(
        self, namespace: str, key: str, suffix: str, data: bytes, meta: dict[str, Any]
    ) -> Path:
        asset, meta_path = self._paths(namespace, key, suffix)
        asset.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename so an interrupted run can't leave a half file that
        # a later run would happily treat as a cache hit.
        tmp = asset.with_suffix(asset.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, asset)
        meta_path.write_text(
            json.dumps({**meta, "bytes": len(data)}, indent=2), encoding="utf-8"
        )
        return asset


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _describe_request_error(exc: requests.RequestException, url: str) -> str:
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return f"connect timeout after {exc} trying {url}"
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return f"read timeout after {exc} waiting on {url}"
    if isinstance(exc, requests.exceptions.SSLError):
        # A proxy or firewall that silently drops the outbound connection shows
        # up here, as the TLS handshake dies mid-flight. It looks like an SSL
        # problem but is almost always a network-egress problem.
        return (
            f"could not establish a secure connection to {url}. The TLS "
            "handshake was closed early, which normally means a firewall, a "
            f"proxy or a sandbox is blocking outbound HTTPS. ({exc})"
        )
    if isinstance(exc, requests.exceptions.ProxyError):
        return f"the configured proxy refused the connection to {url} ({exc})"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return (
            f"could not connect to {url} ({exc}). No network, a firewall, or a "
            "proxy is blocking this host."
        )
    if isinstance(exc, requests.exceptions.TooManyRedirects):
        return f"too many redirects for {url}"
    return f"{type(exc).__name__} for {url}: {exc}"


def request_with_retry(
    method: str,
    url: str,
    *,
    provider: str,
    connect_timeout: float,
    read_timeout: float,
    max_retries: int = 3,
    session: requests.Session | None = None,
    **kwargs: Any,
) -> requests.Response:
    """HTTP with hard timeouts, bounded exponential backoff, clear errors.

    Retries only on transient conditions (connection errors, 429, 5xx). A 4xx
    that is not 429 is returned immediately -- retrying a bad request just
    burns free-tier quota.
    """
    http = session or requests
    timeout = (connect_timeout, read_timeout)
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            response = http.request(method, url, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
            detail = _describe_request_error(exc, url)
            if attempt == max_retries:
                raise NetworkBlockedError(provider, detail) from exc
            sleep_for = min(2 ** (attempt - 1) * 2, 30)
            LOG.warning(
                "%s: %s (attempt %d/%d). Retrying in %ss.",
                provider, detail, attempt, max_retries, sleep_for,
            )
            time.sleep(sleep_for)
            continue

        if response.status_code == 429 or response.status_code >= 500:
            if attempt == max_retries:
                raise ExternalServiceError(
                    provider,
                    f"gave up after {max_retries} attempts. Body: {_snippet(response)}",
                    status=response.status_code,
                )
            retry_after = _retry_after_seconds(response)
            sleep_for = retry_after or min(2 ** (attempt - 1) * 2, 30)
            LOG.warning(
                "%s: HTTP %d (attempt %d/%d). Retrying in %ss.%s",
                provider, response.status_code, attempt, max_retries, sleep_for,
                " (server said Retry-After)" if retry_after else "",
            )
            time.sleep(sleep_for)
            continue

        return response

    # Unreachable in practice; keeps the type checker happy.
    raise NetworkBlockedError(provider, f"exhausted retries: {last_exc}")


def _retry_after_seconds(response: requests.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, min(float(raw), 120.0))
    except (TypeError, ValueError):
        return None


def describe_network_error(exc: BaseException, url: str = "") -> str | None:
    """Explain a transport-level failure in plain language, or return None.

    Shared by the pipeline and the smoke tests so a blocked host is diagnosed
    the same way everywhere. Returns None when the exception is not a network
    problem, so callers can fall through to their own handling.
    """
    if isinstance(exc, ExternalServiceError):
        return str(exc)
    if isinstance(exc, requests.RequestException):
        return _describe_request_error(exc, url or "the remote host")
    return None


def _snippet(response: requests.Response, limit: int = 400) -> str:
    try:
        text = response.text
    except Exception:  # pragma: no cover - defensive
        return "<unreadable body>"
    text = " ".join(text.split())
    return text[:limit] + ("..." if len(text) > limit else "")


def response_error_snippet(response: requests.Response, limit: int = 400) -> str:
    """Public wrapper so provider modules can build their own error messages."""
    return _snippet(response, limit)


# ---------------------------------------------------------------------------
# Subprocess
# ---------------------------------------------------------------------------


def run_command(
    args: Sequence[str],
    *,
    what: str,
    timeout: float = 600.0,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command with a timeout and a useful failure message.

    ``args`` is passed as a list, never through a shell, so prompt text can
    never be interpreted as shell syntax.
    """
    LOG.debug("running: %s", " ".join(args))
    try:
        completed = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ToolMissingError(
            f"Could not run '{args[0]}' while trying to {what}. "
            f"Install it and make sure it is on PATH. ({exc})"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(
            f"'{args[0]}' timed out after {timeout}s while trying to {what}."
        ) from exc

    if check and completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()[-12:]
        raise PipelineError(
            f"'{args[0]}' exited {completed.returncode} while trying to {what}.\n"
            + "\n".join(tail)
        )
    return completed


def read_json_file(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)
