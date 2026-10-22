from conftest import SUMMARY, VIDEO

from youtube_summarizer.config import EmailConfig
from youtube_summarizer.notifiers.email_smtp import EmailNotifier

CONFIG = EmailConfig(
    host="smtp.example.com", port=587, user="me@example.com", password="pw",
    sender="", recipients="a@example.com, b@example.com",
)


def test_message_has_plain_and_html_parts_and_recipients():
    message = EmailNotifier(CONFIG).render_summary(VIDEO, SUMMARY)
    assert message["To"] == "a@example.com, b@example.com"
    assert message["From"] == "me@example.com"  # falls back to the SMTP user
    assert "\n" not in message["Subject"]
    assert message.get_body(("plain",)) is not None
    html = message.get_body(("html",)).get_content()
    assert "https://youtu.be/abc123?t=75" in html
    assert "&lt;break&gt;" in html


def test_subject_newlines_cannot_inject_headers():
    from dataclasses import replace

    video = replace(VIDEO, title="Hi\r\nBcc: evil@example.com")
    message = EmailNotifier(CONFIG).render_summary(video, SUMMARY)
    assert "Bcc" not in message.keys()
