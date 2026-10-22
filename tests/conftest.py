"""Shared fixtures for the notifier tests."""

from youtube_summarizer.models import Point, Summary, Video

VIDEO = Video(
    id="abc123", title="Market <outlook> & levels", channel="Chan",
    published="2026-10-21T14:00:00Z", duration_sec=2300, live="none",
)
SUMMARY = Summary(
    headline="Pullback expected & hedged.",
    tiers={
        "important": [Point("SPX support 6,850 <break> targets 6,700", 75)],
        "medium": [Point("Breadth: 38% above 50-day", 300)],
        "low": [Point("VIX last here in 2023")],
    },
)
