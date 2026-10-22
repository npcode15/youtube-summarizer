import pytest

from youtube_summarizer.models import Video
from youtube_summarizer.summarizer import (
    SummarizerError,
    build_prompt,
    parse_summary,
    summarize,
)

VIDEO = Video(
    id="abc",
    title="Market Wrap",
    channel="Chan",
    published="2026-10-21T14:00:00Z",
    duration_sec=2300,
)
GOOD_REPLY = (
    '{"headline": "h", "important": [{"t": 75, "text": "SPX support 6,850"}],'
    ' "medium": [], "low": []}'
)


def test_parse_fenced_json():
    summary = parse_summary(f"```json\n{GOOD_REPLY}\n```")
    assert summary.headline == "h"
    assert summary.tiers["important"][0].text == "SPX support 6,850"
    assert summary.tiers["important"][0].start_sec == 75


def test_parse_tolerates_chatter_and_plain_strings():
    reply = 'Here you go: {"headline": "h", "low": ["plain item"]} hope that helps'
    summary = parse_summary(reply)
    assert summary.tiers["low"][0].text == "plain item"
    assert summary.tiers["low"][0].start_sec is None


def test_unparseable_timestamps_become_none():
    summary = parse_summary('{"headline": "h", "medium": [{"t": "soon", "text": "x"}]}')
    assert summary.tiers["medium"][0].start_sec is None


def test_empty_summary_is_rejected():
    with pytest.raises(ValueError):
        parse_summary('{"headline": "x"}')


def test_non_object_is_rejected():
    with pytest.raises(ValueError):
        parse_summary("[1, 2]")


def test_build_prompt_fills_every_placeholder():
    prompt = build_prompt(VIDEO, "[0:00] hi", "a careful reader")
    assert "Market Wrap" in prompt
    assert "a careful reader" in prompt
    assert "[0:00] hi" in prompt
    assert "<<" not in prompt


def test_summarize_retries_once_on_bad_json():
    replies = iter(["not json at all", GOOD_REPLY])
    prompts = []

    def fake_complete(prompt):
        prompts.append(prompt)
        return next(replies)

    summary = summarize(VIDEO, "[0:00] hi", fake_complete, "reader")
    assert len(prompts) == 2
    assert "not valid JSON" in prompts[1]
    assert summary.tiers["important"][0].start_sec == 75


def test_summarize_gives_up_after_repeated_bad_replies():
    with pytest.raises(SummarizerError):
        summarize(VIDEO, "[0:00] hi", lambda prompt: "nope", "reader")
