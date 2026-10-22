"""Small, pure formatting helpers (no I/O)."""

from __future__ import annotations

import re
from datetime import datetime

_ISO_DURATION = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def collapse_whitespace(text: str | None) -> str:
    """Collapse runs of whitespace into single spaces and strip both ends."""
    return re.sub(r"\s+", " ", text or "").strip()


def fmt_timestamp(seconds: float) -> str:
    """Format seconds as ``m:ss`` or ``h:mm:ss``."""
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def fmt_duration(seconds: int | None) -> str:
    """Format a length in seconds as ``38 min`` or ``1h 5m``; empty if unknown."""
    if not seconds:
        return ""
    hours, rem = divmod(int(seconds), 3600)
    minutes = rem // 60
    return f"{hours}h {minutes}m" if hours else f"{minutes} min"


def fmt_date(iso: str | None) -> str:
    """Format an ISO-8601 timestamp as ``Oct 21, 2026``; empty if unparseable."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%b %d, %Y")
    except ValueError:
        return ""


def parse_iso_duration(value: str | None) -> int:
    """Parse a YouTube ``contentDetails.duration`` string (``PT1H2M3S``) into seconds."""
    match = _ISO_DURATION.fullmatch(value or "")
    if not match:
        return 0
    days, hours, minutes, secs = (int(group) if group else 0 for group in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + secs
