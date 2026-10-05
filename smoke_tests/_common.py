"""Shared helpers for the smoke tests.

Run any test from the project root:

    python smoke_tests/test_ffmpeg.py

Every test prints exactly one line starting with ``PASS:`` or ``FAIL:`` and
exits 0 or 1 accordingly.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "output" / "smoke"

BANNER = "!" * 78


def pass_(message: str) -> int:
    print(f"PASS: {message}")
    return 0


def fail(reason: str) -> int:
    print(f"FAIL: {reason}")
    return 1


def banner(title: str) -> None:
    print("\n" + BANNER)
    print(title)
    print(BANNER)


def describe_exception(exc: BaseException) -> str:
    """Turn an exception into a reason a human can act on.

    The distinction that matters most: 'the network refused to reach this host'
    is an environment problem, while 'the API returned 400' is a request
    problem. Lumping them together sends people down the wrong path.
    """
    from utils import ExternalServiceError, NetworkBlockedError, describe_network_error

    if isinstance(exc, NetworkBlockedError):
        return (
            "network unreachable - could not connect to the provider at all. "
            "This is an offline machine, a firewall, a proxy, or a sandbox with "
            "an outbound allowlist. It is not evidence that the API key is wrong.\n"
            f"        underlying: {exc}"
        )
    if isinstance(exc, ExternalServiceError):
        return str(exc)
    transport = describe_network_error(exc)
    if transport:
        return (
            "network unreachable - the request never reached the provider. This is "
            "an offline machine, a firewall, a proxy, or a sandbox with an outbound "
            "allowlist; it is not evidence that your API key is wrong.\n"
            f"        underlying: {transport}"
        )
    return f"{type(exc).__name__}: {exc}"


def is_network_problem(exc: BaseException) -> bool:
    """True when the failure was transport-level, so we skip the noisy traceback."""
    import requests

    from utils import ExternalServiceError

    if isinstance(exc, ExternalServiceError):
        return True
    return isinstance(exc, requests.RequestException)


def load_settings_or_fail():
    """Return (settings, None) or (None, exit_code_after_failing)."""
    from config import load_settings
    from utils import ConfigError, setup_logging

    try:
        settings = load_settings()
    except ConfigError as exc:
        return None, fail(f"configuration error: {exc}")
    setup_logging(settings.log_level)
    return settings, None


def ensure_env_file() -> bool:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        print(
            f"note: {env_path} does not exist. Copy .env.example to .env and fill "
            "it in first:\n  cp .env.example .env\n"
        )
        return False
    return True


def run(test) -> int:
    """Run a test function, converting any escaping exception into a FAIL."""
    try:
        return test()
    except KeyboardInterrupt:
        print("\n")
        return fail("interrupted by the user")
    except Exception as exc:  # noqa: BLE001 - this is the top-level handler
        # A blocked host produces a huge, useless traceback. Anything else keeps
        # its traceback, because that is where the real bug will be.
        if not is_network_problem(exc):
            import traceback

            traceback.print_exc()
        return fail(describe_exception(exc))
