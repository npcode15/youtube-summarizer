"""Ask Claude to extract and rank the facts in a transcript, and parse its answer."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

import requests

from .config import DEFAULT_MODEL, DEFAULT_READER_CONTEXT
from .formatting import collapse_whitespace, fmt_duration
from .models import TIERS, Point, Summary, Video

log = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 529})
MAX_POINT_CHARS = 300

PROMPT_TEMPLATE = """\
You are an analyst preparing a briefing from the auto-generated transcript of a YouTube video.

Reader: <<CONTEXT>>
Video: <<TITLE>>
Channel: <<CHANNEL>>
Length: <<DURATION>>

The transcript has [m:ss] markers at the start of ~30-second blocks. It comes from auto-captions, \
so numbers, tickers and names may be mis-transcribed.

The video is long and packed with statistics. Pull out the specific facts and rank them by how \
useful they are to the reader.

Tiers:
- important: specific numbers, price levels, dates and explicit calls that could change a decision \
in the coming days or weeks. Examples: support/resistance or target levels, scheduled catalysts \
with dates, the presenter's directional view together with the stated reason or the level that \
invalidates it, risk warnings, and any change from a previously stated view.
- medium: data that supports or qualifies the important points (breadth, sector or asset moves, \
positioning, macro figures) and the context needed to interpret them.
- low: background, historical comparisons, trivia, anecdotes, and "interesting but not \
actionable" stats.

Rules:
1. Be specific. Keep exact figures as spoken, with units and the asset or ticker they refer to. \
A bullet without a concrete figure, level, date or named claim does not belong.
2. Attribute opinions: write "Presenter expects..." rather than stating a forecast as fact.
3. Never invent or round numbers. If a number sounds garbled, include it and append "(check)".
4. Skip sponsor reads, promotions, calls to subscribe and small talk.
5. Each bullet is one sentence, at most 220 characters, with the key figure first. For important \
bullets add a short reason after a dash.
6. "t" is the start time in whole seconds of the transcript block where the point is made \
(convert [m:ss] to seconds).
7. Counts: important 3-6, medium 4-8, low 3-6. Use fewer if the video has less. Each fact goes in \
exactly one tier.

Return ONLY valid JSON, with no markdown fences, in this shape:
{"headline": "at most 2 sentences on the video's main thesis", \
"important": [{"t": 754, "text": "..."}], "medium": [{"t": 1210, "text": "..."}], \
"low": [{"t": 90, "text": "..."}]}

Transcript:
<<TRANSCRIPT>>
"""


class SummarizerError(RuntimeError):
    """Raised when the model cannot produce a usable summary."""


class ClaudeClient:
    """Minimal client for the Anthropic Messages API."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        *,
        max_tokens: int = 2500,
        timeout: int = 180,
        retries: int = 3,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.retries = retries

    def complete(self, prompt: str) -> str:
        """Send ``prompt`` as a single user message and return the text reply."""
        last_status: int | None = None
        for attempt in range(self.retries):
            response = requests.post(
                API_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": API_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=self.timeout,
            )
            if response.status_code in RETRYABLE_STATUS:
                last_status = response.status_code
                time.sleep(5 * (attempt + 1))
                continue
            if not response.ok:
                raise SummarizerError(
                    f"Anthropic API {response.status_code}: {response.text[:300]}"
                )
            blocks = response.json().get("content", [])
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        raise SummarizerError(f"Anthropic API unavailable (last status {last_status})")


def build_prompt(video: Video, transcript_text: str, reader_context: str) -> str:
    """Fill the prompt template for ``video``."""
    return (
        PROMPT_TEMPLATE.replace("<<CONTEXT>>", reader_context)
        .replace("<<TITLE>>", video.title)
        .replace("<<CHANNEL>>", video.channel or "unknown")
        .replace("<<DURATION>>", fmt_duration(video.duration_sec) or "unknown")
        .replace("<<TRANSCRIPT>>", transcript_text)
    )


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply, tolerating code fences and surrounding chatter."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])


def parse_summary(text: str) -> Summary:
    """Turn a model reply into a :class:`Summary`; raises ``ValueError`` if unusable."""
    data = extract_json(text)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    summary = Summary(headline=collapse_whitespace(str(data.get("headline", "")))[:600])
    for tier in TIERS:
        for item in data.get(tier) or []:
            if isinstance(item, str):
                item = {"text": item}
            if not isinstance(item, dict):
                continue
            point_text = collapse_whitespace(str(item.get("text", "")))
            if not point_text:
                continue
            try:
                start: int | None = int(float(item.get("t")))
            except (TypeError, ValueError, OverflowError):
                start = None
            summary.tiers[tier].append(Point(point_text[:MAX_POINT_CHARS], start))
    if summary.is_empty():
        raise ValueError("model returned no items")
    return summary


def summarize(
    video: Video,
    transcript_text: str,
    complete: Callable[[str], str],
    reader_context: str = DEFAULT_READER_CONTEXT,
    *,
    attempts: int = 2,
) -> Summary:
    """Summarize ``transcript_text`` using ``complete`` (a prompt -> reply function)."""
    prompt = build_prompt(video, transcript_text, reader_context)
    for attempt in range(attempts):
        suffix = "" if attempt == 0 else (
            "\n\nYour previous reply was not valid JSON. Return ONLY the JSON object."
        )
        reply = complete(prompt + suffix)
        try:
            return parse_summary(reply)
        except ValueError as exc:  # includes json.JSONDecodeError
            log.warning("Unusable model output (attempt %d/%d): %s", attempt + 1, attempts, exc)
    raise SummarizerError("Model did not return a valid summary")
