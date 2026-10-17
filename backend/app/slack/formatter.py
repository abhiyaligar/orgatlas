"""Turn an ask response into something readable in Slack.

Kept free of any Slack SDK type so it can be tested as plain data. The rules it
enforces are the same ones the API enforces: if the graph did not support the
answer, the message says so, and nothing is presented as more certain than the
evidence behind it.

Slack's ``mrkdwn`` is not markdown. Bold is ``*bold*``, links are
``<url|label>``, and backticks are not a code span, so the formatting here is
deliberately conservative: a link a reader can follow beats a citation they
have to copy.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Slack block text caps. Exceeding them fails the API call rather than
# truncating, so a long answer is chunked deliberately here.
MAX_BLOCK_CHARS = 3000
# A split block is labelled with its part number, so the body has to leave
# room for that label or the finished block exceeds the limit Slack enforces.
PART_LABEL_RESERVE = 48
MAX_SECTION_BLOCKS = 9

CONFIDENCE_EMOJI = {
    "supported": ":large_green_circle:",
    "partial": ":large_yellow_circle:",
    "insufficient": ":large_orange_circle:",
}

_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_MD_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_HEADING = re.compile(r"^#{1,6}\s*(.+?)\s*$", re.MULTILINE)
_MD_HEADING = _HEADING


def to_slack(text: str) -> str:
    """Convert the markdown subset the model emits into Slack mrkdwn."""
    # Angle brackets are Slack's link delimiters, and a bare one breaks the
    # message. They are neutralised first, on the raw text, because doing it
    # later would consume both the link syntax just written and the ">" that
    # marks a blockquote.
    text = text.replace("<", "(").replace(">", ")")

    # Fenced blocks become blockquotes; Slack has no inline code span to use.
    text = _MD_CODE_FENCE.sub(
        lambda m: "\n".join("> " + line for line in m.group(0).strip("`").splitlines()),
        text,
    )
    text = _HEADING.sub(lambda m: f"\n*{m.group(1)}*\n", text)
    text = _MD_BOLD.sub(lambda m: f"*{m.group(1)}*", text)
    text = _MD_LINK.sub(lambda m: f"<{m.group(2)}|{m.group(1)}>", text)
    return text.strip()


def _hard_split(text: str, limit: int) -> List[str]:
    """Split a single oversized block at word boundaries.

    A paragraph can exceed the limit on its own. Cutting it at a character would
    repeat the problem this module exists to avoid, so it is cut at the last
    space that fits.
    """
    pieces: List[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = window.rfind(" ")
        if cut <= 0:
            # No space to break on; a hard cut is the only option left.
            pieces.append(window)
            remaining = remaining[limit:]
            continue
        pieces.append(window[:cut])
        remaining = remaining[cut + 1 :]
    if remaining:
        pieces.append(remaining)
    return pieces


def _chunk(text: str, limit: int = MAX_BLOCK_CHARS) -> List[str]:
    """Split on paragraph boundaries so a chunk never ends mid-sentence."""
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > limit and current:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate

    if current:
        chunks.append(current)

    # A paragraph that exceeded the limit on its own still has to fit.
    return [piece for chunk in chunks for piece in _hard_split(chunk, limit)]


def citation_line(citation: Dict[str, Any], index: int) -> str:
    """One citable source, rendered so the reader can reach it."""
    title = (citation.get("title") or citation.get("source_id") or "source").strip()
    url = (citation.get("url") or "").strip()
    kind = (citation.get("type") or "source").strip()

    line = f"{index}. *{title}*"
    if citation.get("author"):
        line += f" — {citation['author']}"
    if url:
        line += f" — <{url}|open>"
    else:
        line += f" _(no link, {kind} in the graph)_"
    return line


def blocks_for(response: Dict[str, Any], max_citations: int = 5) -> List[Dict[str, Any]]:
    """Build Slack blocks for one ask response.

    The confidence line is placed above the answer rather than buried under it,
    because a reader who skims only the first line should still see whether the
    answer is load-bearing.
    """
    confidence = str(response.get("confidence") or "partial")
    emoji = CONFIDENCE_EMOJI.get(confidence, ":grey_question:")
    answer = str(response.get("answer") or "").strip()

    header = f"{emoji} *{confidence}*"

    if not answer:
        return [{"type": "section", "text": {"type": "mrkdwn", "text": "No answer produced."}}]

    blocks: List[Dict[str, Any]] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": to_slack(header)},
        }
    ]

    # Slack rejects an over-long block rather than shortening it, so a long
    # answer is split across sections. Slicing it to the cap instead would drop
    # the end of the answer, which is the same half-answer problem the summary
    # limits used to have.
    parts = _chunk(to_slack(answer), MAX_BLOCK_CHARS - PART_LABEL_RESERVE)
    for index, chunk in enumerate(parts):
        text = (
            f"{chunk}\n_(part {index + 1} of {len(parts)})_"
            if len(parts) > 1
            else chunk
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})

    summary = str(response.get("evidence_summary") or "").strip()
    if summary:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": to_slack(summary)[:MAX_BLOCK_CHARS]}],
            }
        )

    citations = list(response.get("citations") or [])
    if citations:
        shown = citations[:max_citations]
        lines = [citation_line(citation, index) for index, citation in enumerate(shown, 1)]
        if len(citations) > len(shown):
            lines.append(f"_…and {len(citations) - len(shown)} more in the API response._")
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Sources*\n" + "\n".join(lines)},
            }
        )

    follow_ups = [str(q) for q in (response.get("suggested_questions") or [])][:3]
    if follow_ups:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "*Try next:* " + " • ".join(follow_ups)}
                ],
            }
        )

    if confidence == "insufficient":
        # Said plainly, because a reader who acts on an unsupported answer
        # deserves to know it was unsupported.
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "The graph does not support an answer to this. "
                        "Ingest the repository or ask about something it covers.",
                    }
                ],
            }
        )

    return blocks[:MAX_SECTION_BLOCKS]


def text_for(response: Dict[str, Any]) -> str:
    """A plain-text rendering, used in logs and for the fallback transport."""
    confidence = str(response.get("confidence") or "partial")
    return f"[{confidence}] {response.get('answer', '').strip()}"


def extract_question(
    text: str,
    bot_user_id: Optional[str] = None,
    max_chars: int = 800,
) -> Optional[str]:
    """Pull the question out of a message that mentions the bot.

    Returns ``None`` when the message contains nothing but the mention, so the
    caller can stay silent instead of answering a blank question.
    """
    if not text:
        return None

    cleaned = text.strip()
    if bot_user_id:
        cleaned = re.sub(rf"<@{re.escape(bot_user_id)}>", " ", cleaned)
    # A leading colon after a mention is Slack convention, not part of the ask.
    cleaned = re.sub(r"^[:\s]+", "", cleaned).strip()

    if not cleaned:
        return None

    if len(cleaned) > max_chars:
        return cleaned[:max_chars].rstrip() + " [question truncated]"

    return cleaned