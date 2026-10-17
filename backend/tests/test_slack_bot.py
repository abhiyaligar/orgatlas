"""The Slack bot's decision to speak, and what it says when it does.

The bot is the same service as the HTTP API, so these tests are about the parts
that are specific to Slack: when it must stay silent, how a mention becomes a
question, and that an unsupported answer is reported as unsupported rather than
smoothed over.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.slack.bot import SlackBot, allowed_channels, is_allowed, mentions_bot
from app.slack.formatter import blocks_for, extract_question, to_slack

BOT = "U0ORGATLAS"


@pytest.fixture(autouse=True)
def _configure(monkeypatch):
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-test", raising=False)
    monkeypatch.setattr(settings, "SLACK_APP_TOKEN", "xapp-test", raising=False)
    monkeypatch.setattr(settings, "SLACK_ALLOWED_CHANNELS", "C111,C222", raising=False)


def event(**overrides):
    payload = {
        "type": "app_mention",
        "channel": "C111",
        "ts": "1700000000.000100",
        "text": f"<@{BOT}> why does checkout use kafka?",
        "user": "UOTHER",
    }
    payload.update(overrides)
    return payload


def bot_with_response(payload):
    ask = MagicMock()
    ask.answer = AsyncMock(return_value=MagicMock(**payload))
    return SlackBot(ask=ask, bot_user_id=BOT), ask


# --- silence ----------------------------------------------------------------


def test_an_empty_allowlist_means_silent_everywhere(monkeypatch):
    monkeypatch.setattr(settings, "SLACK_ALLOWED_CHANNELS", "", raising=False)
    assert allowed_channels() == set()
    assert is_allowed("C111") is False


def test_a_channel_outside_the_allowlist_is_ignored():
    assert is_allowed("C999") is False


def test_a_channel_on_the_allowlist_is_allowed():
    assert is_allowed("C111") is True


def test_a_message_without_a_mention_is_ignored():
    bot, _ = bot_with_response({})
    assert bot.should_answer(event(text="just chatting about kafka")) is None


def test_the_bots_own_message_is_ignored_to_avoid_a_loop():
    bot, _ = bot_with_response({})
    assert bot.should_answer(event(bot_id="B123")) is None


def test_a_message_edit_subtype_is_ignored():
    bot, _ = bot_with_response({})
    assert bot.should_answer(event(subtype="message_changed")) is None


def test_an_unsupported_event_type_is_ignored():
    bot, _ = bot_with_response({})
    assert bot.should_answer(event(type="reaction_added")) is None


def test_a_bare_mention_asks_nothing_and_is_not_answered():
    bot, _ = bot_with_response({})
    assert bot.should_answer(event(text=f"<@{BOT}>")) is None


# --- answering --------------------------------------------------------------


def test_a_mention_becomes_the_question():
    bot, _ = bot_with_response({})
    assert bot.should_answer(event()) == "why does checkout use kafka?"


def test_the_bot_posts_into_the_thread_it_was_asked_in():
    payload = {"answer": "Because of the outage.", "confidence": "supported"}
    bot, _ = bot_with_response(payload)
    result = asyncio.run(bot.handle_event(event()))

    assert result is not None
    assert result["channel"] == "C111"
    assert result["thread_ts"] == "1700000000.000100"


def test_an_unsupported_answer_is_reported_as_unsupported():
    payload = {
        "answer": "Insufficient evidence was found in the knowledge graph.",
        "confidence": "insufficient",
        "evidence_summary": "No supporting graph paths were found.",
        "citations": [],
        "suggested_questions": [],
    }
    bot, _ = bot_with_response(payload)
    result = asyncio.run(bot.handle_event(event()))

    rendered = "\n".join(
        block.get("text", {}).get("text", "")
        if block.get("type") == "section"
        else " ".join(el.get("text", "") for el in block.get("elements", []))
        for block in result["blocks"]
    )
    assert "insufficient" in rendered
    assert "does not support an answer" in rendered
    assert result["text"].startswith("[insufficient]")


def test_a_failure_is_reported_as_a_failure_not_as_an_answer():
    ask = MagicMock()
    ask.answer = AsyncMock(side_effect=RuntimeError("graph down"))
    bot = SlackBot(ask=ask, bot_user_id=BOT)

    result = asyncio.run(bot.handle_event(event()))

    assert result is not None
    assert "could not answer" in result["text"]
    assert result["text"].startswith("[insufficient]")


def test_an_ignored_event_produces_nothing_to_post():
    bot, _ = bot_with_response({})
    assert asyncio.run(bot.handle_event(event(channel="C999"))) is None


# --- formatting -------------------------------------------------------------


def test_confidence_appears_above_the_answer():
    blocks = blocks_for({"answer": "Body text.", "confidence": "partial"})
    assert "partial" in blocks[0]["text"]["text"]
    assert "Body text." in blocks[1]["text"]["text"]


def test_citations_become_a_numbered_source_list():
    blocks = blocks_for(
        {
            "answer": "Because.",
            "confidence": "supported",
            "citations": [
                {"source_id": "doc_rfc", "title": "RFC-042", "type": "document", "url": "https://x.dev/rfc"},
                {"source_id": "cm1", "title": "a1b2c3d fix", "type": "commit", "author": "Avi"},
            ],
        }
    )
    sources = next(b for b in blocks if b.get("text", {}).get("text", "").startswith("*Sources*"))
    text = sources["text"]["text"]
    assert "1. *RFC-042*" in text
    assert "<https://x.dev/rfc|open>" in text
    assert "2. *a1b2c3d fix* — Avi" in text


def test_a_citation_with_no_link_says_so_rather_than_inventing_one():
    blocks = blocks_for(
        {
            "answer": "Because.",
            "confidence": "supported",
            "citations": [{"source_id": "doc_rfc", "title": "RFC-042", "type": "document"}],
        }
    )
    sources = next(b for b in blocks if b.get("text", {}).get("text", "").startswith("*Sources*"))
    assert "no link" in sources["text"]["text"]


def test_more_citations_than_fit_are_summarised_not_silently_cut():
    citations = [{"source_id": f"d{i}", "title": f"Doc {i}", "type": "document"} for i in range(9)]
    blocks = blocks_for({"answer": "Because.", "confidence": "supported", "citations": citations})
    sources = next(b for b in blocks if b.get("text", {}).get("text", "").startswith("*Sources*"))
    assert "and 4 more" in sources["text"]["text"]


def test_markdown_links_survive_the_conversion_to_mrkdwn():
    assert to_slack("See [RFC-042](https://x.dev/rfc).") == "See <https://x.dev/rfc|RFC-042>."


def test_generic_angle_brackets_do_not_break_the_message():
    """Only the deliberate link delimiters may survive; Result<T> must not."""
    rendered = to_slack("returns Result<T> and [x](https://y.dev)")
    assert "Result(T)" in rendered
    assert rendered.count("<") == rendered.count(">") == 1
    assert "<https://y.dev|x>" in rendered


def test_a_long_answer_is_split_into_sections_and_not_cut():
    """The end of a long answer must survive; Slack rejects an oversized block."""
    answer = "First sentence.\n\n" + ("Body paragraph.\n\n" * 500)
    blocks = blocks_for({"answer": answer, "confidence": "supported"})

    sections = [b for b in blocks if b["type"] == "section"]
    assert len(sections) > 1, "a long answer must not be squeezed into one block"
    assert all(len(b["text"]["text"]) <= 3000 for b in sections)

    joined = " ".join(b["text"]["text"] for b in sections)
    assert "First sentence." in joined
    assert "part 2 of" in joined, "a split answer says which part it is on"


def test_a_very_long_question_is_marked_as_truncated():
    question = extract_question(f"<@{BOT}> " + "why " * 400, BOT, max_chars=100)
    assert question.endswith("[question truncated]")