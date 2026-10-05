#!/usr/bin/env python3
"""Smoke test: Pollinations keyless image endpoint (primary image generator).

Prints the HTTP status, the Content-Type, and saves the returned image so you
can look at it with your own eyes.

The keyless tier has tightened up: anonymous requests are throttled to roughly
one every 15 seconds, images may carry a watermark, and a blocked or throttled
request can still come back as HTTP 200 with HTML in the body. That is why this
test checks the bytes, not just the status code.

    python smoke_tests/test_pollinations.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

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

TEST_PROMPT = (
    "a friendly round robot with a dented copper body and one crooked antenna, "
    "standing in a sunlit meadow, flat vector illustration, bold outlines, "
    "warm palette"
)


def test() -> int:
    import requests

    from image_generator import POLLINATIONS_ENDPOINT, sniff_image_suffix

    banner("Pollinations image smoke test")

    if not ensure_env_file():
        print("note: continuing anyway - this endpoint does not need a key.\n")

    settings, code = load_settings_or_fail()
    if settings is None:
        return code

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    params = {
        "width": str(settings.video_width),
        "height": str(settings.video_height),
        "nologo": "true",
        "seed": "12345",
        "referrer": "local-slideshow-generator-smoketest",
    }
    if settings.pollinations_model:
        params["model"] = settings.pollinations_model

    url = f"{POLLINATIONS_ENDPOINT}/{quote(TEST_PROMPT, safe='')}"
    print(f"GET {POLLINATIONS_ENDPOINT}/<prompt>")
    print(f"params: {params}\n")

    response = requests.get(
        url,
        params=params,
        headers={"Accept": "image/*"},
        timeout=(settings.http_connect_timeout, settings.http_read_timeout),
    )

    print(f"HTTP status  : {response.status_code}")
    print(f"Content-Type : {response.headers.get('Content-Type', '<none>')}")
    print(f"Bytes        : {len(response.content)}")
    for header in ("x-ratelimit-remaining", "retry-after", "x-cache", "server"):
        if header in response.headers:
            print(f"{header:13}: {response.headers[header]}")
    print()

    if response.status_code == 429:
        return fail(
            "HTTP 429 - you are rate limited. The anonymous tier allows about one "
            "request every 15 seconds. Wait a minute and run this test again."
        )
    if response.status_code in (401, 403):
        return fail(
            f"HTTP {response.status_code} - the keyless tier appears to now require "
            "an account or token for this request. If that stays true, use the "
            "Cloudflare Workers AI fallback: set CF_ACCOUNT_ID, CF_API_TOKEN and "
            "CF_IMAGE_MODEL in .env (see smoke_tests/test_cloudflare.py)."
        )
    if response.status_code != 200:
        body = " ".join(response.text.split())[:300]
        return fail(f"unexpected HTTP {response.status_code}. Body: {body}")

    suffix = sniff_image_suffix(response.content)
    if suffix is None:
        return fail(
            "HTTP 200 but the body is not a recognised image format "
            f"(Content-Type={response.headers.get('Content-Type')!r}, "
            f"starts with {response.content[:16]!r}). A throttled or blocked "
            "keyless response can still return 200 with HTML or JSON, so the "
            "status code alone proves nothing."
        )

    dest = OUTPUT_DIR / f"pollinations_test{suffix}"
    dest.write_bytes(response.content)

    if len(response.content) < 1024:
        return fail(f"image at {dest} is suspiciously small ({len(response.content)} bytes)")

    return pass_(
        f"got HTTP 200, detected {suffix} in the body, saved {len(response.content) // 1024} KB "
        f"to {dest.relative_to(dest.parents[2])}. Open it and check whether a "
        "watermark is visible."
    )


if __name__ == "__main__":
    raise SystemExit(run(test))
