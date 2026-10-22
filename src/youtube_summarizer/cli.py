"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from .config import ConfigError, Settings, load_dotenv_if_available
from .logging_utils import configure_logging
from .notifiers import DeliveryError
from .pipeline import run
from .youtube import YouTubeError

log = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="youtube-summarizer",
        description="Summarize a YouTube channel's new videos and send them to Discord, "
        "Slack, Telegram or email.",
        epilog="First time? Run `youtube-summarizer init` for guided setup.",
    )
    parser.add_argument(
        "--test-latest",
        action="store_true",
        help="summarize the newest video now, ignoring saved state",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would be sent instead of sending it, and do not save state",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one polling cycle, or the setup helper when called as ``init``."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "init":
        from .setup_wizard import init_main

        return init_main(arguments[1:])

    load_dotenv_if_available()
    args = build_parser().parse_args(arguments)
    configure_logging(args.verbose)
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        log.error("%s", exc)
        return 2
    configure_logging(args.verbose, settings.secret_values())  # scrub secrets from all logs
    for warning in settings.warnings():
        log.warning("%s", warning)
    problems = settings.problems(dry_run=args.dry_run)
    if problems:
        for problem in problems:
            log.error("%s", problem)
        return 2
    try:
        return run(settings, test_latest=args.test_latest, dry_run=args.dry_run)
    except (YouTubeError, DeliveryError) as exc:
        log.error("%s", exc)
        return 1
