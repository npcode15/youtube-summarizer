import logging

from youtube_summarizer.logging_utils import RedactingFormatter


def test_secrets_are_replaced_in_the_final_text():
    formatter = RedactingFormatter("%(message)s", ["sk-ant-secret"])
    record = logging.LogRecord(
        "x", logging.ERROR, __file__, 1, "failed: https://x?key=%s", ("sk-ant-secret",), None
    )
    assert formatter.format(record) == "failed: https://x?key=***"


def test_no_secrets_leaves_text_alone():
    formatter = RedactingFormatter("%(message)s", [])
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", (), None)
    assert formatter.format(record) == "hello"
