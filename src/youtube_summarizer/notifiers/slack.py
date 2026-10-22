"""Slack output: a Block Kit message posted to an incoming webhook."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

import requests

from ..formatting import fmt_timestamp
from ..models import TIERS, Point, Summary, Video
from .base import (
    BULLET,
    FOOTER_TEXT,
    TIER_EMOJI,
    TIER_LABELS,
    Notifier,
    timestamp_url,
    video_meta,
)

SECTION_TEXT_LIMIT = 2900  # Slack allows 3000 characters in one section block
HEADER_TEXT_LIMIT = 150  # and 150 in a header block
WEBHOOK_TIMEOUT = 30
MAX_TRIES = 5


def escape(text: str) -> str:
    """Escape the three characters Slack treats specially in message text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def bullet(point: Point, video: Video) -> str:
    """Format one point as a bullet, with a clickable timestamp when known."""
    text = escape(point.text)
    if point.start_sec is not None and point.start_sec >= 0:
        link = f"<{timestamp_url(video, point.start_sec)}|{fmt_timestamp(point.start_sec)}>"
        return f"{BULLET} {text} ({link})"
    return f"{BULLET} {text}"


def tier_text(tier: str, points: Sequence[Point], video: Video) -> str:
    """One tier's section text, dropping trailing bullets that would exceed Slack's limit."""
    heading = f"{TIER_EMOJI[tier]} *{TIER_LABELS[tier]}*"
    lines = [bullet(point, video) for point in points]
    while len(lines) > 1 and len(heading) + 1 + len("\n".join(lines)) > SECTION_TEXT_LIMIT:
        lines.pop()
    return heading + "\n" + "\n".join(lines)


def _section(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _retry_after(response: requests.Response) -> float:
    try:
        return float(response.headers.get("Retry-After", 2))
    except ValueError:
        return 2.0


class SlackNotifier(Notifier):
    """Posts summaries to a Slack channel through an incoming webhook."""

    name = "slack"

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def render_summary(self, video: Video, summary: Summary) -> dict[str, Any]:
        meta = " • ".join(part for part in (video.channel, video_meta(video)) if part)
        intro = [f"<{video.url}|Watch on YouTube>"]
        if meta:
            intro.append(escape(meta))
        if summary.headline:
            intro.append("\n" + escape(summary.headline))
        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": video.title[:HEADER_TEXT_LIMIT],
                    "emoji": True,
                },
            },
            _section("\n".join(intro)),
        ]
        for tier in TIERS:
            points = summary.tiers.get(tier) or []
            if points:
                blocks.append({"type": "divider"})
                blocks.append(_section(tier_text(tier, points, video)))
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": FOOTER_TEXT}]})
        return {
            "text": f"New video: {video.title}",  # notification and fallback text
            "blocks": blocks,
            "unfurl_links": False,
            "unfurl_media": False,
        }

    def render_notice(self, video: Video, reason: str) -> dict[str, Any]:
        text = (
            f"Couldn't summarize this video automatically ({escape(reason)}).\n"
            f"<{video.url}|{escape(video.title)}>"
        )
        return {"text": f"New video: {video.title}", "blocks": [_section(text)]}

    def post(self, payload: dict[str, Any]) -> None:
        for _ in range(MAX_TRIES):
            response = requests.post(self.webhook_url, json=payload, timeout=WEBHOOK_TIMEOUT)
            if response.status_code == 429:
                time.sleep(_retry_after(response) + 0.5)
                continue
            if not response.ok:
                raise RuntimeError(f"Slack {response.status_code}: {response.text[:200]}")
            return
        raise RuntimeError(f"Slack rate limit: gave up after {MAX_TRIES} tries")
