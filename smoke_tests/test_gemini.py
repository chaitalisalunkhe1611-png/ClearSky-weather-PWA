#!/usr/bin/env python3
"""Smoke test: Gemini API (primary script generator).

Lists the models your key can actually see, then sends one real prompt and
prints the reply.

    python smoke_tests/test_gemini.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import banner, ensure_env_file, fail, load_settings_or_fail, pass_, run  # noqa: E402

TEST_PROMPT = "Reply with exactly the two words: SMOKE TEST"


def test() -> int:
    import requests

    from script_generator import GEMINI_ENDPOINT

    banner("Gemini API smoke test")

    if not ensure_env_file():
        return fail(".env is missing - copy .env.example to .env and fill it in")

    settings, code = load_settings_or_fail()
    if settings is None:
        return code

    if not settings.gemini_api_key:
        return fail("GEMINI_API_KEY is empty in .env (get one at https://aistudio.google.com/apikey)")
    if not settings.gemini_model:
        return fail(
            "GEMINI_MODEL is empty in .env. Look up a model that is free right "
            "now at https://ai.google.dev/gemini-api/docs/pricing and paste the "
            "exact model ID."
        )

    print(f"key   : ...{settings.gemini_api_key[-4:]}")
    print(f"model : {settings.gemini_model}\n")

    headers = {"x-goog-api-key": settings.gemini_api_key}
    timeout = (settings.http_connect_timeout, settings.http_read_timeout)

    # --- 1. list models -------------------------------------------------
    listed: list[str] = []
    url = f"{GEMINI_ENDPOINT}?pageSize=200"
    for _ in range(5):
        response = requests.get(url, headers=headers, timeout=timeout)

        if response.status_code != 200:
            body = " ".join(response.text.split())[:400]
            if response.status_code in (400, 403):
                return fail(
                    f"listing models returned HTTP {response.status_code}. The key is "
                    f"probably invalid or lacks access. Body: {body}"
                )
            return fail(f"listing models returned HTTP {response.status_code}. Body: {body}")

        body = response.json()
        for model in body.get("models", []):
            methods = model.get("supportedGenerationMethods", [])
            if "generateContent" in methods:
                listed.append(model.get("name", "").removeprefix("models/"))
        token = body.get("nextPageToken")
        if not token:
            break
        url = f"{GEMINI_ENDPOINT}?pageSize=200&pageToken={token}"

    print(f"models available to this key that support generateContent: {len(listed)}")
    for name in listed:
        marker = "  <-- GEMINI_MODEL" if name == settings.gemini_model else ""
        print(f"  - {name}{marker}")
    print()

    if settings.gemini_model not in listed:
        return fail(
            f"GEMINI_MODEL='{settings.gemini_model}' is not in the list above. "
            "Pick one of the IDs printed above (they must match exactly) and put "
            "it in .env. If the list is empty, your project has no free-tier "
            "access to any text model."
        )

    # --- 2. one real prompt ---------------------------------------------
    model_path = settings.gemini_model
    if not model_path.startswith("models/"):
        model_path = f"models/{model_path}"

    response = requests.post(
        f"{GEMINI_ENDPOINT}/{model_path}:generateContent",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "contents": [{"role": "user", "parts": [{"text": TEST_PROMPT}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 32},
        },
        timeout=timeout,
    )

    if response.status_code != 200:
        body = " ".join(response.text.split())[:400]
        hint = ""
        if response.status_code == 429:
            hint = (
                " You are rate limited. Free-tier limits apply per Google Cloud "
                "project, not per API key, and reset at midnight Pacific."
            )
        return fail(f"generateContent returned HTTP {response.status_code}.{hint} Body: {body}")

    body = response.json()
    candidates = body.get("candidates") or []
    if not candidates:
        return fail(f"no candidates in the response: {str(body)[:300]}")

    parts = (candidates[0].get("content") or {}).get("parts") or []
    reply = "".join(part.get("text", "") for part in parts).strip()

    if not reply:
        return fail(
            f"model returned no text (finishReason={candidates[0].get('finishReason')})"
        )

    print(f"reply : {reply!r}")
    usage = body.get("usageMetadata") or {}
    if usage:
        print(
            f"tokens: prompt={usage.get('promptTokenCount')} "
            f"output={usage.get('candidatesTokenCount')}"
        )

    return pass_(
        f"Gemini replied via '{settings.gemini_model}'. Model list and one real "
        "generation both work."
    )


if __name__ == "__main__":
    raise SystemExit(run(test))
