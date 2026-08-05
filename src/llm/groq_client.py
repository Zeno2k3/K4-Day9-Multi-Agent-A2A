"""Thin wrapper around Groq's OpenAI-compatible chat completions endpoint.

Every agent's LLM call goes through here so retry/backoff, JSON-mode, and
graceful degradation (never crash a case) are handled in exactly one place.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from openai import APIError, APIStatusError, APITimeoutError, OpenAI

from src.config import (
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MODEL,
    LLM_MAX_RETRIES,
    LLM_MIN_INTERVAL_SECONDS,
    LLM_RETRY_BASE_DELAY_SECONDS,
    LLM_TIMEOUT_SECONDS,
)


@dataclass
class LlmCallResult:
    success: bool
    parsed: dict[str, Any] | None
    prompt_excerpt: str
    response_excerpt: str
    attempt: int
    latency_ms: int
    error: str | None


class GroqClient:
    def __init__(self, force_unavailable: bool = False) -> None:
        self._client: OpenAI | None = None
        self._last_call_ts = 0.0
        if GROQ_API_KEY and not force_unavailable:
            self._client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL, timeout=LLM_TIMEOUT_SECONDS)

    @property
    def available(self) -> bool:
        return self._client is not None

    def _pace(self) -> None:
        elapsed = time.monotonic() - self._last_call_ts
        if elapsed < LLM_MIN_INTERVAL_SECONDS:
            time.sleep(LLM_MIN_INTERVAL_SECONDS - elapsed)

    def call_json(self, system_prompt: str, user_payload: dict[str, Any]) -> LlmCallResult:
        """Calls the model in JSON mode. Returns success=False (never
        raises) if the API is unreachable, rate-limited past retry budget,
        or returns unparseable JSON — callers fall back to the deterministic
        value in that case."""
        prompt_excerpt = (system_prompt + "\n" + json.dumps(user_payload, ensure_ascii=False))[:800]
        if self._client is None:
            return LlmCallResult(False, None, prompt_excerpt, "", 0, 0, "no_api_key")

        last_error = "unknown"
        start = time.monotonic()
        for attempt in range(1, LLM_MAX_RETRIES + 1):
            self._pace()
            start = time.monotonic()
            try:
                self._last_call_ts = time.monotonic()
                resp = self._client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    max_tokens=300,
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                content = resp.choices[0].message.content or "{}"
                parsed = json.loads(content)
                return LlmCallResult(
                    True, parsed, prompt_excerpt, content[:500], attempt, latency_ms, None
                )
            except json.JSONDecodeError as exc:
                last_error = f"json_decode_error: {exc}"
            except APITimeoutError as exc:
                last_error = f"timeout: {exc}"
            except APIStatusError as exc:
                last_error = f"status_{exc.status_code}: {exc}"
            except APIError as exc:
                last_error = f"api_error: {exc}"
            except Exception as exc:  # noqa: BLE001 - one bad LLM call must never crash a case
                last_error = f"unexpected: {exc}"
            time.sleep(LLM_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))

        latency_ms = int((time.monotonic() - start) * 1000)
        return LlmCallResult(
            False, None, prompt_excerpt, "", LLM_MAX_RETRIES, latency_ms, last_error
        )
