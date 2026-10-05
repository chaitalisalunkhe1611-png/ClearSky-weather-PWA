#!/usr/bin/env python3
"""Smoke test: Groq API (fallback script generator).

    python smoke_tests/test_groq.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import banner, ensure_env_file, fail, load_settings_or_fail, pass_, run  # noqa: E402

GROQ_MODELS_ENDPOINT = "https://api.groq.com/openai/v1/models"
GROQ_CHAT_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
TEST_PROMPT = "Reply with exactly the two words: SMOKE TEST"


def test() -> int:
    import requests

    banner("Groq API smoke test")

    if not ensure_env_file():
        return fail(".env is missing - copy .env.example to .env and fill it in")

    settings, code = load_settings_or_fail()
    if settings is None:
        return code

    if not settings.groq_api_key:
        return fail("GROQ_API_KEY is empty in .env (get one at https://console.groq.com/keys)")
    if not settings.groq_model:
        return fail(
            "GROQ_MODEL is empty in .env. Pick an ID from "
            "https://console.groq.com/docs/models and paste it in."
        )

    print(f"key   : ...{settings.groq_api_key[-4:]}")
    print(f"model : {settings.groq_model}\n")

    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
    timeout = (settings.http_connect_timeout, settings.http_read_timeout)

    # --- 1. list models -------------------------------------------------
    response = requests.get(GROQ_MODELS_ENDPOINT, headers=headers, timeout=timeout)
    if response.status_code != 200:
        body = " ".join(response.text.split())[:400]
        return fail(f"listing models returned HTTP {response.status_code}. Body: {body}")

    listed = sorted(model.get("id", "") for model in response.json().get("data", []))
    print(f"models available to this key: {len(listed)}")
    for name in listed:
        marker = "  <-- GROQ_MODEL" if name == settings.groq_model else ""
        print(f"  - {name}{marker}")
    print()

    if settings.groq_model not in listed:
        return fail(
            f"GROQ_MODEL='{settings.groq_model}' is not in the list above. Copy one "
            "of the exact IDs printed above into .env."
        )

    # --- 2. one real prompt ---------------------------------------------
    response = requests.post(
        GROQ_CHAT_ENDPOINT,
        headers={**headers, "Content-Type": "application/json"},
        json={
            "model": settings.groq_model,
            "messages": [{"role": "user", "content": TEST_PROMPT}],
            "temperature": 0.0,
            "max_tokens": 32,
        },
        timeout=timeout,
    )

    if response.status_code != 200:
        body = " ".join(response.text.split())[:400]
        hint = " You are rate limited." if response.status_code == 429 else ""
        return fail(f"chat completion returned HTTP {response.status_code}.{hint} Body: {body}")

    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        return fail(f"no choices in the response: {str(body)[:300]}")

    reply = ((choices[0].get("message") or {}).get("content") or "").strip()
    if not reply:
        return fail(f"empty content (finish_reason={choices[0].get('finish_reason')})")

    print(f"reply : {reply!r}")
    usage = body.get("usage") or {}
    if usage:
        print(f"tokens: prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')}")

    return pass_(
        f"Groq replied via '{settings.groq_model}'. The fallback script provider works."
    )


if __name__ == "__main__":
    raise SystemExit(run(test))
