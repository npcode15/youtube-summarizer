"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_READER_CONTEXT = (
    "someone who wants the specific numbers, dates and claims in this video "
    "that could change a decision they make"
)
OUTPUT_NAMES: tuple[str, ...] = ("discord", "slack", "telegram", "email")
MIN_SECRET_LENGTH = 6  # shorter values are not redacted from logs (too likely to match by accident)


class ConfigError(ValueError):
    """Raised when configuration is malformed."""


@dataclass(frozen=True)
class DiscordConfig:
    """Discord incoming webhook."""

    webhook_url: str = ""

    def missing(self) -> list[str]:
        return [] if self.webhook_url else ["DISCORD_WEBHOOK_URL"]

    def secrets(self) -> list[str]:
        return [self.webhook_url]


@dataclass(frozen=True)
class SlackConfig:
    """Slack incoming webhook."""

    webhook_url: str = ""

    def missing(self) -> list[str]:
        return [] if self.webhook_url else ["SLACK_WEBHOOK_URL"]

    def secrets(self) -> list[str]:
        return [self.webhook_url]


@dataclass(frozen=True)
class TelegramConfig:
    """Telegram bot token and the chat that should receive messages."""

    bot_token: str = ""
    chat_id: str = ""

    def missing(self) -> list[str]:
        names = []
        if not self.bot_token:
            names.append("TELEGRAM_BOT_TOKEN")
        if not self.chat_id:
            names.append("TELEGRAM_CHAT_ID")
        return names

    def secrets(self) -> list[str]:
        return [self.bot_token]


@dataclass(frozen=True)
class EmailConfig:
    """SMTP account used to send summaries by email."""

    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    sender: str = ""  # defaults to ``user``
    recipients: str = ""  # comma-separated

    @property
    def from_address(self) -> str:
        return self.sender or self.user

    @property
    def to_addresses(self) -> list[str]:
        return [address.strip() for address in self.recipients.split(",") if address.strip()]

    def missing(self) -> list[str]:
        names = []
        if not self.host:
            names.append("SMTP_HOST")
        if not self.user:
            names.append("SMTP_USER")
        if not self.password:
            names.append("SMTP_PASSWORD")
        if not self.to_addresses:
            names.append("EMAIL_TO")
        return names

    def secrets(self) -> list[str]:
        return [self.password]


