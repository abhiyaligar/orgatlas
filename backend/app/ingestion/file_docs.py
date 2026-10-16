"""Describe source files from content the repository authors already wrote.

The extractor deliberately prefers authored text over anything generated:

1. A Rust module's ``//!`` or ``/*! ... */`` inner documentation.
2. Otherwise the ``///`` or ``/** ... */`` block attached to its first public item.
3. Otherwise, for Markdown, the first real paragraph below the title.

Public symbol names are read from the declaration itself, so a file with no
prose still yields something an agent can act on.

No network or model call happens here. The optional model fallback lives in
:func:`llm_fallback_available` and is inert until a real provider key is
configured.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# A Rust public declaration at the start of a line, ignoring indentation.
RUST_PUBLIC_ITEM = re.compile(
    r"^[ \t]*pub(?:\s*\([^)]*\))?[ \t]+"
    r"(?:async[ \t]+|unsafe[ \t]+|const[ \t]+|extern[ \t]+\"[^\"]+\"[ \t]+)*"
    r"(fn|struct|enum|trait|impl|mod|const|static|type|union|use)\b"
    r"[ \t]*(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)

INNER_LINE_DOC = re.compile(r"^[ \t]*//!(.*)$")
INNER_BLOCK_DOC = re.compile(r"/\*!(.*?)\*/", re.DOTALL)
OUTER_BLOCK_DOC = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)

MARKDOWN_HEADING = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
MARKDOWN_FENCE = re.compile(r"^[ \t]*(```|~~~)")
MARKDOWN_LINK_ONLY = re.compile(r"^[ \t]*\[.*\]\(.*\)[ \t]*$")

TOML_TABLE = re.compile(r"^\[([^\]]+)\][ \t]*$", re.MULTILINE)
YAML_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*):", re.MULTILINE)

MAX_SUMMARY_CHARS = 400
MAX_SYMBOLS = 25

PLACEHOLDER_KEYS = frozenset(
    {"", "your_nebius_api_key", "your_api_key", "none", "changeme", "placeholder"}
)


def _clean_doc_lines(lines: List[str]) -> str:
    """Strip comment markers and collapse the block into one paragraph."""
    cleaned: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("///"):
            stripped = stripped[3:]
        elif stripped.startswith("//!"):
            stripped = stripped[3:]
        elif stripped.startswith("//"):
            stripped = stripped[2:]
        cleaned.append(stripped.strip())
    return " ".join(part for part in cleaned if part).strip()


def _truncate(text: str, limit: int = MAX_SUMMARY_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "\u2026"


def rust_module_summary(text: str) -> str:
    """Return the module-level ``//!`` or ``/*! ... */`` documentation."""
    block = _clean_doc_lines(
        [
            match.group(1)
            for match in INNER_BLOCK_DOC.finditer(text)
            if match.start() < len(text) // 2
        ]
    )
    if block:
        return _truncate(block)

    leading: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if leading:
                break
            continue
        # Attributes and inner attributes may precede the module docs.
        if line.startswith("#!["):
            continue
        if line.startswith("//!"):
            leading.append(line)
            continue
        break
    return _truncate(_clean_doc_lines(leading))


def rust_public_symbols(text: str) -> List[str]:
    """Return the names of public Rust declarations, in source order."""
    symbols: List[str] = []
    seen = set()
    for match in RUST_PUBLIC_ITEM.finditer(text):
        name = match.group("name")
        if name in seen:
            continue
        seen.add(name)
        symbols.append(name)
        if len(symbols) >= MAX_SYMBOLS:
            break
    return symbols


def first_item_summary(text: str) -> str:
    """Return the ``///`` block attached to the first documented item."""
    blocks = [
        match.group(1)
        for match in OUTER_BLOCK_DOC.finditer(text)
    ]
    if blocks:
        return _truncate(_clean_doc_lines(blocks[0].splitlines()))

    lines = text.splitlines()
    for index, raw in enumerate(lines):
        if not raw.strip().startswith("///"):
            continue
        block: List[str] = []
        cursor = index
        while cursor < len(lines) and lines[cursor].strip().startswith("///"):
            block.append(lines[cursor])
            cursor += 1
        # Only treat it as item docs when an item actually follows.
        if cursor < len(lines) and lines[cursor].strip():
            return _truncate(_clean_doc_lines(block))
    return ""


