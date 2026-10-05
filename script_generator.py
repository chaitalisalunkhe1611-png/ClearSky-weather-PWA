"""Turn a one-line premise into a structured, narratable scene script.

Primary provider: Google Gemini (REST, free tier).
Fallback provider: Groq (OpenAI-compatible REST, free tier).

Both are called over plain HTTP with explicit timeouts. No provider SDK is used,
which keeps the failure modes visible and the dependency list short.

Output contract (strict)::

    {"title": str,
     "scenes": [{"scene_number": int, "dialogue": str, "image_prompt": str}, ...]}
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from config import Settings
from utils import (
    ConfigError,
    ExternalServiceError,
    NetworkBlockedError,
    log_fallback,
    request_with_retry,
    response_error_snippet,
)

LOG = logging.getLogger("slideshow.script")

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

# Edge TTS en-US voices at default rate land near this. Used only to convert the
# target duration into a word budget for the prompt -- the authoritative
# duration is always the measured TTS audio length.
ASSUMED_WORDS_PER_MINUTE = 150.0

MIN_WORDS_PER_SCENE = 5
MAX_WORDS_PER_SCENE = 90


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


@dataclass
class WordBudget:
    target: int
    low: int
    high: int


def compute_word_budget(settings: Settings) -> WordBudget:
    """Convert SCENE_COUNT + MIN/MAX_TOTAL_SECONDS into per-scene word counts."""
    scenes = max(1, settings.scene_count)
    low = (settings.min_total_seconds / scenes) * ASSUMED_WORDS_PER_MINUTE / 60.0
    high = (settings.max_total_seconds / scenes) * ASSUMED_WORDS_PER_MINUTE / 60.0
    target = (settings.min_total_seconds + settings.max_total_seconds) / 2.0
    target_words = int(round((target / scenes) * ASSUMED_WORDS_PER_MINUTE / 60.0))
    return WordBudget(
        target=max(MIN_WORDS_PER_SCENE, target_words),
        low=max(MIN_WORDS_PER_SCENE, int(round(low))),
        high=max(MIN_WORDS_PER_SCENE + 1, int(round(high))),
    )


def build_prompt(premise: str, settings: Settings, budget: WordBudget) -> str:
    scenes = settings.scene_count
    return f"""You are a scriptwriter for short narrated slideshows.

PREMISE:
{premise}

Write a {scenes}-scene narrated slideshow.

OUTPUT FORMAT -- return ONE JSON object and nothing else. No markdown fences,
no commentary before or after:

{{
  "title": "a short YouTube title, under 70 characters, no clickbait, no emoji",
  "scenes": [
    {{"scene_number": 1, "dialogue": "...", "image_prompt": "..."}},
    ... exactly {scenes} entries, numbered 1 through {scenes} in order ...
  ]
}}

FIELD RULES

dialogue
- The narration spoken over this scene. Plain prose. No stage directions, no
  speaker labels, no emoji, no quotes around the whole line, no markdown.
- Between {budget.low} and {budget.high} words (aim for {budget.target}).
- Spoken-friendly: short sentences, no parentheticals, no abbreviations that
  a text-to-speech engine would mispronounce. Write "and" instead of "&",
  and spell out numbers under one hundred.
- The {scenes} lines together must tell one continuous story from start to
  finish, in order, with a hook in scene 1 and a closing thought in the last.

image_prompt
- A description of ONE still image, in English, for a text-to-image model.
- It MUST begin with the same verbatim 25-45 word block describing the
  recurring characters and the art style, repeated word for word in every
  single scene. Then add what is different in this scene.
- Repeat that block exactly. Do not paraphrase it, do not shorten it, do not
  reorder it. This is the only defence against the characters drifting
  between images, and it is still only a partial defence.
- After the block, describe the specific action, setting, time of day,
  lighting and camera framing for this scene.
- Landscape 16:9 composition. Keep the main subject near the centre of the
  frame with headroom, because the video zooms and pans into the image and
  anything near the edges may be cropped out.
- Never request text, lettering, captions, logos or watermarks in the image.

ORIGINALITY -- MANDATORY
- Invent every character name yourself. They must be original to this script.
- Do NOT use character names, mascots, catchphrases or settings from any
  existing film, television series, game, book, comic or brand. A name that
  merely resembles a well-known one is also not acceptable.
- Do not describe an existing franchise's art style. Describe a generic style
  instead, for example "flat vector illustration, bold outlines, warm palette".

CONTENT
- Family-friendly and advertiser-safe. No violence, no romance, no politics,
  no real public figures, no medical or financial claims.
