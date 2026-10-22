"""Email output: a plain-text and HTML message sent over SMTP."""

from __future__ import annotations

import html
import smtplib
from email.message import EmailMessage

from ..config import EmailConfig
from ..formatting import collapse_whitespace, fmt_timestamp
from ..models import TIERS, Point, Summary, Video
from .base import (
    FOOTER_TEXT,
    TIER_EMOJI,
    TIER_LABELS,
    Notifier,
    timestamp_url,
    video_meta,
)

SMTP_TIMEOUT = 30
TIER_COLORS = {"important": "#c0392b", "medium": "#b9770e", "low": "#707b7c"}


def connect(config: EmailConfig) -> smtplib.SMTP:
    """Open an authenticated SMTP connection (implicit TLS on 465, STARTTLS otherwise)."""
    if config.port == 465:
        server: smtplib.SMTP = smtplib.SMTP_SSL(config.host, config.port, timeout=SMTP_TIMEOUT)
    else:
        server = smtplib.SMTP(config.host, config.port, timeout=SMTP_TIMEOUT)
        server.starttls()
    server.login(config.user, config.password)
    return server


def _plain_bullet(point: Point, video: Video) -> str:
    if point.start_sec is not None and point.start_sec >= 0:
        stamp = f"{fmt_timestamp(point.start_sec)} {timestamp_url(video, point.start_sec)}"
        return f"- {point.text} ({stamp})"
    return f"- {point.text}"


def _html_bullet(point: Point, video: Video) -> str:
    text = html.escape(point.text, quote=False)
    if point.start_sec is not None and point.start_sec >= 0:
        url = html.escape(timestamp_url(video, point.start_sec), quote=True)
        return f'<li>{text} (<a href="{url}">{fmt_timestamp(point.start_sec)}</a>)</li>'
    return f"<li>{text}</li>"


class EmailNotifier(Notifier):
    """Emails summaries to one or more recipients."""

    name = "email"

    def __init__(self, config: EmailConfig) -> None:
        self.config = config

    def _message(self, subject: str, plain: str, html_body: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = collapse_whitespace(subject)[:200]  # headers cannot contain newlines
        message["From"] = self.config.from_address
        message["To"] = ", ".join(self.config.to_addresses)
        message.set_content(plain)
        message.add_alternative(html_body, subtype="html")
        return message

    def render_summary(self, video: Video, summary: Summary) -> EmailMessage:
        meta = " • ".join(part for part in (video.channel, video_meta(video)) if part)
        plain = [video.title, meta, video.url, ""]
        url = html.escape(video.url, quote=True)
        body = [
            '<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;'
            'max-width:680px;line-height:1.45">',
            f'<h2 style="margin:0 0 4px"><a href="{url}" style="text-decoration:none">'
            f"{html.escape(video.title, quote=False)}</a></h2>",
            f'<p style="color:#666;margin:0 0 12px">{html.escape(meta, quote=False)}</p>',
        ]
        if summary.headline:
            plain += [summary.headline, ""]
            body.append(f"<p>{html.escape(summary.headline, quote=False)}</p>")
        for tier in TIERS:
            points = summary.tiers.get(tier) or []
            if not points:
                continue
            label = TIER_LABELS[tier]
            plain += [label.upper(), *(_plain_bullet(p, video) for p in points), ""]
            body.append(
                f'<h3 style="color:{TIER_COLORS[tier]};margin:18px 0 6px">'
                f"{TIER_EMOJI[tier]} {html.escape(label, quote=False)}</h3>"
                '<ul style="margin:0;padding-left:20px">'
                + "".join(_html_bullet(p, video) for p in points)
                + "</ul>"
            )
        plain.append(FOOTER_TEXT)
        body.append(f'<p style="color:#888;font-size:12px;margin-top:20px">{FOOTER_TEXT}</p></div>')
        subject = f"[{video.channel}] {video.title}" if video.channel else video.title
        return self._message(subject, "\n".join(plain), "".join(body))

    def render_notice(self, video: Video, reason: str) -> EmailMessage:
        plain = f"Couldn't summarize this video automatically ({reason}).\n{video.url}"
        body = (
            f"<p>Couldn't summarize this video automatically ({html.escape(reason, quote=False)})."
            f'<br><a href="{html.escape(video.url, quote=True)}">'
            f"{html.escape(video.title, quote=False)}</a></p>"
        )
        return self._message(f"{video.title} (summary unavailable)", plain, body)

    def preview(self, payload: EmailMessage) -> str:
        plain = payload.get_body(preferencelist=("plain",))
        text = plain.get_content() if plain is not None else ""
        return f"Subject: {payload['Subject']}\nTo: {payload['To']}\n\n{text}"

    def post(self, payload: EmailMessage) -> None:
        with connect(self.config) as server:
            server.send_message(payload)
