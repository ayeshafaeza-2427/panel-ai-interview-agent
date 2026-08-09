"""
AI Provider layer.

    AI Provider
       |
       v
    Question Generation / Answer Evaluation / Follow-up Generation / Final Evaluation

This is the ONLY module in the application that talks to an AI API.
Everything above it (question_engine.py, evaluator.py) calls the single
`generate_json()` function below and never imports a provider SDK
directly - swapping providers is a matter of changing environment
variables, not application code.

Implementation choice: rather than writing a bespoke client per vendor,
this speaks the OpenAI-compatible chat-completions wire format via the
`openai` Python SDK's configurable `base_url`. That one format is
implemented by:

- Google Gemini    (the default here - Gemini API keys are free to
                     create at https://aistudio.google.com/apikey, no
                     credit card required; official OpenAI-compat docs:
                     https://ai.google.dev/gemini-api/docs/openai)
- OpenAI itself
- Together AI, Fireworks, Anyscale, Groq, OpenRouter, and most other
  hosted inference providers
- Local runtimes like Ollama or vLLM (OpenAI-compatible mode)

So "the provider" is fully described by three env vars - AI_API_KEY,
AI_BASE_URL, AI_MODEL - with AI_PROVIDER as a convenience preset that
fills in the base URL/model/key-variable-name defaults for a couple of
well-known providers. No Anthropic-specific (or any other
vendor-specific) code lives anywhere in the application.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

from openai import APIError, OpenAI

logger = logging.getLogger("interview_agent.ai_provider")


# Known providers that speak the OpenAI-compatible format, with sensible
# free-friendly defaults. AI_BASE_URL / AI_MODEL env vars always win over
# these presets if set explicitly. `key_env` is the provider-specific
# API key variable checked as a fallback if the generic AI_API_KEY isn't
# set - this lets a Gemini key just be called GEMINI_API_KEY, as Google's
# own docs use, while the app still works with any OpenAI-compatible
# provider via the generic vars alone.
#
# Model verified against Google's official OpenAI-compatibility docs
# (https://ai.google.dev/gemini-api/docs/openai, last updated 2026-07-21):
# every current example there uses model="gemini-3.6-flash".
_PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-3.6-flash",
        "key_env": "GEMINI_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "key_env": "OPENAI_API_KEY",
    },
}

DEFAULT_PROVIDER = os.environ.get("AI_PROVIDER", "gemini").strip().lower()
_preset = _PROVIDER_PRESETS.get(DEFAULT_PROVIDER, {})

BASE_URL = os.environ.get("AI_BASE_URL", _preset.get("base_url", ""))
MODEL = os.environ.get("AI_MODEL", _preset.get("model", ""))
MAX_TOKENS = int(os.environ.get("AI_MAX_TOKENS", "1024"))
TEMPERATURE = float(os.environ.get("AI_TEMPERATURE", "0.7"))


class AIProviderUnavailableError(RuntimeError):
    """Raised when the AI API call fails after retries (network/auth/etc)."""


class AIProviderMalformedResponseError(RuntimeError):
    """Raised when the model's output can't be parsed/validated as JSON."""


def _resolve_api_key() -> str | None:
    """AI_API_KEY (generic) wins if set; otherwise fall back to the active
    preset's provider-specific key variable (e.g. GEMINI_API_KEY)."""
    generic = os.environ.get("AI_API_KEY")
    if generic:
        return generic
    key_env = _preset.get("key_env")
    if key_env:
        return os.environ.get(key_env)
    return None


def _get_client() -> OpenAI:
    api_key = _resolve_api_key()
    if not api_key:
        key_env = _preset.get("key_env", "AI_API_KEY")
        raise AIProviderUnavailableError(
            f"No API key found. Set {key_env} (or the generic AI_API_KEY) "
            "in your .env file (see .env.example) - get a free Gemini API "
            "key at https://aistudio.google.com/apikey (no credit card "
            "required), or point AI_PROVIDER/AI_BASE_URL/AI_MODEL at any "
            "other OpenAI-compatible provider."
        )
    if not BASE_URL or not MODEL:
        raise AIProviderUnavailableError(
            f"AI_PROVIDER='{DEFAULT_PROVIDER}' is not a known preset and "
            "AI_BASE_URL/AI_MODEL were not set explicitly. Set AI_PROVIDER "
            f"to one of {list(_PROVIDER_PRESETS)}, or set AI_BASE_URL and "
            "AI_MODEL directly for a custom OpenAI-compatible endpoint."
        )
    return OpenAI(api_key=api_key, base_url=BASE_URL)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _call_model(client: OpenAI, system_prompt: str, user_prompt: str, use_json_mode: bool) -> str:
    kwargs: dict[str, Any] = dict(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    if use_json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        completion = client.chat.completions.create(**kwargs)
    except APIError as exc:
        if use_json_mode:
            # Some OpenAI-compatible providers/models reject the
            # response_format param even though they otherwise support
            # the chat-completions format. Fall back to plain prompting
            # (the JSON-extraction/retry logic below still applies).
            logger.info(
                "Provider rejected response_format=json_object, retrying "
                "without it: %s",
                exc,
            )
            return _call_model(client, system_prompt, user_prompt, use_json_mode=False)
        logger.error("AI provider API error: %s", exc)
        raise AIProviderUnavailableError(f"AI provider API call failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - network/auth errors etc.
        logger.error("AI provider request failed: %s", exc)
        raise AIProviderUnavailableError(f"AI provider request failed: {exc}") from exc

    return (completion.choices[0].message.content or "").strip()


def generate_json(
    system_prompt: str,
    user_prompt: str,
    validator: Callable[[dict], bool] | None = None,
    max_retries: int = 1,
) -> dict[str, Any]:
    """
    Calls the configured AI provider expecting a single JSON object back.
    Validates the parsed JSON with `validator` if provided. Retries once
    with a corrective instruction if parsing/validation fails, then
    raises. Provider-agnostic: works against any OpenAI-compatible
    endpoint configured via AI_API_KEY / AI_BASE_URL / AI_MODEL (or a
    provider preset via AI_PROVIDER).
    """
    client = _get_client()
    attempt_prompt = user_prompt
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        raw_text = _call_model(client, system_prompt, attempt_prompt, use_json_mode=True)
        cleaned = _strip_code_fences(raw_text)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning("Malformed JSON from AI provider (attempt %s): %s", attempt + 1, exc)
            attempt_prompt = (
                user_prompt
                + "\n\nYour previous reply was not valid JSON. "
                "Reply with ONLY a single valid JSON object, no prose, "
                "no markdown fences."
            )
            continue

        if validator is not None and not validator(parsed):
            last_error = AIProviderMalformedResponseError("Response JSON failed schema validation")
            logger.warning("AI provider JSON failed validation (attempt %s): %s", attempt + 1, parsed)
            attempt_prompt = (
                user_prompt
                + f"\n\nYour previous reply did not match the required JSON "
                f"shape. You returned: {json.dumps(parsed)}\n"
                "Reply again with ONLY a single valid JSON object matching "
                "the required fields exactly."
            )
            continue

        return parsed

    raise AIProviderMalformedResponseError(
        f"AI provider did not return valid/expected JSON after "
        f"{max_retries + 1} attempts: {last_error}"
    )