"""


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class Scene:
    scene_number: int
    dialogue: str
    image_prompt: str


@dataclass
class ScriptResult:
    title: str
    scenes: list[Scene]
    provider: str
    model: str
    fallback_reason: str | None = None


# ---------------------------------------------------------------------------
# JSON extraction + validation
# ---------------------------------------------------------------------------


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def extract_json_object(raw: str) -> dict[str, Any]:
    """Pull a JSON object out of a model reply, repairing common sloppiness.

    Models sometimes wrap JSON in markdown fences or add a stray sentence. We
    try progressively more aggressive recovery before giving up, because a
    retry costs free-tier quota.
    """
    if not raw or not raw.strip():
        raise ValueError("model returned an empty response")

    candidates: list[str] = [raw.strip()]

    fenced = _FENCE_RE.search(raw)
    if fenced:
        candidates.append(fenced.group(1).strip())

    # Outermost balanced braces.
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])

    for candidate in candidates:
        for text in (candidate, _TRAILING_COMMA_RE.sub(r"\1", candidate)):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    raise ValueError(f"could not parse a JSON object from the reply: {raw[:300]!r}")


def validate_script(payload: dict[str, Any], settings: Settings) -> tuple[str, list[Scene]]:
    """Enforce the output contract. Raises ValueError with a precise reason."""
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("'title' is missing or not a non-empty string")

    raw_scenes = payload.get("scenes")
    if not isinstance(raw_scenes, list):
        raise ValueError("'scenes' is missing or not a list")
    if len(raw_scenes) != settings.scene_count:
        raise ValueError(
            f"expected {settings.scene_count} scenes, model returned {len(raw_scenes)}"
        )

    scenes: list[Scene] = []
    for index, item in enumerate(raw_scenes, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"scene {index} is not an object")

        dialogue = item.get("dialogue")
        if not isinstance(dialogue, str) or not dialogue.strip():
            raise ValueError(f"scene {index} has an empty 'dialogue'")

        image_prompt = item.get("image_prompt")
        if not isinstance(image_prompt, str) or not image_prompt.strip():
            raise ValueError(f"scene {index} has an empty 'image_prompt'")

        words = len(dialogue.split())
        if not (MIN_WORDS_PER_SCENE <= words <= MAX_WORDS_PER_SCENE):
            raise ValueError(
                f"scene {index} dialogue is {words} words, outside the accepted "
                f"{MIN_WORDS_PER_SCENE}-{MAX_WORDS_PER_SCENE} range"
            )

        # scene_number is normalised rather than trusted: models occasionally
        # repeat or skip numbers, and 1..N in order is what the pipeline needs.
        scenes.append(
            Scene(
                scene_number=index,
                dialogue=" ".join(dialogue.split()),
                image_prompt=" ".join(image_prompt.split()),
            )
        )

    return title.strip(), scenes


def warn_about_drift(scenes: list[Scene]) -> None:
    """Report how much shared wording the image prompts actually have.

    We ask for a verbatim repeated character block. Models comply imperfectly.
    Rather than pretending consistency is guaranteed, measure the overlap and
    say so plainly.
    """
    token_lists = [scene.image_prompt.lower().split() for scene in scenes]
    if len(token_lists) < 2:
        return

    shared = 0
    for index in range(min(len(t) for t in token_lists)):
        first = token_lists[0][index]
        if all(tokens[index] == first for tokens in token_lists[1:]):
            shared += 1
        else:
            break

    if shared >= 5:
        LOG.info(
            "Image prompts share a %d-word verbatim opening block. Character "
            "consistency is still not guaranteed, but drift should be reduced.",
            shared,
        )
    else:
        LOG.warning(
            "Image prompts share only a %d-word verbatim opening block. Visual "
            "drift between scenes is LIKELY. Consider regenerating, or lower the "
            "temperature by re-running.",
            shared,
        )


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def _gemini_generate(prompt: str, settings: Settings) -> str:
    model = settings.require_model("GEMINI_MODEL")
    # Gemini model IDs are referenced as "models/<id>"; accept either form so
    # users can paste whichever string the docs show them.
    model_path = model if model.startswith("models/") else f"models/{model}"
    url = f"{GEMINI_ENDPOINT}/{model_path}:generateContent"

    response = request_with_retry(
        "POST",
        url,
        provider="Gemini",
        connect_timeout=settings.http_connect_timeout,
        read_timeout=settings.http_read_timeout,
        max_retries=settings.http_max_retries,
        headers={
            "x-goog-api-key": settings.gemini_api_key,
            "Content-Type": "application/json",
        },
        json={
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.9,
                "maxOutputTokens": 8192,
            },
        },
    )

    if response.status_code != 200:
        raise ExternalServiceError(
            "Gemini",
            f"generateContent failed. Body: {response_error_snippet(response)}",
            status=response.status_code,
        )

    body = response.json()

    block_reason = (body.get("promptFeedback") or {}).get("blockReason")
    if block_reason:
        raise ExternalServiceError(
            "Gemini", f"request was blocked by safety filters (blockReason={block_reason})"
        )

    candidates = body.get("candidates") or []
    if not candidates:
        raise ExternalServiceError("Gemini", "response contained no candidates")

    finish = candidates[0].get("finishReason")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts)

    if not text.strip():
        raise ExternalServiceError(
            "Gemini", f"candidate carried no text (finishReason={finish})"
        )
    if finish == "MAX_TOKENS":
        LOG.warning("Gemini hit MAX_TOKENS; the JSON may be truncated.")

    return text


def _groq_generate(prompt: str, settings: Settings) -> str:
    model = settings.require_model("GROQ_MODEL")

    response = request_with_retry(
        "POST",
        GROQ_ENDPOINT,
        provider="Groq",
        connect_timeout=settings.http_connect_timeout,
        read_timeout=settings.http_read_timeout,
        max_retries=settings.http_max_retries,
        headers={
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You reply with a single valid JSON object and nothing else.",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.9,
            "max_tokens": 8192,
        },
    )

    if response.status_code != 200:
        raise ExternalServiceError(
            "Groq",
            f"chat completion failed. Body: {response_error_snippet(response)}",
            status=response.status_code,
        )

    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        raise ExternalServiceError("Groq", "response contained no choices")

    text = (choices[0].get("message") or {}).get("content") or ""
    if not text.strip():
        raise ExternalServiceError(
            "Groq", f"choice carried no content (finish_reason={choices[0].get('finish_reason')})"
        )
    return text


def _attempt(provider: str, generate, prompt: str, settings: Settings) -> tuple[str, list[Scene], str]:
    """Call one provider and fully validate. Returns (title, scenes, model)."""
    model = (
        settings.require_model("GEMINI_MODEL")
        if provider == "Gemini"
        else settings.require_model("GROQ_MODEL")
    )
    raw = generate(prompt, settings)
    payload = extract_json_object(raw)
    title, scenes = validate_script(payload, settings)
    return title, scenes, model


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_script(premise: str, settings: Settings) -> ScriptResult:
    """Generate the scene script, trying Gemini first and Groq second."""
    if not premise or not premise.strip():
        raise ConfigError("The premise is empty -- give the pipeline something to write about.")

    budget = compute_word_budget(settings)
    prompt = build_prompt(premise.strip(), settings, budget)

    primary_error: Exception | None = None

    if settings.has_gemini:
        try:
            title, scenes, model = _attempt("Gemini", _gemini_generate, prompt, settings)
            warn_about_drift(scenes)
            return ScriptResult(title=title, scenes=scenes, provider="Gemini", model=model)
        except (ExternalServiceError, NetworkBlockedError, ValueError) as exc:
            primary_error = exc
            LOG.warning("Gemini script generation failed: %s", exc)
        except ConfigError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            primary_error = exc
            LOG.warning("Gemini script generation raised an unexpected error: %s", exc)
    else:
        LOG.warning(
            "GEMINI_API_KEY/GEMINI_MODEL are not both set, so the primary script "
            "provider is unavailable. Set them in .env to use Gemini."
        )

    # --- fallback ---
    if settings.has_groq:
        reason = (
            str(primary_error)
            if primary_error
            else "Gemini is not configured (GEMINI_API_KEY / GEMINI_MODEL empty)"
        )
        log_fallback("script", "Gemini", "Groq", reason)
        try:
            title, scenes, model = _attempt("Groq", _groq_generate, prompt, settings)
            warn_about_drift(scenes)
            return ScriptResult(
                title=title,
                scenes=scenes,
                provider="Groq",
                model=model,
                fallback_reason=reason,
            )
        except (ExternalServiceError, NetworkBlockedError, ValueError) as exc:
            raise ExternalServiceError(
                "Groq",
                f"fallback script generation also failed: {exc}"
                + (f" (the primary error was: {primary_error})" if primary_error else ""),
            ) from exc
    else:
        raise ConfigError(
            "Script generation failed and no fallback is available. "
            f"Primary error: {primary_error}. "
            "Set GROQ_API_KEY and GROQ_MODEL in .env to enable the fallback."
        )
