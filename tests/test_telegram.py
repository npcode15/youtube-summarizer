from conftest import SUMMARY, VIDEO
from youtube_summarizer.notifiers.telegram import TelegramNotifier


def test_messages_are_html_escaped_and_within_limit():
    messages = TelegramNotifier("123:abc", "42").render_summary(VIDEO, SUMMARY)
    assert messages
    assert all(len(m) <= 4096 for m in messages)
    text = "\n".join(messages)
    assert "&lt;break&gt;" in text
    assert "https://youtu.be/abc123?t=75" in text


def test_long_summary_is_split_but_stays_within_limit():
    from youtube_summarizer.models import Point, Summary

    summary = Summary(
        headline="h",
        tiers={"important": [Point("X" * 400, i) for i in range(40)], "medium": [], "low": []},
    )
    messages = TelegramNotifier("t", "c").render_summary(VIDEO, summary)
    assert all(len(m) <= 4096 for m in messages)
