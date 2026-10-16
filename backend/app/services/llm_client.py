"""Model-provider fallback for files whose authors wrote no usable documentation.

This module runs on the API side only. The E2B sandbox never receives provider
credentials, so every call here happens after a scan payload has returned.

Design rules:

* The provider is a fallback, never a dependency. Any failure degrades to
  "no description" plus a recorded reason, and never propagates.
* Only files with no authored documentation reach this module at all; the
  caller decides that. See :func:`app.services.file_describer.needs_model`.
* The raw assistant message and token usage are returned alongside the parsed
  fields so the caller can store them for audit.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.ingestion.file_docs import llm_fallback_available

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"

MAX_EXCERPT_CHARS = 12_000
MAX_SUMMARY_CHARS = 400
MAX_SYMBOLS = 25

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 2

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

PROMPT_TEMPLATE = """\
You are documenting a single file from an open-source repository so that a \
developer can decide whether to read it before changing related code.

Rules:
- Describe only what this file actually contains. Do not guess, and do not \
mention functionality you cannot see.
- Prefer naming the responsibility of the file and its main public symbols.
- Use at most {max_summary} characters for the summary.
- List at most {max_symbols} public symbols, most important first.
- Reply with JSON only, no prose and no code fences, using exactly these keys:
  {{"summary": "...", "symbols": ["...", "..."]}}

Language: {language}
Path: {path}

----- file contents -----
{excerpt}
----- end of file -----
"""


@dataclass
class ModelDescription:
    """A parsed model answer plus everything needed to audit it."""

    summary: str
    symbols: List[str]
    model: str
    raw_response: str
    usage: Dict[str, Any] = field(default_factory=dict)
    prompt_version: str = PROMPT_VERSION
    input_chars: int = 0


@dataclass
class ModelFailure:
    """Why no description was produced. Carries no credentials."""

    reason: str
    detail: str = ""
    attempts: int = 0

    @property
    def ok(self) -> bool:
        return False


Result = Any  # ModelDescription | ModelFailure


def build_excerpt(text: str, limit: int = MAX_EXCERPT_CHARS) -> str:
    """Bound the text sent to the provider."""
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [truncated for length] ..."


def build_prompt(excerpt: str, path: str, language: str = "") -> str:
    return PROMPT_TEMPLATE.format(
        max_summary=MAX_SUMMARY_CHARS,
        max_symbols=MAX_SYMBOLS,
        language=language or "unknown",
        path=path,
        excerpt=excerpt,
    )


def parse_response(content: str) -> Optional[Dict[str, Any]]:
    """Parse the model's reply, tolerating fences and surrounding prose."""
    if not content:
        return None

    candidates = [content.strip()]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())
    block = _JSON_BLOCK.search(content)
    if block:
        candidates.append(block.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict) and parsed.get("summary"):
            return parsed
    return None


def _clean_symbols(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    symbols: List[str] = []
    seen = set()
    for item in value:
        if not isinstance(item, str):
            continue
        name = " ".join(item.split()).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        symbols.append(name)
        if len(symbols) >= MAX_SYMBOLS:
            break
    return symbols


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
    return {
        key: usage.get(key)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if usage.get(key) is not None
    }


def _chat(messages: List[Dict[str, str]], timeout: int, max_retries: int) -> Any:
    """One chat completion, retried on transient provider errors."""
    from openai import OpenAI

    try:
        client = OpenAI(
            api_key=settings.NEBIUS_API_KEY,
            base_url=settings.NEBIUS_API_BASE_URL,
            timeout=timeout,
            max_retries=0,  # retries are handled here so failures stay typed
        )
    except Exception as exc:
        raise ModelCallError(f"provider client could not be created: {exc}") from exc

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 2):
        try:
            return client.chat.completions.create(
                model=settings.NEBIUS_MODEL_NAME,
                messages=messages,
                temperature=0.1,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # provider/transport errors are all typed
            last_error = exc
            name = type(exc).__name__
            if "RateLimit" in name or "Timeout" in name or "APIConnection" in name:
                logger.warning(
                    "provider attempt %s/%s failed (%s); retrying",
                    attempt,
                    max_retries + 1,
                    name,
                )
                continue
            break

    raise ModelCallError(str(last_error)) from last_error


class ModelCallError(RuntimeError):
    """A provider call that did not return a usable answer."""


def describe_file(
    text: str,
    path: str,
    language: str = "",
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> Result:
    """Describe one file with the configured model.

    Returns a :class:`ModelDescription` or a :class:`ModelFailure`. It never
    raises, so a provider outage cannot fail an ingestion.
    """
    if not llm_fallback_available(settings.NEBIUS_API_KEY):
        return ModelFailure(
            reason="no_provider_key",
            detail="NEBIUS_API_KEY is unset or still a placeholder",
        )

    excerpt = build_excerpt(text)
    if not excerpt.strip():
        return ModelFailure(reason="empty_excerpt", detail="no source text to send")

    prompt = build_prompt(excerpt, path, language)
    messages = [
        {
            "role": "system",
            "content": "You document source files. You always answer with JSON.",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        completion = _chat(messages, timeout, max_retries)
    except ModelCallError as exc:
        logger.warning("model call failed for %s: %s", path, exc)
        return ModelFailure(reason="provider_error", detail=str(exc)[:400])
    except Exception as exc:  # the fallback must never fail an ingestion
        logger.warning("unexpected model client error for %s: %s", path, exc)
        return ModelFailure(reason="provider_client_error", detail=f"{type(exc).__name__}: {exc}"[:400])

    choices = getattr(completion, "choices", None) or []
    if not choices:
        return ModelFailure(reason="empty_response", detail="provider returned no choices")

    raw_content = getattr(choices[0].message, "content", None) or ""
    parsed = parse_response(raw_content)
    if parsed is None:
        return ModelFailure(
            reason="unparsable_response",
            detail=raw_content[:400],
        )

    summary = " ".join(str(parsed.get("summary", "")).split()).strip()
    if not summary:
        return ModelFailure(reason="empty_summary", detail=raw_content[:400])

    return ModelDescription(
        summary=summary[:MAX_SUMMARY_CHARS],
        symbols=_clean_symbols(parsed.get("symbols")),
        model=settings.NEBIUS_MODEL_NAME,
        raw_response=raw_content,
        usage=_normalise_usage(getattr(completion, "usage", None)),
        input_chars=len(excerpt),
    )