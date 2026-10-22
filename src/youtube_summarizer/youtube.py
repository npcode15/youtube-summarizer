"""Find a channel's recent uploads via the YouTube Data API, with an RSS fallback."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

import requests

from .formatting import parse_iso_duration
from .models import Video

log = logging.getLogger(__name__)

API_BASE = "https://www.googleapis.com/youtube/v3"
RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
REQUEST_TIMEOUT = 20
USER_AGENT = {"User-Agent": "Mozilla/5.0 (compatible; youtube-summarizer)"}

_CHANNEL_ID = re.compile(r"(UC[A-Za-z0-9_-]{22})")
_HANDLE = re.compile(r"@([A-Za-z0-9._-]+)")
_ATOM = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


class YouTubeError(RuntimeError):
    """Raised when a channel or its videos cannot be resolved."""


def resolve_channel_id(raw: str, api_key: str = "") -> str:
    """Turn a channel ID, ``@handle`` or channel URL into a ``UC...`` channel ID."""
    match = _CHANNEL_ID.search(raw or "")
    if match:
        return match.group(1)
    handle = _HANDLE.search(raw or "")
    if handle and api_key:
        try:
            response = requests.get(
                f"{API_BASE}/channels",
                params={"part": "id", "forHandle": f"@{handle.group(1)}", "key": api_key},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            items = response.json().get("items") or []
        except (requests.RequestException, ValueError) as exc:
            raise YouTubeError(
                f"Could not look up handle {handle.group(0)}: {type(exc).__name__}"
            ) from exc
        if items:
            return items[0]["id"]
    raise YouTubeError(
        f"Could not resolve a channel ID from {raw!r}. Set YT_CHANNEL to the UC... channel ID."
    )


def videos_from_api(
    items: list[dict[str, Any]], details: dict[str, dict[str, Any]]
) -> list[Video]:
    """Combine ``playlistItems`` results with ``videos`` details into :class:`Video` objects.

    Items missing from ``details`` (private or deleted videos) are dropped.
    """
    videos = []
    for item in items:
        video_id = item["contentDetails"]["videoId"]
        detail = details.get(video_id)
        if detail is None:
            continue
        snippet = item["snippet"]
        videos.append(
            Video(
                id=video_id,
                title=snippet.get("title", "(untitled)"),
                channel=snippet.get("channelTitle", ""),
                published=item["contentDetails"].get("videoPublishedAt")
                or snippet.get("publishedAt", ""),
                duration_sec=parse_iso_duration(detail["contentDetails"].get("duration", "")),
                live=detail["snippet"].get("liveBroadcastContent", "none"),
            )
        )
    return videos


def videos_from_rss(content: bytes) -> list[Video]:
    """Parse a YouTube Atom feed into :class:`Video` objects (duration unknown)."""
    root = ET.fromstring(content)
    channel = root.findtext("a:title", default="", namespaces=_ATOM)
    videos = []
    for entry in root.findall("a:entry", _ATOM):
        video_id = entry.findtext("yt:videoId", namespaces=_ATOM)
        if not video_id:
            continue
        videos.append(
            Video(
                id=video_id,
                title=entry.findtext("a:title", default="(untitled)", namespaces=_ATOM),
                channel=channel,
                published=entry.findtext("a:published", default="", namespaces=_ATOM),
            )
        )
    return videos


def fetch_via_api(channel_id: str, api_key: str) -> list[Video]:
    # A channel's uploads playlist ID is its channel ID with the "UC" prefix swapped for "UU".
    playlist = requests.get(
        f"{API_BASE}/playlistItems",
        params={
            "part": "snippet,contentDetails",
            "playlistId": "UU" + channel_id[2:],
            "maxResults": 15,
            "key": api_key,
        },
        timeout=REQUEST_TIMEOUT,
    )
    playlist.raise_for_status()
    items = playlist.json().get("items", [])
    ids = [item["contentDetails"]["videoId"] for item in items]
    details: dict[str, dict[str, Any]] = {}
    if ids:
        response = requests.get(
            f"{API_BASE}/videos",
            params={"part": "contentDetails,snippet", "id": ",".join(ids), "key": api_key},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        details = {video["id"]: video for video in response.json().get("items", [])}
    return videos_from_api(items, details)


def _fetch_via_rss(channel_id: str) -> list[Video]:
    try:
        response = requests.get(
            RSS_URL.format(channel_id=channel_id), headers=USER_AGENT, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return videos_from_rss(response.content)
    except (requests.RequestException, ET.ParseError) as exc:
        raise YouTubeError(f"RSS feed unavailable: {exc}") from exc


def fetch_recent_videos(channel_id: str, api_key: str = "") -> list[Video]:
    """Return the channel's most recent uploads, newest first.

    Uses the Data API when a key is provided and falls back to the RSS feed,
    which YouTube serves unreliably (intermittent 404/500 responses).
    """
    videos: list[Video] | None = None
    if api_key:
        try:
            videos = fetch_via_api(channel_id, api_key)
        except (requests.RequestException, KeyError, ValueError) as exc:
            log.warning("YouTube Data API failed (%s); falling back to RSS", exc)
    else:
        log.warning("YOUTUBE_API_KEY is not set; using the RSS feed, which is unreliable")
    if videos is None:
        videos = _fetch_via_rss(channel_id)
    return sorted(videos, key=lambda video: video.published, reverse=True)
