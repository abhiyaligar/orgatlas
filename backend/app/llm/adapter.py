"""Nebius adapter for answer synthesis.

The model writes prose. It does not decide what is true: the facts and the
citable sources come from FalkorDB, and every citation the model emits is
validated against them afterwards.

Two behaviours here are not boilerplate:

* The configured model is a reasoning model. It spends completion tokens
  before it answers, so the completion allowance must leave real headroom or
  the provider returns an empty completion. Thinking tokens are also reported,
  because for this model they dominate the cost.
* No failure reaches the caller. A timeout, a rate limit or an outage becomes
  a ``SynthesisFailure`` so the ask path can answer deterministically instead
  of failing.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from app.core.config import settings
from app.ingestion.file_docs import llm_fallback_available
from app.llm.client import SynthesisFailure, SynthesisRequest, SynthesisSuccess

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_RETRIES = 2
DEFAULT_MAX_TOKENS = 2048

# Errors worth retrying: the provider is transiently unable, not refusing.
RETRYABLE = ("RateLimit", "Timeout", "APIConnection", "InternalServerError", "ServiceUnavailable")


class NebiusLLMAdapter:
    """Synthesise an answer from retrieved evidence using Nebius inference."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.NEBIUS_API_KEY
        self.base_url = base_url if base_url is not None else settings.NEBIUS_API_BASE_URL
        self.model = model if model is not None else settings.NEBIUS_MODEL_NAME
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_tokens = max_tokens

    # --- availability --------------------------------------------------------

    @property
    def available(self) -> bool:
        """True only when a real key is configured.

        A placeholder key must never reach the network, or every answer would
        pay a failed request for a guaranteed 401.
        """
        return llm_fallback_available(self.api_key)

    # --- synthesis -----------------------------------------------------------

    async def generate_synthesis(self, request: SynthesisRequest) -> Any:
        from app.llm.prompts import build_synthesis_messages

        if not self.available:
            return SynthesisFailure(
                reason="no_provider_key",
                detail="NEBIUS_API_KEY is unset or still a placeholder",
            )

        messages = build_synthesis_messages(request)
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 2):
            try:
                completion = await self._complete(messages)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                name = type(exc).__name__
                if any(marker in name for marker in RETRYABLE):
                    logger.warning(
                        "synthesis attempt %s/%s failed (%s)", attempt, self.max_retries + 1, name
                    )
                    continue
                break

            outcome = self._interpret(completion)
            if isinstance(outcome, SynthesisFailure):
                # A budget-exhausted completion is worth one more attempt with a
                # larger allowance rather than a silent deterministic answer.
                if outcome.reason == "reasoning_budget_exhausted" and attempt == 1:
                    self.max_tokens = self.max_tokens * 2
                    logger.warning(
                        "model spent its completion budget reasoning; retrying with %s tokens",
                        self.max_tokens,
                    )
                    continue
                return outcome
            return outcome

        return SynthesisFailure(
            reason="provider_error",
            detail=f"{type(last_error).__name__}: {last_error}"[:400] if last_error else "unknown",
            attempts=self.max_retries + 1,
        )

    async def _complete(self, messages: List[Dict[str, str]]) -> Any:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=0,  # retries are handled here so failures stay typed
        )
        return await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            max_tokens=self.max_tokens,
        )

    # --- response interpretation --------------------------------------------

    def _interpret(self, completion: Any) -> Any:
        choices = getattr(completion, "choices", None) or []
        if not choices:
            return SynthesisFailure(reason="empty_response", detail="no choices returned")

        choice = choices[0]
        content = getattr(choice.message, "content", None) or ""

        if not content.strip():
            finish = getattr(choice, "finish_reason", None)
            reasoning = getattr(choice.message, "reasoning_content", None) or ""
            if finish in ("length", "max_tokens") or reasoning:
                return SynthesisFailure(
                    reason="reasoning_budget_exhausted",
                    detail=(
                        f"finish_reason={finish}; the model used its completion budget "
                        "reasoning and returned no answer"
                    ),
                )
            return SynthesisFailure(reason="empty_response", detail="no content returned")

        return SynthesisSuccess(
            answer=content.strip(),
            model=self.model,
            usage=self._normalise_usage(getattr(completion, "usage", None)),
        )

    @staticmethod
    def _normalise_usage(usage: Any) -> Dict[str, Any]:
        if usage is None:
            return {}
        for attribute in ("model_dump", "dict", "to_dict"):
            method = getattr(usage, attribute, None)
            if callable(method):
                try:
                    usage = method()
                except Exception:  # pragma: no cover - defensive
                    continue
                break
        if not isinstance(usage, dict):
            return {}
        normalised = {
            key: usage.get(key)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if usage.get(key) is not None
        }
        details = usage.get("completion_tokens_details") or {}
        if isinstance(details, dict) and details.get("reasoning_tokens") is not None:
            normalised["reasoning_tokens"] = details["reasoning_tokens"]
        return normalised