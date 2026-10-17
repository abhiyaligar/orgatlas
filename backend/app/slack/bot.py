"""Answer questions in Slack from the OrgAtlas graph.

The bot is a thin face on the same ``AskService`` the HTTP API uses, so an answer
in Slack is the answer the API gives, with the same evidence and the same
refusal to answer what the graph does not support. Nothing here writes to the
graph or reads a Slack message the bot was not mentioned in.

Socket Mode is used rather than an Events API webhook. Socket Mode opens an
outbound WebSocket to Slack, so the bot runs from a laptop with no public URL
and no inbound firewall rule -- the same constraint that keeps the MCP HTTP
route development-only. The cost is that it is a long-running local process, not
a serverless function.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Sequence, Set

from app.core.config import settings
from app.services.ask_service import AskService
from app.slack.formatter import blocks_for, extract_question, text_for

logger = logging.getLogger(__name__)

# Only app_mention and message channels are handled. Everything else is ignored
# rather than acknowledged, so the bot does not burn a rate-limit slot on events
# it will never answer.
SUPPORTED_EVENTS = {"app_mention", "message"}


def allowed_channels() -> Set[str]:
    """Channels the bot may answer in.

    An empty allowlist means silent everywhere. A bot that has merely been
    invited to a workspace must not start answering questions in it until someone
    has said where that is wanted.
    """
    raw = (settings.SLACK_ALLOWED_CHANNELS or "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.replace(";", ",").split(",") if part.strip()}


def is_allowed(channel_id: Optional[str]) -> bool:
    allowlist = allowed_channels()
    if not allowlist:
        return False
    return bool(channel_id) and channel_id in allowlist


def mentions_bot(text: str, bot_user_id: Optional[str]) -> bool:
    """Whether the message addresses the bot at all.

    Subtype ``message_im`` (the implicit "channel" conversation) is excluded by
    the caller; here a plain substring check is enough because the mention tag
    is unambiguous.
    """
    if not text or not bot_user_id:
        return False
    return f"<@{bot_user_id}>" in text


class SlackBot:
    """Answers mentioned questions from the graph. Read-only by construction."""

    def __init__(
        self,
        ask: Optional[AskService] = None,
        bot_user_id: Optional[str] = None,
    ) -> None:
        self.ask = ask or AskService()
        self.bot_user_id = bot_user_id

    # --- decision to answer --------------------------------------------------

    def should_answer(self, event: Dict[str, Any]) -> Optional[str]:
        """Return the question to answer, or ``None`` to stay silent.

        Silent by default. The bot answers only when it was mentioned, in a
        channel on the allowlist, and only for the event types it understands.
        """
        event_type = event.get("type")
        if event_type not in SUPPORTED_EVENTS:
            return None

        if event.get("subtype"):
            # Message edits, joins, and the bot's own posts would otherwise loop.
            return None

        if event.get("bot_id") or event.get("bot_profile"):
            return None

        channel = event.get("channel")
        if not is_allowed(channel):
            logger.debug("ignoring mention in unlisted channel %s", channel)
            return None

        text = event.get("text") or ""
        if not mentions_bot(text, self.bot_user_id):
            return None

        return extract_question(
            text,
            self.bot_user_id,
            max_chars=settings.SLACK_MAX_QUESTION_CHARS,
        )

    # --- answering -----------------------------------------------------------

    async def answer(self, question: str) -> Dict[str, Any]:
        """Run one question through the same service the API uses."""
        response = await self.ask.answer(question)
        return {
            "answer": response.answer,
            "evidence_summary": response.evidence_summary,
            "citations": [
                citation.model_dump() if hasattr(citation, "model_dump") else dict(citation)
                for citation in response.citations
            ],
            "confidence": response.confidence,
            "suggested_questions": list(response.suggested_questions),
        }

    async def handle_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Turn a Slack event into the payload to post, or ``None`` to ignore."""
        question = self.should_answer(event)
        if not question:
            return None

        try:
            result = await self.answer(question)
        except Exception as exc:  # pragma: no cover - defensive
            # A failure here must not read as a wrong answer. Say it broke.
            logger.exception("slack answer failed")
            result = {
                "answer": f"OrgAtlas could not answer that: {type(exc).__name__}.",
                "evidence_summary": "",
                "citations": [],
                "confidence": "insufficient",
                "suggested_questions": [],
            }

        return {
            "channel": event.get("channel"),
            "thread_ts": event.get("ts"),
            "blocks": blocks_for(result),
            "text": text_for(result),
        }

    # --- transport -----------------------------------------------------------

    async def run(self) -> None:
        """Connect over Socket Mode and answer until interrupted."""
        from slack_sdk.socket_mode.aiohttp import SocketModeClient
        from slack_sdk.web.async_client import AsyncWebClient

        bot_token = settings.SLACK_BOT_TOKEN
        app_token = settings.SLACK_APP_TOKEN
        if not bot_token or not app_token:
            raise RuntimeError(
                "SLACK_BOT_TOKEN and SLACK_APP_TOKEN must both be set to run the bot."
            )

        if not allowed_channels():
            logger.warning(
                "SLACK_ALLOWED_CHANNELS is empty: the bot will stay silent in every channel."
            )

        web = AsyncWebClient(token=bot_token)
        self.bot_user_id = (await web.auth_test()).user_id
        client = SocketModeClient(app_token=app_token, web_client=web)

        async def handle(client: Any, request: Any) -> None:
            if request.type != "events_api":
                return
            envelope = request.payload
            event = (envelope or {}).get("event") or {}
            payload = await self.handle_event(event)
            if payload is None:
                return
            await web.chat_postMessage(
                channel=payload["channel"],
                thread_ts=payload["thread_ts"],
                text=payload["text"],
                blocks=payload["blocks"],
            )
            await client.send_socket_mode_response(
                {"envelope_id": request.envelope_id}
            )

        logger.info(
            "Slack bot connecting as %s, answering in %s",
            self.bot_user_id,
            sorted(allowed_channels()) or "no channels",
        )
        await client.connect()
        await client.send_message("hello")
        try:
            await client.start()
        finally:
            await client.close()
            await web.close()


async def main() -> None:  # pragma: no cover - entry point
    logging.basicConfig(level=logging.INFO)
    await SlackBot().run()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())