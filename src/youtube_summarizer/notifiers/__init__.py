"""Output channels: where finished summaries are delivered."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ..config import Settings
from .base import DeliveryError, Dispatcher, Notifier, Sink
from .discord import DiscordNotifier
from .email_smtp import EmailNotifier
from .slack import SlackNotifier
from .telegram import TelegramNotifier

__all__ = [
    "DeliveryError",
    "DiscordNotifier",
    "Dispatcher",
    "EmailNotifier",
    "Notifier",
    "SlackNotifier",
    "Sink",
    "TelegramNotifier",
    "build_notifiers",
]


def build_notifiers(settings: Settings, names: Sequence[str] | None = None) -> list[Notifier]:
    """Create the notifiers for ``names`` (default: every enabled output in ``settings``)."""
    factories: dict[str, Callable[[], Notifier]] = {
        "discord": lambda: DiscordNotifier(settings.discord.webhook_url),
        "slack": lambda: SlackNotifier(settings.slack.webhook_url),
        "telegram": lambda: TelegramNotifier(
            settings.telegram.bot_token, settings.telegram.chat_id
        ),
        "email": lambda: EmailNotifier(settings.email),
    }
    selected = settings.enabled_outputs() if names is None else list(names)
    return [factories[name]() for name in selected]
