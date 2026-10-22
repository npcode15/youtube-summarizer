from conftest import SUMMARY, VIDEO
from youtube_summarizer.notifiers.slack import SECTION_TEXT_LIMIT, SlackNotifier, escape


def test_escape_handles_slack_control_characters():
    assert escape("a & <b>") == "a &amp; &lt;b&gt;"


def test_blocks_respect_slack_limits_and_link_timestamps():
    payload = SlackNotifier("https://hooks.slack.com/x").render_summary(VIDEO, SUMMARY)
    blocks = payload["blocks"]
    assert blocks[0]["type"] == "header"
    assert len(blocks[0]["text"]["text"]) <= 150
    sections = [b["text"]["text"] for b in blocks if b["type"] == "section"]
    assert all(len(text) <= 3000 for text in sections)
    joined = "\n".join(sections)
    assert "https://youtu.be/abc123?t=75" in joined
    assert "&lt;break&gt;" in joined


def test_long_tiers_are_trimmed():
    from youtube_summarizer.models import Point, Summary

    summary = Summary(
        headline="h",
        tiers={"important": [Point("X" * 300, i) for i in range(30)], "medium": [], "low": []},
    )
    payload = SlackNotifier("u").render_summary(VIDEO, summary)
    for block in payload["blocks"]:
        if block["type"] == "section":
            assert len(block["text"]["text"]) <= SECTION_TEXT_LIMIT + 100
