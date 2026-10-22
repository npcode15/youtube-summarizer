from youtube_summarizer.formatting import (
    collapse_whitespace,
    fmt_date,
    fmt_duration,
    fmt_timestamp,
    parse_iso_duration,
)


def test_fmt_timestamp():
    assert fmt_timestamp(0) == "0:00"
    assert fmt_timestamp(754) == "12:34"
    assert fmt_timestamp(3725) == "1:02:05"


def test_fmt_duration():
    assert fmt_duration(2292) == "38 min"
    assert fmt_duration(3900) == "1h 5m"
    assert fmt_duration(None) == ""
    assert fmt_duration(0) == ""


def test_fmt_date():
    assert fmt_date("2026-10-21T14:00:00Z") == "Oct 21, 2026"
    assert fmt_date("2026-10-21T14:00:00+00:00") == "Oct 21, 2026"
    assert fmt_date("not a date") == ""
    assert fmt_date(None) == ""


def test_parse_iso_duration():
    assert parse_iso_duration("PT38M12S") == 2292
    assert parse_iso_duration("PT1H2M3S") == 3723
    assert parse_iso_duration("P0D") == 0
    assert parse_iso_duration("") == 0
    assert parse_iso_duration(None) == 0


def test_collapse_whitespace():
    assert collapse_whitespace("  a \n\t b  ") == "a b"
    assert collapse_whitespace(None) == ""
