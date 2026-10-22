"""Logging setup that scrubs secrets from every message and traceback."""

from __future__ import annotations

import logging
from collections.abc import Iterable

REDACTED = "***"


class RedactingFormatter(logging.Formatter):
    """A formatter that replaces known secret values in the final log text.

    HTTP library errors often include the full request URL, which can contain an
    API key or webhook token. Scrubbing the finished text also covers tracebacks.
    """

    def __init__(self, fmt: str | None = None, secrets: Iterable[str] = ()) -> None:
        super().__init__(fmt)
        # Longest first, so a secret that contains another one is replaced whole.
        self._secrets = sorted({s for s in secrets if s}, key=len, reverse=True)

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text


def configure_logging(verbose: bool = False, secrets: Iterable[str] = ()) -> None:
    """Send all logs to stderr at INFO (or DEBUG) level, with secrets redacted."""
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(asctime)s [%(levelname)s] %(message)s", secrets))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
