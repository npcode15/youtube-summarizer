"""Discord output: rich embeds posted to an incoming webhook."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
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

Embed = dict[str, Any]

COLORS = {
    "header": 0x3498DB,
    "important": 0xE74C3C,
    "medium": 0xF39C12,
    "low": 0x95A5A6,
    "notice": 0x7F8C8D,
}
TIER_TITLES = {tier: f"{TIER_EMOJI[tier]} {TIER_LABELS[tier]}" for tier in TIERS}

# Discord caps a message at 10 embeds and 6000 characters of embed text in total.
EMBED_TOTAL_LIMIT = 5800
EMBED_DESCRIPTION_LIMIT = 4000
WEBHOOK_TIMEOUT = 30
WEBHOOK_MAX_TRIES = 5


def bullet(point: Point, video: Video) -> str:
    """Format one point as a bullet, with a clickable timestamp when known."""
    if point.start_sec is not None and point.start_sec >= 0:
        link = timestamp_url(video, point.start_sec)
        return f"{BULLET} {point.text} ([{fmt_timestamp(point.start_sec)}]({link}))"
    return f"{BULLET} {point.text}"


def render_embeds(
    video: Video, headline: str, tiers: Mapping[str, Sequence[Point]]
) -> list[Embed]:
    """Build the header embed plus one embed per non-empty tier."""
    meta = video_meta(video)
    description = "\n\n".join(part for part in (headline, f"*{meta}*" if meta else "") if part)
    header: Embed = {
        "title": video.title[:256],
        "url": video.url,
        "description": description[:EMBED_DESCRIPTION_LIMIT],
        "color": COLORS["header"],
        "image": {"url": f"https://i.ytimg.com/vi/{video.id}/hqdefault.jpg"},
    }
    if video.channel:
        header["author"] = {"name": video.channel[:256]}
    embeds = [header]
    for tier in TIERS:
        points = tiers.get(tier) or []
        if points:
            embeds.append(
                {
                    "title": TIER_TITLES[tier],
                    "description": "\n".join(bullet(point, video) for point in points),
                    "color": COLORS[tier],
                }
            )
    embeds[-1]["footer"] = {"text": FOOTER_TEXT}
    return embeds


def embed_chars(embed: Embed) -> int:
    """Count the characters Discord counts toward its per-message embed limit."""
    return (
        len(embed.get("title", ""))
        + len(embed.get("description", ""))
        + len(embed.get("author", {}).get("name", ""))
        + len(embed.get("footer", {}).get("text", ""))
    )


def build_embeds(video: Video, summary: Summary) -> list[Embed]:
    """Render ``summary``, dropping the least important bullets until it fits Discord's limits."""
    tiers = {tier: list(summary.tiers.get(tier, [])) for tier in TIERS}
    while True:
        embeds = render_embeds(video, summary.headline, tiers)
        too_big = sum(embed_chars(e) for e in embeds) > EMBED_TOTAL_LIMIT or any(
            len(e.get("description", "")) > EMBED_DESCRIPTION_LIMIT for e in embeds
        )
        if not too_big:
            return embeds
        for tier in reversed(TIERS):  # low, then medium, then important
            if len(tiers[tier]) > (1 if tier == "important" else 0):
                tiers[tier].pop()
                break
        else:
            return embeds


def notice_embeds(video: Video, reason: str) -> list[Embed]:
    """A plain notice for videos that could not be summarized."""
    return [
        {
            "title": video.title[:256],
            "url": video.url,
            "description": (
                f"Couldn't summarize this video automatically ({reason}).\n"
                f"Open it here: {video.url}"
            ),
            "color": COLORS["notice"],
        }
    ]


def post_webhook(webhook_url: str, embeds: list[Embed]) -> None:
    """POST ``embeds`` to a Discord webhook, honouring rate limits."""
    payload = {
        "username": "YT Summarizer",
        "embeds": embeds,
        "allowed_mentions": {"parse": []},  # never let transcript text ping anyone
    }
    for _ in range(WEBHOOK_MAX_TRIES):
        response = requests.post(
            webhook_url, params={"wait": "true"}, json=payload, timeout=WEBHOOK_TIMEOUT
        )
        if response.status_code == 429:
            try:
                delay = float(response.json().get("retry_after", 2))
            except ValueError:
                delay = 2.0
            time.sleep(delay + 0.5)
            continue
        if not response.ok:
            raise RuntimeError(f"Discord {response.status_code}: {response.text[:300]}")
        return
    raise RuntimeError(f"Discord rate limit: gave up after {WEBHOOK_MAX_TRIES} tries")


class DiscordNotifier(Notifier):
    """Posts summaries to a Discord channel through a webhook."""

    name = "discord"

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def render_summary(self, video: Video, summary: Summary) -> list[Embed]:
        return build_embeds(video, summary)

    def render_notice(self, video: Video, reason: str) -> list[Embed]:
        return notice_embeds(video, reason)

    def post(self, payload: list[Embed]) -> None:
        post_webhook(self.webhook_url, payload)
