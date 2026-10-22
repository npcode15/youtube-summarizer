import contextlib
import io

import pytest
from conftest import SUMMARY, VIDEO

from youtube_summarizer.notifiers import DeliveryError, Dispatcher, Notifier


class FakeNotifier(Notifier):
    name = "fake"

    def __init__(self, fail=False):
        self.fail = fail
        self.posted = []

    def render_summary(self, video, summary):
        return f"summary:{video.id}"

    def render_notice(self, video, reason):
        return f"notice:{reason}"

    def post(self, payload):
        if self.fail:
            raise RuntimeError("boom")
        self.posted.append(payload)

    def preview(self, payload):
        return payload


def test_delivers_to_every_output():
    first, second = FakeNotifier(), FakeNotifier()
    dispatcher = Dispatcher([first, second])
    dispatcher.summary(VIDEO, SUMMARY)
    dispatcher.notice(VIDEO, "no captions")
    assert first.posted == second.posted == ["summary:abc123", "notice:no captions"]
    assert dispatcher.failures == []


def test_one_failing_output_does_not_block_the_others():
    good, bad = FakeNotifier(), FakeNotifier(fail=True)
    dispatcher = Dispatcher([bad, good])
    dispatcher.summary(VIDEO, SUMMARY)
    assert good.posted == ["summary:abc123"]
    assert dispatcher.failures == ["fake"]


def test_all_outputs_failing_raises():
    dispatcher = Dispatcher([FakeNotifier(fail=True)])
    with pytest.raises(DeliveryError):
        dispatcher.summary(VIDEO, SUMMARY)


def test_dry_run_prints_and_does_not_post():
    notifier = FakeNotifier(fail=True)  # would raise if post() were called
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        Dispatcher([notifier], dry_run=True).summary(VIDEO, SUMMARY)
    assert "--- fake ---" in out.getvalue()
    assert notifier.posted == []
