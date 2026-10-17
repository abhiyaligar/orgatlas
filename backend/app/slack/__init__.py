"""Slack integration.

The bot answers questions in a channel from the same ``AskService`` the HTTP
API uses, so an answer in Slack carries the same evidence and the same
refusal to answer what the graph does not support.
"""

from app.slack.bot import SlackBot
from app.slack.formatter import blocks_for, to_slack

__all__ = ["SlackBot", "blocks_for", "to_slack"]
