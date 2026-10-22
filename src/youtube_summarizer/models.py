"""Plain data containers shared across modules."""

from __future__ import annotations

from dataclasses import dataclass, field

TIERS: tuple[str, ...] = ("important", "medium", "low")


@dataclass(frozen=True)
class Video:
    """A YouTube video as seen in a channel's upload list."""

    id: str
    title: str
    channel: str
    published: str  # ISO-8601 timestamp
    duration_sec: int | None = None  # None when unknown (RSS fallback)
    live: str | None = None  # "none" | "live" | "upcoming"; None when unknown

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"


@dataclass(frozen=True)
class Point:
    """One extracted fact, with the second of the video where it is discussed."""

    text: str
    start_sec: int | None = None


@dataclass
class Summary:
    """A video summary: a headline plus facts ranked into tiers."""

    headline: str
    tiers: dict[str, list[Point]] = field(default_factory=lambda: {t: [] for t in TIERS})

    def is_empty(self) -> bool:
        return not any(self.tiers.get(tier) for tier in TIERS)
