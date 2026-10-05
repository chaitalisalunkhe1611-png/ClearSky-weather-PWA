#!/usr/bin/env python3
"""Smoke test: Cloudflare Workers AI (fallback image generator).

This provider is optional. If CF_API_TOKEN is not set, the test reports a skip
and exits 0 rather than failing - but if any of the three Cloudflare values IS
set while another is missing, that is a real configuration error and the test
fails.

    python smoke_tests/test_cloudflare.py
"""

from __future__ import annotations

import base64
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

TEST_PROMPT = (
    "a friendly round robot with a dented copper body and one crooked antenna, "
    "standing in a sunlit meadow, flat vector illustration, bold outlines, "
    "warm palette"
)


def test() -> int:
    import requests

    from image_generator import CLOUDFLARE_ENDPOINT, sniff_image_suffix

    banner("Cloudflare Workers AI smoke test")

    if not ensure_env_file():
        print("note: continuing anyway - this test reads values from the environment.\n")

    settings, code = load_settings_or_fail()
    if settings is None:
        return code

    configured = {
        "CF_ACCOUNT_ID": bool(settings.cf_account_id),
        "CF_API_TOKEN": bool(settings.cf_api_token),
        "CF_IMAGE_MODEL": bool(settings.cf_image_model),
    }

    if not any(configured.values()):
        return pass_(
            "skipped - none of CF_ACCOUNT_ID / CF_API_TOKEN / CF_IMAGE_MODEL is set, "
            "so the optional Cloudflare fallback is simply not configured. The "
            "pipeline will run on Pollinations alone. This is not a failure."
        )

    missing = [name for name, present in configured.items() if not present]
    if missing:
        return fail(
            "the Cloudflare fallback is partially configured. Missing: "
            + ", ".join(missing)
            + ". Set all three in .env, or clear all three to disable the fallback "
            "cleanly. Free tier: 10,000 Neurons/day."
        )

    print(f"account : ...{settings.cf_account_id[-4:]}")
    print(f"token   : ...{settings.cf_api_token[-4:]}")
    print(f"model   : {settings.cf_image_model}\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    model_path = settings.cf_image_model.lstrip("/")
    url = f"{CLOUDFLARE_ENDPOINT}/{settings.cf_account_id}/ai/run/{model_path}"

    print(f"POST {CLOUDFLARE_ENDPOINT}/<account>/ai/run/{model_path}\n")

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {settings.cf_api_token}",
            "Content-Type": "application/json",
        },
        json={
            "prompt": TEST_PROMPT,
            "seed": 12345,
            "width": settings.video_width,
            "height": settings.video_height,
        },
        timeout=(settings.http_connect_timeout, settings.http_read_timeout),
    )

    print(f"HTTP status  : {response.status_code}")
    print(f"Content-Type : {response.headers.get('Content-Type', '<none>')}\n")

    if response.status_code == 401:
        return fail(
            "HTTP 401 - the API token was rejected. Check that it is a Workers AI "
            "token and that CF_ACCOUNT_ID belongs to the same account."
        )
    if response.status_code == 403:
        return fail(
            "HTTP 403 - the token lacks the Workers AI permission. Recreate it from "
            "the 'Workers AI' template in My Profile -> API Tokens."
        )
    if response.status_code == 429:
        return fail(
            "HTTP 429 - the daily free allowance (10,000 Neurons, shared across all "
            "Workers AI models) is exhausted. It resets daily."
        )
    if response.status_code != 200:
        body = " ".join(response.text.split())[:400]
        return fail(f"unexpected HTTP {response.status_code}. Body: {body}")

    content_type = response.headers.get("Content-Type", "")

    if content_type.startswith("image/"):
        data = response.content
    else:
        try:
            body = response.json()
        except ValueError:
            return fail(f"response was neither an image nor JSON: {response.content[:200]!r}")

        if not body.get("success", True):
            return fail(f"API reported failure: {str(body.get('errors') or body)[:400]}")

        result = body.get("result") or {}
        encoded = result.get("image") or result.get("data")
        if not encoded:
            return fail(
                "no 'image' field in result. Present keys: "
                f"{sorted(result) if isinstance(result, dict) else type(result).__name__}. "
                "Check that CF_IMAGE_MODEL is an image model, not a text model."
            )
        if encoded.startswith("data:"):
            encoded = encoded.split(",", 1)[-1]
        try:
            data = base64.b64decode(encoded, validate=True)
        except Exception as exc:  # noqa: BLE001
            return fail(f"'image' field was not valid base64: {exc}")

    suffix = sniff_image_suffix(data)
    if suffix is None:
        return fail("decoded payload is not a recognised image format")

    dest = OUTPUT_DIR / f"cloudflare_test{suffix}"
    dest.write_bytes(data)

    return pass_(
        f"Cloudflare returned a valid {suffix} image "
        f"({len(data) // 1024} KB) from '{settings.cf_image_model}', saved to "
        f"{dest.relative_to(dest.parents[2])}"
    )


if __name__ == "__main__":
    raise SystemExit(run(test))