@dataclass(frozen=True)
class Settings:
    """All tunables for one run. Build it with :meth:`Settings.from_env`."""

    channel: str = ""
    youtube_api_key: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = DEFAULT_MODEL
    reader_context: str = DEFAULT_READER_CONTEXT
    transcript_proxy_url: str = ""
    state_file: Path = Path("state/seen_videos.json")
    max_videos_per_run: int = 3
    min_duration_sec: int = 600
    max_attempts: int = 4
    outputs: tuple[str, ...] = ()  # explicit OUTPUTS choice; empty means auto-detect
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    email: EmailConfig = field(default_factory=EmailConfig)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Read settings from ``environ`` (defaults to ``os.environ``).

        Empty or whitespace-only values count as unset, which matters on GitHub
        Actions where a missing secret is passed through as an empty string.
        """
        env = os.environ if environ is None else environ

        def text(name: str, default: str = "") -> str:
            value = (env.get(name) or "").strip()
            return value or default

        def integer(name: str, default: int) -> int:
            raw = text(name)
            if not raw:
                return default
            try:
                return int(raw)
            except ValueError as exc:
                raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc

        requested = [part.strip().lower() for part in text("OUTPUTS").split(",") if part.strip()]
        unknown = [name for name in requested if name not in OUTPUT_NAMES]
        if unknown:
            raise ConfigError(
                f"OUTPUTS has unknown value(s) {unknown}; choose from {', '.join(OUTPUT_NAMES)}"
            )

        return cls(
            channel=text("YT_CHANNEL"),
            youtube_api_key=text("YOUTUBE_API_KEY"),
            anthropic_api_key=text("ANTHROPIC_API_KEY"),
            anthropic_model=text("ANTHROPIC_MODEL", DEFAULT_MODEL),
            reader_context=text("USER_CONTEXT", DEFAULT_READER_CONTEXT),
            transcript_proxy_url=text("TRANSCRIPT_PROXY_URL"),
            state_file=Path(text("STATE_FILE", "state/seen_videos.json")),
            max_videos_per_run=integer("MAX_VIDEOS_PER_RUN", 3),
            min_duration_sec=integer("MIN_DURATION_SEC", 600),
            max_attempts=integer("MAX_TRANSCRIPT_ATTEMPTS", 4),
            outputs=tuple(dict.fromkeys(requested)),
            discord=DiscordConfig(webhook_url=text("DISCORD_WEBHOOK_URL")),
            slack=SlackConfig(webhook_url=text("SLACK_WEBHOOK_URL")),
            telegram=TelegramConfig(
                bot_token=text("TELEGRAM_BOT_TOKEN"), chat_id=text("TELEGRAM_CHAT_ID")
            ),
            email=EmailConfig(
                host=text("SMTP_HOST"),
                port=integer("SMTP_PORT", 587),
                user=text("SMTP_USER"),
                password=text("SMTP_PASSWORD"),
                sender=text("EMAIL_FROM"),
                recipients=text("EMAIL_TO"),
            ),
        )

    def output_config(
        self, name: str
    ) -> DiscordConfig | SlackConfig | TelegramConfig | EmailConfig:
        """Return the configuration object for the output called ``name``."""
        return getattr(self, name)

    def enabled_outputs(self) -> list[str]:
        """Outputs to use: the explicit ``OUTPUTS`` list, else every fully configured one."""
        if self.outputs:
            return list(self.outputs)
        return [name for name in OUTPUT_NAMES if not self.output_config(name).missing()]

    def problems(self, *, dry_run: bool = False) -> list[str]:
        """Return a human-readable message for every missing required value."""
        problems = []
        if not self.channel:
            problems.append("YT_CHANNEL is not set")
        if not self.anthropic_api_key:
            problems.append("ANTHROPIC_API_KEY is not set")
        if dry_run:
            return problems
        enabled = self.enabled_outputs()
        if not enabled:
            problems.append(
                "No output is configured. Set DISCORD_WEBHOOK_URL, SLACK_WEBHOOK_URL, "
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, or SMTP_HOST, SMTP_USER, "
                "SMTP_PASSWORD and EMAIL_TO"
            )
        for name in enabled:
            for variable in self.output_config(name).missing():
                problems.append(f"{variable} is not set (required by the {name} output)")
        return problems

    def warnings(self) -> list[str]:
        """Messages about partly configured outputs that auto-detection will ignore."""
        if self.outputs:
            return []
        found = []
        for name in OUTPUT_NAMES:
            missing = self.output_config(name).missing()
            if missing and len(missing) < _required_count(self.output_config(name)):
                found.append(
                    f"The {name} output is partly configured and will be ignored; "
                    f"missing: {', '.join(missing)}"
                )
        return found

    def secret_values(self) -> list[str]:
        """Every secret value, so logs can be scrubbed of them."""
        values = [self.youtube_api_key, self.anthropic_api_key, self.transcript_proxy_url]
        for name in OUTPUT_NAMES:
            values.extend(self.output_config(name).secrets())
        return [v for v in values if v and len(v) >= MIN_SECRET_LENGTH]


def _required_count(config: DiscordConfig | SlackConfig | TelegramConfig | EmailConfig) -> int:
    """Number of required variables for an output (what ``missing()`` returns when unset)."""
    return len(type(config)().missing())


def parse_env_text(text: str) -> dict[str, str]:
    """Parse ``KEY=value`` lines (comments, blank lines, simple quotes)."""
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        result[key] = value
    return result


def load_dotenv_if_available(path: str | Path = ".env") -> bool:
    """Load ``path`` (default ``./.env``) into the environment; returns True if it was read.

    Variables already set in the real environment win. Needs no extra package.
    """
    env_file = Path(path)
    if not env_file.is_file():
        return False
    for key, value in parse_env_text(env_file.read_text(encoding="utf-8-sig")).items():
        if not os.environ.get(key):
            os.environ[key] = value
    return True
