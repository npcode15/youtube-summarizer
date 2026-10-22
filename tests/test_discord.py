from youtube_summarizer.notifiers.discord import (
    EMBED_TOTAL_LIMIT,
    build_embeds,
    embed_chars,
    notice_embeds,
)
from youtube_summarizer.models import Point, Summary, Video

VIDEO = Video(
    id="abc123",
    title="T" * 300,
    channel="C" * 300,
    published="2026-10-21T14:00:00Z",
    duration_sec=2300,
    live="none",
)


def _summary(important=1, medium=1, low=1, text="SPX support 6,850"):
    def points(count, offset):
        return [Point(text, offset + i) for i in range(count)]

    return Summary(
        headline="Presenter expects a pullback.",
        tiers={
            "important": points(important, 100),
            "medium": points(medium, 500),
            "low": points(low, 900),
        },
    )


def test_normal_summary_renders_header_and_three_tiers_in_order():
    embeds = build_embeds(VIDEO, _summary())
    assert len(embeds) == 4
    assert embeds[1]["title"].startswith("\U0001F534")
    assert embeds[2]["title"].startswith("\U0001F7E0")
    assert embeds[3]["title"].startswith("⚪")
    assert len({e["color"] for e in embeds}) == 4


def test_bullets_carry_clickable_timestamps():
    embeds = build_embeds(VIDEO, _summary(important=1, medium=0, low=0))
    assert "([1:40](https://youtu.be/abc123?t=100))" in embeds[1]["description"]


def test_last_embed_has_the_caption_footer():
    embeds = build_embeds(VIDEO, _summary())
    assert "footer" in embeds[-1]
    assert all("footer" not in e for e in embeds[:-1])


def test_empty_tiers_are_omitted():
    embeds = build_embeds(VIDEO, _summary(important=2, medium=0, low=0))
    assert len(embeds) == 2


def test_oversized_summary_is_trimmed_from_the_bottom_up():
    summary = _summary(important=6, medium=8, low=6, text="X" * 300)
    embeds = build_embeds(VIDEO, summary)
    assert sum(embed_chars(e) for e in embeds) <= EMBED_TOTAL_LIMIT
    assert len(embeds) <= 10
    assert all(len(e.get("description", "")) <= 4096 for e in embeds)
    assert len(embeds[0]["title"]) <= 256
    important = next(e for e in embeds if e["title"].startswith("\U0001F534"))
    assert important["description"].count("•") == 6  # most important tier is kept whole


def test_notice_links_to_the_video():
    embed = notice_embeds(VIDEO, "captions not available")[0]
    assert "captions not available" in embed["description"]
    assert VIDEO.url in embed["description"]
