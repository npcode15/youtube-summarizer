"""Telegram output: HTML messages sent through the Bot API."""

from __future__ import annotations

import html
import time
from collections.abc import Sequence

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

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
MESSAGE_LIMIT = 3900  # Telegram's hard limit is 4096 characters per message
FOOTER_RESERVE = 150  # room kept free for the footer on the last message
SEND_INTERVAL = 1.1  # Telegram allows about one message per second per chat
REQUEST_TIMEOUT = 30
MAX_TRIES = 5


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def bullet(point: Point, video: Video) -> str:
    """Format one point as an HTML bullet, with a clickable timestamp when known."""
    text = _escape(point.text)
    if point.start_sec is not None and point.start_sec >= 0:
        url = html.escape(timestamp_url(video, point.start_sec), quote=True)
        return f'{BULLET} {text} (<a href="{url}">{fmt_timestamp(point.start_sec)}</a>)'
    return f"{BULLET} {text}"


def tier_message(tier: str, points: Sequence[Point], video: Video, limit: int) -> str:
    """One tier as a message, dropping trailing bullets that would exceed ``limit``."""
    heading = f"{TIER_EMOJI[tier]} <b>{_escape(TIER_LABELS[tier])}</b>"
    lines = [bullet(point, video) for point in points]
    while len(lines) > 1 and len(heading) + 1 + len("\n".join(lines)) > limit:
        lines.pop()
    return heading + "\n" + "\n".join(lines)


class TelegramNotifier(Notifier):
    """Sends summaries to a Telegram chat with a bot."""

    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    def render_summary(self, video: Video, summary: Summary) -> list[str]:
        """A header message followed by one message per non-empty tier."""
        url = html.escape(video.url, quote=True)
        meta = " • ".join(part for part in (video.channel, video_meta(video)) if part)
        head = [f'<a href="{url}"><b>{_escape(video.title)}</b></a>']
        if meta:
            head.append(_escape(meta))
        if summary.headline:
            head.append("\n" + _escape(summary.headline))
        messages = ["\n".join(head)[:MESSAGE_LIMIT]]
        limit = MESSAGE_LIMIT - FOOTER_RESERVE
        for tier in TIERS:
            points = summary.tiers.get(tier) or []
            if points:
                messages.append(tier_message(tier, points, video, limit))
        messages[-1] += f"\n\n<i>{_escape(FOOTER_TEXT)}</i>"
        return messages

    def render_notice(self, video: Video, reason: str) -> list[str]:
        url = html.escape(video.url, quote=True)
        return [
            f"Couldn't summarize this video automatically ({_escape(reason)}).\n"
            f'<a href="{url}">{_escape(video.title)}</a>'
        ]

    def preview(self, payload: list[str]) -> str:
        return "\n\n-----\n\n".join(payload)

    def post(self, payload: list[str]) -> None:
        for index, text in enumerate(payload):
            if index:
                time.sleep(SEND_INTERVAL)
            self._send(text)

    def _send(self, text: str) -> None:
        url = API_URL.format(token=self.bot_token)
        body = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        for _ in range(MAX_TRIES):
            response = requests.post(url, json=body, timeout=REQUEST_TIMEOUT)
            try:
                data = response.json()
            except ValueError:
                data = {}
            if response.status_code == 429:
                delay = data.get("parameters", {}).get("retry_after", 2)
                time.sleep(float(delay) + 0.5)
                continue
            if not response.ok or not data.get("ok", False):
                reason = data.get("description", response.status_code)
                raise RuntimeError(f"Telegram: {reason}")
            return
        raise RuntimeError(f"Telegram rate limit: gave up after {MAX_TRIES} tries")
