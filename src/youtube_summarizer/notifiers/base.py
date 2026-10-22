"""The notifier interface, shared formatting pieces, and the dispatcher that fans out messages."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, ClassVar, Protocol

from ..formatting import fmt_date, fmt_duration
from ..models import Summary, Video

log = logging.getLogger(__name__)

FOOTER_TEXT = "Built from auto-captions - verify key numbers in the video"
BULLET = "•"
TIER_EMOJI = {"important": "\U0001F534", "medium": "\U0001F7E0", "low": "⚪"}
TIER_LABELS = {
    "important": "Important - could change a decision",
    "medium": "Medium - supporting data & context",
    "low": "Low - background / FYI",
}


def video_meta(video: Video) -> str:
    """``38 min • Oct 21, 2026`` (parts that are unknown are left out)."""
    parts = (fmt_duration(video.duration_sec), fmt_date(video.published))
    return f" {BULLET} ".join(part for part in parts if part)


def timestamp_url(video: Video, start_sec: int) -> str:
    """A link that opens ``video`` at ``start_sec``."""
    return f"https://youtu.be/{video.id}?t={start_sec}"


class DeliveryError(RuntimeError):
    """Raised when a message could not be delivered to any output."""


class Notifier(ABC):
    """One place summaries can be sent (Discord, Slack, Telegram, email...)."""

    name: ClassVar[str]

    @abstractmethod
    def render_summary(self, video: Video, summary: Summary) -> Any:
        """Build the payload for a summary without sending it."""

    @abstractmethod
    def render_notice(self, video: Video, reason: str) -> Any:
        """Build the payload for a "could not summarize" notice."""

    @abstractmethod
    def post(self, payload: Any) -> None:
        """Send a payload produced by one of the ``render_*`` methods."""

    def preview(self, payload: Any) -> str:
        """Human-readable text for ``--dry-run``."""
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, indent=2, ensure_ascii=False)


class Sink(Protocol):
    """What the pipeline needs from a dispatcher (lets tests substitute a recorder)."""

    def summary(self, video: Video, summary: Summary) -> None: ...

    def notice(self, video: Video, reason: str) -> None: ...


class Dispatcher:
    """Send each message to every configured output.

    One failing output does not stop the others. If *every* output fails, a
    :class:`DeliveryError` is raised so the video is retried on the next run.
    Names of outputs that failed are collected in :attr:`failures`.
    """

    def __init__(self, notifiers: Sequence[Notifier], *, dry_run: bool = False) -> None:
        self.notifiers = list(notifiers)
        self.dry_run = dry_run
        self.failures: list[str] = []

    def summary(self, video: Video, summary: Summary) -> None:
        self._send(lambda notifier: notifier.render_summary(video, summary))

    def notice(self, video: Video, reason: str) -> None:
        self._send(lambda notifier: notifier.render_notice(video, reason))

    def _send(self, render: Any) -> None:
        delivered = 0
        for notifier in self.notifiers:
            try:
                payload = render(notifier)
                if self.dry_run:
                    print(f"--- {notifier.name} ---\n{notifier.preview(payload)}")
                else:
                    notifier.post(payload)
                delivered += 1
            except Exception as exc:  # one broken output must not block the others
                log.error("%s output failed: %s: %s", notifier.name, type(exc).__name__, exc)
                log.debug("Traceback for the %s failure", notifier.name, exc_info=True)
                self.failures.append(notifier.name)
        if self.notifiers and not self.dry_run and delivered == 0:
            raise DeliveryError("every output failed")
