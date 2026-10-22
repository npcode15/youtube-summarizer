from youtube_summarizer.transcript import Segment, to_timestamped_text


def test_groups_segments_into_timestamped_blocks():
    segments = [
        Segment(0, "hello"),
        Segment(10, "world"),
        Segment(31, "next block"),
        Segment(65, "third"),
    ]
    assert to_timestamped_text(segments).splitlines() == [
        "[0:00] hello world",
        "[0:31] next block",
        "[1:05] third",
    ]


def test_long_transcripts_are_truncated():
    segments = [Segment(i * 40, "x" * 100) for i in range(50)]
    text = to_timestamped_text(segments, max_chars=500)
    assert text.endswith("[transcript truncated]")
    assert len(text) < 600


def test_no_segments_gives_empty_text():
    assert to_timestamped_text([]) == ""
