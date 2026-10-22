"""Fetch a video's captions and turn them into timestamped text for the model."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import NamedTuple

from .formatting import collapse_whitespace, fmt_timestamp

log = logging.getLogger(__name__)

DEFAULT_LANGUAGES: tuple[str, ...] = ("en", "en-US", "en-GB")
MAX_TRANSCRIPT_CHARS = 150_000


class Segment(NamedTuple):
    """One caption line: start time in seconds and its text."""

    start: float
    text: str


def fetch_segments(
    video_id: str,
    proxy_url: str = "",
    languages: Sequence[str] = DEFAULT_LANGUAGES,
) -> list[Segment] | None:
    """Fetch captions for ``video_id``; return ``None`` if they are unavailable.

    YouTube sometimes blocks requests from cloud IP ranges. Pass ``proxy_url``
    to route the request through a proxy in that case.
    """
    # Imported lazily so the rest of the package works without the dependency.
    from youtube_transcript_api import YouTubeTranscriptApi

    kwargs = {}
    if proxy_url:
        from youtube_transcript_api.proxies import GenericProxyConfig

        kwargs["proxy_config"] = GenericProxyConfig(http_url=proxy_url, https_url=proxy_url)
    try:
        raw = YouTubeTranscriptApi(**kwargs).fetch(video_id, languages=list(languages))
        rows = raw.to_raw_data()
    except Exception as exc:  # the library raises many distinct error types
        log.warning("Transcript fetch failed for %s: %s: %s", video_id, type(exc).__name__, exc)
        return None
    segments = [
        Segment(float(row.get("start", 0)), collapse_whitespace(row.get("text", "")))
        for row in rows
    ]
    return [segment for segment in segments if segment.text] or None


def to_timestamped_text(
    segments: Sequence[Segment],
    block_sec: int = 30,
    max_chars: int = MAX_TRANSCRIPT_CHARS,
) -> str:
    """Group captions into ~``block_sec`` blocks, each prefixed with ``[m:ss]``.

    The markers let the model cite where in the video a point was made.
    """
    lines: list[str] = []
    buffer: list[str] = []
    block_start = 0.0
    for segment in segments:
        if not buffer:
            block_start = segment.start
        elif segment.start - block_start >= block_sec:
            lines.append(f"[{fmt_timestamp(block_start)}] {' '.join(buffer)}")
            buffer = []
            block_start = segment.start
        buffer.append(segment.text)
    if buffer:
        lines.append(f"[{fmt_timestamp(block_start)}] {' '.join(buffer)}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[transcript truncated]"
    return text