def markdown_summary(text: str) -> str:
    """Return the first prose paragraph of a Markdown file."""
    paragraph: List[str] = []
    in_fence = False
    in_front_matter = False
    seen_front_matter_end = False

    for index, raw in enumerate(text.splitlines()):
        line = raw.strip()

        if index == 0 and line in ("---", "+++"):
            in_front_matter = True
            continue
        if in_front_matter:
            if line in ("---", "+++"):
                in_front_matter = False
                seen_front_matter_end = True
            continue
        if not seen_front_matter_end and index == 0:
            # Tolerate a leading blank line before front matter.
            continue

        if MARKDOWN_FENCE.match(raw):
            in_fence = not in_fence
            if paragraph:
                break
            continue
        if in_fence or not line:
            if paragraph:
                break
            continue
        if line.startswith("#"):
            if paragraph:
                break
            continue
        if line.startswith(("-", "*", "+", "|", ">")):
            continue
        if MARKDOWN_LINK_ONLY.match(raw) or line.startswith("!["):
            continue
        if "http" in line and len(line) < 120:
            continue

        paragraph.append(line)
        if sum(len(part) for part in paragraph) > MAX_SUMMARY_CHARS:
            break

    return _truncate(" ".join(paragraph))


def markdown_symbols(text: str) -> List[str]:
    return [match.group(2).strip() for match in MARKDOWN_HEADING.finditer(text)][:MAX_SYMBOLS]


def toml_symbols(text: str) -> List[str]:
    return [match.group(1).strip() for match in TOML_TABLE.finditer(text)][:MAX_SYMBOLS]


def yaml_symbols(text: str) -> List[str]:
    symbols: List[str] = []
    seen = set()
    for line in text.splitlines():
        if line.startswith((" ", "\t", "-")) or "#" in line.split(":", 1)[0]:
            continue
        match = YAML_KEY.match(line)
        if not match:
            continue
        name = match.group(1)
        if name in seen:
            continue
        seen.add(name)
        symbols.append(name)
        if len(symbols) >= MAX_SYMBOLS:
            break
    return symbols


def describe_source(text: str, path: str, language: Optional[str] = None) -> Dict[str, Any]:
    """Describe one source file from its own text.

    Returns ``docs_source`` as ``module`` (module-level inner docs),
    ``item`` (docs on the first item), ``heading``/``key`` (structured files)
    or ``none`` when the file carries no usable description.
    """
    language = (language or "").strip().lower()
    if not text or not text.strip():
        return {"summary": "", "symbols": [], "docs_source": "none", "path": path}

    if language in ("rust", "rs") or path.endswith(".rs"):
        symbols = rust_public_symbols(text)
        summary = rust_module_summary(text)
        docs_source = "module" if summary else ""
        if not summary:
            summary = first_item_summary(text)
            docs_source = "item" if summary else ""
        if not summary and symbols:
            summary = f"{len(symbols)} public Rust item(s): " + ", ".join(symbols[:5])
            docs_source = "declaration"
        return {
            "summary": _truncate(summary),
            "symbols": symbols,
            "docs_source": docs_source or "none",
            "path": path,
        }

    if language in ("markdown", "md") or path.endswith((".md", ".markdown")):
        symbols = markdown_symbols(text)
        summary = markdown_summary(text)
        return {
            "summary": summary,
            "symbols": symbols,
            "docs_source": "heading" if symbols or summary else "none",
            "path": path,
        }

    if path.endswith(".toml"):
        symbols = toml_symbols(text)
        return {
            "summary": f"TOML manifest with {len(symbols)} table(s).",
            "symbols": symbols,
            "docs_source": "key" if symbols else "none",
            "path": path,
        }

    if path.endswith((".yml", ".yaml")):
        symbols = yaml_symbols(text)
        return {
            "summary": f"YAML configuration with {len(symbols)} top-level key(s).",
            "symbols": symbols,
            "docs_source": "key" if symbols else "none",
            "path": path,
        }

    return {"summary": "", "symbols": [], "docs_source": "none", "path": path}


def llm_fallback_available(api_key: Optional[str]) -> bool:
    """True only when a real model-provider key is configured.

    Placeholder values must never trigger a network call or an API error.
    """
    if not api_key:
        return False
    candidate = api_key.strip().lower()
    if candidate in PLACEHOLDER_KEYS:
        return False
    return "your_" not in candidate