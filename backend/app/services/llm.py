"""LLM access layer.

* Primary provider: Anthropic Claude (``ANTHROPIC_MODEL``, default ``claude-opus-5-5``) with
  structured JSON outputs, adaptive thinking/effort control and server-side refusal fallback.
* Secondary provider: OpenAI chat-completions (``OPENAI_API_KEY``), used when Claude errors out.
* When no provider is configured, :class:`LLMUnavailable` is raised and every service falls back
  to deterministic heuristics so the product still works offline.

Retry policy (PLAN.md §13): LLM API error -> 3 attempts with 1s/2s/4s backoff, then fall back to
the secondary provider.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

JSON_RULE = (
    "\n\n═══════════════════════════════════════════════════════════════════\n"
    "OUTPUT FORMAT\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "Every task you receive through this API expects a single JSON object as the complete "
    "response. Do not wrap it in markdown fences and do not add commentary before or after it."
)

REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    """Generic LLM failure."""


class LLMUnavailable(LLMError):
    """No LLM provider is configured (or all providers failed)."""


class LLMRefusal(LLMError):
    """The model declined the request."""


# --------------------------------------------------------------------------- prompts
@lru_cache(maxsize=64)
def load_prompt(name: str) -> str:
    path = Path(settings.PROMPTS_DIR) / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def render_prompt(name: str, **variables: Any) -> str:
    template = load_prompt(name)

    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        value = variables.get(key, "")
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str)
        return "" if value is None else str(value)

    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", _sub, template)


def system_prompt() -> str:
    return load_prompt("master_system") + JSON_RULE


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object out of a model response, tolerating fences or stray prose."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("Model response did not contain JSON") from None
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model response contained invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise LLMError("Model response JSON was not an object")
    return value


# --------------------------------------------------------------------------- providers
class Provider(Protocol):
    name: str

    def complete(
        self, system: str, prompt: str, schema: dict[str, Any] | None, effort: str | None, max_tokens: int | None
    ) -> str: ...


class AnthropicProvider:
    """Claude via the official ``anthropic`` SDK (streaming + ``get_final_message``)."""

    name = "anthropic"

    # Optional request features we can drop if a configured model rejects them.
    _disabled_features: set[str] = set()
    _features_lock = threading.Lock()

    def __init__(self) -> None:
        import anthropic

        self._anthropic = anthropic
        # We implement the retry policy ourselves (1s/2s/4s) so the SDK should not retry too.
        self.client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY, timeout=settings.LLM_TIMEOUT_SECONDS, max_retries=0
        )

    def _disable(self, feature: str) -> None:
        with self._features_lock:
            self._disabled_features.add(feature)
        logger.warning("Anthropic model %s rejected feature '%s'; disabling it", settings.ANTHROPIC_MODEL, feature)

    def _request(
        self, system: str, prompt: str, schema: dict[str, Any] | None, effort: str | None, max_tokens: int | None
    ) -> Any:
        disabled = self._disabled_features
        output_config: dict[str, Any] = {}
        if effort and "effort" not in disabled:
            output_config["effort"] = effort
        if schema and "format" not in disabled:
            output_config["format"] = {"type": "json_schema", "schema": schema}

        kwargs: dict[str, Any] = {
            "model": settings.ANTHROPIC_MODEL,
            "max_tokens": max_tokens or settings.ANTHROPIC_MAX_TOKENS,
            # The master prompt is stable across calls -> cache it.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": prompt}],
        }
        if output_config:
            kwargs["output_config"] = output_config

        if settings.ANTHROPIC_REFUSAL_FALLBACK and "fallbacks" not in disabled:
            stream = self.client.beta.messages.stream(
                betas=[REFUSAL_FALLBACK_BETA], fallbacks="default", **kwargs
            )
        else:
            stream = self.client.messages.stream(**kwargs)
        with stream as s:
            return s.get_final_message()

    def complete(
        self, system: str, prompt: str, schema: dict[str, Any] | None, effort: str | None, max_tokens: int | None
    ) -> str:
        anthropic = self._anthropic
        for _ in range(4):  # at most one downgrade per optional feature
            try:
                message = self._request(system, prompt, schema, effort, max_tokens)
                break
            except anthropic.BadRequestError as exc:
                text = str(exc).lower()
                if "fallback" in text and "fallbacks" not in self._disabled_features:
                    self._disable("fallbacks")
                elif ("output_config.format" in text or "json_schema" in text or "schema" in text) and schema and (
                    "format" not in self._disabled_features
                ):
                    self._disable("format")
                elif "effort" in text and "effort" not in self._disabled_features:
                    self._disable("effort")
                else:
                    raise
        else:  # pragma: no cover - defensive
            raise LLMError("Anthropic request could not be completed")

        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            raise LLMRefusal(f"Claude declined the request ({getattr(details, 'category', None)})")
        if message.stop_reason == "max_tokens":
            raise LLMError("Claude response was truncated (max_tokens)")
        text = "".join(block.text for block in message.content if getattr(block, "type", None) == "text")
        if not text.strip():
            raise LLMError("Claude returned an empty response")
        usage = getattr(message, "usage", None)
        if usage is not None:
            logger.debug(
                "claude usage in=%s out=%s cache_read=%s",
                getattr(usage, "input_tokens", None),
                getattr(usage, "output_tokens", None),
                getattr(usage, "cache_read_input_tokens", None),
            )
        return text

    def is_retryable(self, exc: Exception) -> bool:
        a = self._anthropic
        if isinstance(exc, (a.RateLimitError, a.APIConnectionError, a.APITimeoutError, a.InternalServerError)):
            return True
        return isinstance(exc, a.APIStatusError) and exc.status_code >= 500


class OpenAIProvider:
    """OpenAI chat-completions over REST (secondary provider)."""

    name = "openai"

    def complete(
        self, system: str, prompt: str, schema: dict[str, Any] | None, effort: str | None, max_tokens: int | None
    ) -> str:
        body: dict[str, Any] = {
            "model": settings.OPENAI_MODEL,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": min(max_tokens or 8000, 16000),
        }
        if schema is not None:
            body["response_format"] = {"type": "json_object"}
        response = httpx.post(
            f"{settings.OPENAI_BASE_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            json=body,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            raise LLMError(f"OpenAI error {response.status_code}: {response.text[:300]}")
        data = response.json()
        return data["choices"][0]["message"]["content"] or ""

    def is_retryable(self, exc: Exception) -> bool:
        if isinstance(exc, httpx.TransportError):
            return True
        return isinstance(exc, LLMError) and bool(re.search(r"error (429|5\d\d)", str(exc)))


# --------------------------------------------------------------------------- client
class LLMClient:
    def __init__(self, providers: list[Any] | None = None) -> None:
        if providers is None:
            providers = []
            if settings.ANTHROPIC_API_KEY:
                providers.append(AnthropicProvider())
            if settings.OPENAI_API_KEY:
                providers.append(OpenAIProvider())
        self.providers = providers

    @property
    def available(self) -> bool:
        return bool(self.providers)

    @property
    def provider_names(self) -> list[str]:
        return [p.name for p in self.providers]

    def _call_with_retries(self, provider: Any, call: Any) -> str:
        delays = [1, 2, 4][: max(settings.LLM_MAX_RETRIES - 1, 0)]
        attempt = 0
        while True:
            try:
                return call()
            except LLMRefusal:
                raise
            except Exception as exc:
                retryable = getattr(provider, "is_retryable", lambda e: False)(exc)
                if not retryable or attempt >= len(delays):
                    raise
                logger.warning("%s call failed (%s); retrying in %ss", provider.name, exc, delays[attempt])
                time.sleep(delays[attempt])
                attempt += 1

    def complete_json(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        effort: str | None = None,
        max_tokens: int | None = None,
        task: str = "task",
    ) -> dict[str, Any]:
        if not self.providers:
            raise LLMUnavailable("No LLM provider configured (set ANTHROPIC_API_KEY or OPENAI_API_KEY)")
        system = system_prompt()
        errors: list[str] = []
        for provider in self.providers:
            try:
                text = self._call_with_retries(
                    provider,
                    lambda p=provider: p.complete(
                        system, prompt, schema, effort or settings.ANTHROPIC_EFFORT, max_tokens
                    ),
                )
                return extract_json(text)
            except Exception as exc:  # noqa: BLE001 - try the next provider
                logger.warning("LLM provider %s failed on %s: %s", provider.name, task, exc)
                errors.append(f"{provider.name}: {exc}")
        raise LLMUnavailable("All LLM providers failed: " + " | ".join(errors))


_client: LLMClient | None = None
_client_lock = threading.Lock()


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = LLMClient()
    return _client


def set_llm(client: LLMClient | None) -> None:
    """Override the process-wide client (tests / scripts)."""
    global _client
    _client = client
