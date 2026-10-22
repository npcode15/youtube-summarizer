from youtube_summarizer.config import Settings
from youtube_summarizer.models import Point, Summary, Video
from youtube_summarizer.pipeline import process_video, select_new_videos
from youtube_summarizer.state import State
from youtube_summarizer.transcript import Segment

SETTINGS = Settings(max_attempts=3)
SUMMARY = Summary(headline="h", tiers={"important": [Point("a", 1)], "medium": [], "low": []})


def _video(video_id="v1", *, duration=2300, live="none", published="2026-10-21T14:00:00Z"):
    return Video(
        id=video_id, title=f"Video {video_id}", channel="Chan",
        published=published, duration_sec=duration, live=live,
    )


class Recorder:
    """Stands in for the dispatcher and records what would be delivered."""

    def __init__(self):
        self.summaries = []
        self.notices = []

    def summary(self, video, summary):
        self.summaries.append((video, summary))

    def notice(self, video, reason):
        self.notices.append((video, reason))


def _hooks(*, captions=True, summary=SUMMARY):
    def summarize_fn(video, text):
        if summary is None:
            raise RuntimeError("model down")
        return summary

    return {
        "fetch": lambda video_id: [Segment(0, "hi")] if captions else None,
        "summarize_fn": summarize_fn,
    }


def test_success_delivers_and_finishes():
    sink = Recorder()
    done = process_video(_video(), State(), SETTINGS, sink, **_hooks())
    assert done is True
    assert len(sink.summaries) == 1


def test_missing_captions_are_retried_then_reported():
    state, sink, video = State(), Recorder(), _video()
    hooks = _hooks(captions=False)
    assert process_video(video, state, SETTINGS, sink, **hooks) is False
    assert state.pending[video.id] == 1
    assert process_video(video, state, SETTINGS, sink, **hooks) is False
    assert state.pending[video.id] == 2
    assert not sink.notices
    assert process_video(video, state, SETTINGS, sink, **hooks) is True
    assert len(sink.notices) == 1
    assert "captions" in sink.notices[0][1]
    assert video.id not in state.pending


def test_model_failure_counts_as_a_failed_attempt():
    state, sink, video = State(), Recorder(), _video()
    assert process_video(video, state, SETTINGS, sink, **_hooks(summary=None)) is False
    assert state.pending[video.id] == 1
    assert not sink.summaries and not sink.notices


def test_select_new_videos_filters_and_orders_oldest_first():
    state = State(initialized=True, seen=["old"])
    videos = [
        _video("new2", published="2026-10-21T15:00:00Z"),
        _video("live1", live="upcoming", published="2026-10-21T16:00:00Z"),
        _video("clip", duration=45, published="2026-10-21T12:00:00Z"),
        _video("old", published="2026-10-20T10:00:00Z"),
        _video("new1", published="2026-10-21T13:00:00Z"),
    ]
    todo = select_new_videos(videos, state, min_duration_sec=600)
    assert [v.id for v in todo] == ["new1", "new2"]
    assert "clip" in state.seen  # short clips are never reconsidered
    assert "live1" not in state.seen  # unfinished streams are revisited later
