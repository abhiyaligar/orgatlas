"""Turn an uploaded file into text a model can be asked about.

Four kinds are supported, and text is the point: everything downstream -- entity
linking, extraction, retrieval -- operates on prose. A spreadsheet is a special
case rather than a different pipeline, because a decision log exported to CSV is
still prose with columns.

PDF text extraction is best-effort by nature. A scanned PDF has no text layer,
so the honest outcome there is an explicit failure that names the reason, not an
empty document that later reads as "this file said nothing".
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

KIND_PDF = "pdf"
KIND_MARKDOWN = "markdown"
KIND_TEXT = "text"
KIND_CSV = "csv"

SUPPORTED_KINDS = (KIND_PDF, KIND_MARKDOWN, KIND_TEXT, KIND_CSV)

_EXTENSION_KINDS = {
    ".pdf": KIND_PDF,
    ".md": KIND_MARKDOWN,
    ".markdown": KIND_MARKDOWN,
    ".txt": KIND_TEXT,
    ".text": KIND_TEXT,
    ".csv": KIND_CSV,
}

# A document past this size is truncated for extraction rather than sent whole.
# The stored text keeps everything; only the model prompt is bounded.
MAX_EXTRACT_CHARS = 24000

# A parsed representation of one logical document. A CSV yields several, one per
# row, because a decision log flattened into a single blob loses the fact that it
# was ever a list.
@dataclass
class ParsedDocument:
    id: str
    title: str
    kind: str
    text: str
    # Row index or page offset, when the source had internal structure.
    ordinal: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.text)


class DocumentParseError(Exception):
    """Raised when a file cannot be read as text. Names the reason."""


def kind_for_filename(filename: str) -> str:
    lowered = (filename or "").lower()
    for extension, kind in _EXTENSION_KINDS.items():
        if lowered.endswith(extension):
            return kind
    raise DocumentParseError(
        f"unsupported file type for {filename!r}; "
        f"supported: {', '.join(sorted(_EXTENSION_KINDS))}"
    )


def _clean(text: str) -> str:
    """Collapse the whitespace that PDF and CSV extraction leaves behind.

    De-hyphenation matters more than it looks: a PDF that wraps a word across a
    line break produces "asynchro-\nnous", which then fails to resolve to
    "asynchronous" when the document is linked to the graph.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_pdf(data: bytes, document_id: str, title: Optional[str] = None) -> List[ParsedDocument]:
    """Extract a PDF's text layer.

    Raises rather than returning empty when there is no text to extract: an
    image-only scan has nothing to link, and reporting that as a document with
    no content would read later as "the authors wrote nothing".
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise DocumentParseError("pypdf is not installed; PDFs cannot be parsed") from exc

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise DocumentParseError(f"could not read PDF: {exc}") from exc

    pages: List[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            # One unreadable page should not lose the rest of the document.
            pages.append("")

    body = _clean("\n\n".join(pages))
    if not body.strip():
        raise DocumentParseError(
            "PDF has no text layer (it is probably a scan). "
            "OCR it first, then upload the result."
        )

    resolved = title or (reader.metadata.title if reader.metadata else None) or "document"
    return [
        ParsedDocument(
            id=document_id,
            title=str(resolved),
            kind=KIND_PDF,
            text=body,
            metadata={"pages": len(reader.pages)},
        )
    ]


def parse_markdown(data: bytes, document_id: str, title: Optional[str] = None) -> List[ParsedDocument]:
    text = _clean(data.decode("utf-8", errors="replace"))
    heading = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    resolved = title or (heading.group(1).strip() if heading else None) or "document"
    return [
        ParsedDocument(id=document_id, title=resolved, kind=KIND_MARKDOWN, text=text)
    ]


def parse_text(data: bytes, document_id: str, title: Optional[str] = None) -> List[ParsedDocument]:
    text = _clean(data.decode("utf-8", errors="replace"))
    first_line = text.split("\n", 1)[0].strip()
    resolved = title or (first_line[:120] if first_line else None) or "document"
    return [ParsedDocument(id=document_id, title=resolved, kind=KIND_TEXT, text=text)]


def parse_csv(data: bytes, document_id: str, title: Optional[str] = None) -> List[ParsedDocument]:
    """Split a CSV into one document per row.

    A decision log or an incident register is a table of separate records. Kept
    as one blob the model would summarise the whole sheet and attribute every
    decision to every row, so each row becomes its own document with its own
    title and its own citable identifier.
    """
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise DocumentParseError("CSV is empty")

    header = [column.strip() for column in header]
    if not any(header):
        raise DocumentParseError("CSV has no header row")

    base = title or "document"
    documents: List[ParsedDocument] = []
    for index, row in enumerate(reader):
        if not any(cell.strip() for cell in row):
            continue

        fields = {
            header[position]: cell.strip()
            for position, cell in enumerate(row)
            if position < len(header) and header[position] and cell.strip()
        }
        if not fields:
            continue

        # Prefer an explicit title/decision/summary column for the row's name.
        row_title = next(
            (
                fields[key]
                for key in ("title", "decision", "summary", "subject", "name")
                if key in fields
            ),
            f"{base} row {index + 1}",
        )

        body = "\n".join(f"{key}: {value}" for key, value in fields.items())
        documents.append(
            ParsedDocument(
                id=f"{document_id}#{index + 1}",
                title=row_title[:200],
                kind=KIND_CSV,
                text=body,
                ordinal=index + 1,
                metadata={"columns": header, "fields": fields},
            )
        )

    if not documents:
        raise DocumentParseError("CSV has a header but no rows")

    return documents


_PARSERS = {
    KIND_PDF: parse_pdf,
    KIND_MARKDOWN: parse_markdown,
    KIND_TEXT: parse_text,
    KIND_CSV: parse_csv,
}


def parse_document(
    data: bytes, filename: str, document_id: str, title: Optional[str] = None
) -> List[ParsedDocument]:
    """Parse any supported upload into one or more documents."""
    kind = kind_for_filename(filename)
    return _PARSERS[kind](data, document_id, title)


def for_extraction(text: str, limit: int = MAX_EXTRACT_CHARS) -> str:
    """Bound the text handed to the model. The stored document keeps all of it."""
    if len(text) <= limit:
        return text
    # Cut at a paragraph so the model is not handed a sentence half-finished.
    window = text[:limit]
    cut = window.rfind("\n\n")
    if cut > limit // 2:
        return window[:cut]
    return window