"""``youtube-summarizer init``: guided setup that validates keys and stores them safely.

Secrets are typed with hidden input, checked against the real services without
posting anything, then saved to GitHub repository secrets (``gh secret set``,
value passed on stdin) and/or a local ``.env`` file. Nothing is printed back.
"""

from __future__ import annotations

import argparse
import getpass
import os
import shutil
import smtplib
import ssl
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

from .config import DEFAULT_MODEL, OUTPUT_NAMES, ConfigError, Settings, parse_env_text
from .notifiers import Dispatcher, build_notifiers
from .youtube import YouTubeError, fetch_via_api, resolve_channel_id

TIMEOUT = 15
WORKFLOW_NAME = "Summarize new videos"
SECRET_PROMPTS = {"YOUTUBE_API_KEY", "ANTHROPIC_API_KEY", "DISCORD_WEBHOOK_URL",
                  "SLACK_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN", "SMTP_PASSWORD"}

# Variables each output needs: (env name, human prompt, default)
OUTPUT_FIELDS: dict[str, list[tuple[str, str, str]]] = {
    "discord": [("DISCORD_WEBHOOK_URL", "Discord webhook URL", "")],
    "slack": [("SLACK_WEBHOOK_URL", "Slack incoming-webhook URL", "")],
    "telegram": [
        ("TELEGRAM_BOT_TOKEN", "Telegram bot token (from @BotFather)", ""),
        ("TELEGRAM_CHAT_ID", "Telegram chat ID", ""),
    ],
    "email": [
        ("SMTP_HOST", "SMTP host (e.g. smtp.gmail.com)", ""),
        ("SMTP_PORT", "SMTP port", "587"),
        ("SMTP_USER", "SMTP username", ""),
        ("SMTP_PASSWORD", "SMTP password / app password", ""),
        ("EMAIL_FROM", "From address (blank = username)", ""),
        ("EMAIL_TO", "To address(es), comma separated", ""),
    ],
}


class Console(Protocol):
    def say(self, message: str) -> None: ...
    def ask(self, prompt: str, default: str = "") -> str: ...
    def secret(self, prompt: str) -> str: ...
    def confirm(self, prompt: str, default: bool = True) -> bool: ...


class TerminalConsole:
    """Real terminal I/O; secrets use hidden input."""

    def say(self, message: str) -> None:
        print(message)

    def ask(self, prompt: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        return input(f"{prompt}{suffix}: ").strip() or default

    def secret(self, prompt: str) -> str:
        return getpass.getpass(f"{prompt} (hidden): ").strip()

    def confirm(self, prompt: str, default: bool = True) -> bool:
        hint = "Y/n" if default else "y/N"
        answer = input(f"{prompt} [{hint}]: ").strip().lower()
        return default if not answer else answer.startswith("y")


Check = tuple[bool, str]  # (ok, message)
Runner = Callable[..., "subprocess.CompletedProcess[str]"]


# --------------------------------------------------------------------------- validators
def check_youtube(values: Mapping[str, str]) -> Check:
    try:
        channel_id = resolve_channel_id(values["YT_CHANNEL"], values["YOUTUBE_API_KEY"])
        videos = fetch_via_api(channel_id, values["YOUTUBE_API_KEY"])
    except (YouTubeError, requests.RequestException) as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        detail = f"HTTP {status}" if status else type(exc).__name__
        return False, f"YouTube rejected the request ({detail})."
    return True, f"YouTube OK: {len(videos)} recent videos found."


def check_anthropic(values: Mapping[str, str]) -> Check:
    model = values.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
    headers = {"x-api-key": values["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"}
    try:
        resp = requests.get(
            f"https://api.anthropic.com/v1/models/{model}", headers=headers, timeout=TIMEOUT
        )
    except requests.RequestException:
        return True, "Could not reach Anthropic to verify the key (continuing)."
    if resp.status_code == 401:
        return False, "Anthropic rejected this API key."
    if resp.status_code == 404:
        return False, f"Anthropic does not know the model '{model}'."
    return True, "Anthropic key accepted."


def check_discord(values: Mapping[str, str]) -> Check:
    url = values["DISCORD_WEBHOOK_URL"]
    if "/api/webhooks/" not in url:
        return False, "That does not look like a Discord webhook URL."
    try:
        resp = requests.get(url, timeout=TIMEOUT)
    except requests.RequestException:
        return True, "Could not reach Discord to verify the webhook (continuing)."
    if resp.status_code in (401, 404):
        return False, "Discord says this webhook does not exist."
    return True, "Discord webhook OK."


def check_slack(values: Mapping[str, str]) -> Check:
    if not values["SLACK_WEBHOOK_URL"].startswith("https://hooks.slack.com/"):
        return False, "Slack webhook URLs start with https://hooks.slack.com/"
    return True, "Slack URL format OK (not tested; use the test message to confirm)."


def check_telegram(values: Mapping[str, str]) -> Check:
    base = f"https://api.telegram.org/bot{values['TELEGRAM_BOT_TOKEN']}"
    try:
        me = requests.get(f"{base}/getMe", timeout=TIMEOUT)
        if me.status_code in (401, 404):
            return False, "Telegram rejected this bot token."
        chat = requests.get(
            f"{base}/getChat", params={"chat_id": values["TELEGRAM_CHAT_ID"]}, timeout=TIMEOUT
        )
    except requests.RequestException:
        return True, "Could not reach Telegram to verify (continuing)."
    if chat.status_code != 200:
        return False, "Telegram cannot see that chat. Message the bot first, then retry."
    return True, "Telegram bot and chat OK."


def check_email(values: Mapping[str, str]) -> Check:
    try:
        port = int(values.get("SMTP_PORT") or 587)
    except ValueError:
        return False, "SMTP port must be a number."
    host = values["SMTP_HOST"]
    try:
        if port == 465:
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                host, port, timeout=TIMEOUT, context=ssl.create_default_context()
            )
        else:
            server = smtplib.SMTP(host, port, timeout=TIMEOUT)
        with server:
            if port != 465:
                server.starttls(context=ssl.create_default_context())
            if values.get("SMTP_USER"):
                server.login(values["SMTP_USER"], values.get("SMTP_PASSWORD", ""))
    except smtplib.SMTPAuthenticationError:
        return False, "The mail server rejected the username or password."
    except (OSError, smtplib.SMTPException) as exc:
        return False, f"Could not connect to the mail server ({type(exc).__name__})."
    return True, "SMTP login OK."


CHECKERS: dict[str, Callable[[Mapping[str, str]], Check]] = {
    "youtube": check_youtube,
    "anthropic": check_anthropic,
    "discord": check_discord,
    "slack": check_slack,
    "telegram": check_telegram,
    "email": check_email,
}


# --------------------------------------------------------------------------- storage
def write_env_file(path: Path, values: Mapping[str, str]) -> None:
    """Merge ``values`` into ``path``, keeping unrelated lines; file mode 600."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = {k: v for k, v in values.items() if v != ""}
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip().removeprefix("export ").strip()
        if "=" in line and not line.lstrip().startswith("#") and key in remaining:
            out.append(_env_line(key, remaining.pop(key)))
        else:
            out.append(line)
    out.extend(_env_line(k, v) for k, v in remaining.items())
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass  # e.g. filesystems without POSIX permissions


def _env_line(key: str, value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{key}="{escaped}"'


def push_github_secrets(
    values: Mapping[str, str], repo: str | None, run: Runner = subprocess.run
) -> list[str]:
    """Set each value as a GitHub secret via ``gh``; returns names that failed."""
    failed = []
    for name, value in values.items():
        if value == "":
            continue
        command = ["gh", "secret", "set", name] + (["--repo", repo] if repo else [])
        result = run(command, input=value, text=True, capture_output=True)
        if result.returncode != 0:
            failed.append(name)
    return failed


# --------------------------------------------------------------------------- flow
@dataclass
class Options:
    repo: str | None = None
    env_file: Path = Path(".env")
    validate: bool = True
    from_env: bool = False
    assume_yes: bool = False


def _prompt_value(console: Console, name: str, label: str, default: str) -> str:
    if name in SECRET_PROMPTS:
        value = console.secret(label)
        return value or default
    return console.ask(label, default)


def _collect_group(
    console: Console, label: str, fields: Sequence[tuple[str, str, str]],
    checker: Callable[[Mapping[str, str]], Check] | None, context: Mapping[str, str],
    validate: bool,
) -> dict[str, str]:
    """Ask for a group of values, re-asking until the checker passes (or user skips)."""
    while True:
        values = {name: _prompt_value(console, name, text, default)
                  for name, text, default in fields}
        if not validate or checker is None:
            return values
        ok, message = checker({**context, **values})
        console.say(("  ✔ " if ok else "  ✘ ") + message)
        if ok:
            return values
        if not console.confirm(f"Try {label} again?", True):
            console.say(f"  Skipping validation for {label}; saving what you typed.")
            return values


def gather_interactive(console: Console, options: Options) -> dict[str, str]:
    console.say("YouTube Summarizer setup. Secrets are hidden and never printed.\n")
    values: dict[str, str] = {}
    values["YT_CHANNEL"] = console.ask(
        "YouTube channel (ID starting UC, @handle or URL)", ""
    )
    console.say("\nYouTube Data API key (free: enable 'YouTube Data API v3' in Google Cloud).")
    values |= _collect_group(
        console, "YouTube key", [("YOUTUBE_API_KEY", "YouTube API key", "")],
        CHECKERS["youtube"], values, options.validate,
    )
    console.say("\nAnthropic API key (console.anthropic.com).")
    values |= _collect_group(
        console, "Anthropic key", [("ANTHROPIC_API_KEY", "Anthropic API key", "")],
        CHECKERS["anthropic"], values, options.validate,
    )
    console.say(f"\nOutputs available: {', '.join(OUTPUT_NAMES)}")
    chosen = [n for n in OUTPUT_NAMES if console.confirm(f"Send summaries to {n}?", n == "discord")]
    for name in chosen:
        console.say(f"\n{name.capitalize()} settings:")
        values |= _collect_group(
            console, name, OUTPUT_FIELDS[name], CHECKERS[name], values, options.validate
        )
    if len(chosen) != len(OUTPUT_NAMES):
        values["OUTPUTS"] = ",".join(chosen)
    context = console.ask("\nWho are the summaries for? (optional, shapes what is 'Important')", "")
    if context:
        values["USER_CONTEXT"] = context
    return values


def gather_from_env(
    environ: Mapping[str, str], env_file: Path, console: Console, options: Options
) -> dict[str, str]:
    """Collect values from the environment plus ``env_file`` (environment wins)."""
    source: dict[str, str] = {}
    if env_file.exists():
        source.update(parse_env_text(env_file.read_text(encoding="utf-8")))
    source.update({k: v for k, v in environ.items() if v})
    names = {"YT_CHANNEL", "YOUTUBE_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
             "USER_CONTEXT", "TRANSCRIPT_PROXY_URL", "OUTPUTS"}
    for fields in OUTPUT_FIELDS.values():
        names.update(name for name, _, _ in fields)
    values = {k: source[k] for k in sorted(names) if source.get(k)}
    if options.validate:
        if values.get("YOUTUBE_API_KEY") and values.get("YT_CHANNEL"):
            ok, message = CHECKERS["youtube"](values)
        else:
            ok, message = False, "YouTube key or channel is missing."
        console.say(("  ✔ " if ok else "  ✘ ") + message)
        if values.get("ANTHROPIC_API_KEY"):
            ok, message = CHECKERS["anthropic"](values)
        else:
            ok, message = False, "Anthropic key is missing."
        console.say(("  ✔ " if ok else "  ✘ ") + message)
    return values


def send_test_message(values: Mapping[str, str], console: Console) -> bool:
    from .models import Point, Summary, Video

    try:
        settings = Settings.from_env(values)
    except ConfigError as exc:
        console.say(f"  ✘ {exc}")
        return False
    notifiers = build_notifiers(settings)
    if not notifiers:
        console.say("  No output is fully configured, so no test message was sent.")
        return False
    video = Video(id="dQw4w9WgXcQ", title="Setup test", channel="YouTube Summarizer",
                  published="2026-01-01T00:00:00Z")
    summary = Summary(
        headline="If you can read this, delivery works.",
        tiers={"important": [Point("Setup is complete.", 0)], "medium": [], "low": []},
    )
    dispatcher = Dispatcher(notifiers)
    try:
        dispatcher.summary(video, summary)
    except Exception as exc:
        console.say(f"  ✘ Test message failed ({type(exc).__name__}).")
        return False
    if dispatcher.failures:
        console.say(f"  ✘ Failed outputs: {', '.join(dispatcher.failures)}")
        return False
    console.say("  ✔ Test message sent.")
    return True


def manual_secrets_help(values: Mapping[str, str], repo: str | None) -> str:
    """Explain how to add the secrets by hand when the GitHub CLI is missing (no values shown)."""
    where = f"https://github.com/{repo}/settings/secrets/actions" if repo else (
        "your repository > Settings > Secrets and variables > Actions"
    )
    names = "\n".join(f"    {name}" for name in values if values[name])
    return (
        "\nThe GitHub CLI (`gh`) is not installed, so secrets cannot be uploaded automatically.\n"
        "Either install it (https://cli.github.com/, then `gh auth login` and re-run this "
        "command),\nor add these repository secrets by hand at\n"
        f"  {where}\n{names}\n"
        "Saving a .env file below lets you copy values from it, or re-run "
        "`youtube-summarizer init --from-env` once gh is installed."
    )


def finish(
    values: Mapping[str, str], console: Console, options: Options,
    run: Runner = subprocess.run, which: Callable[[str], str | None] = shutil.which,
) -> int:
    """Save ``values`` where the user wants them, then offer a test."""
    has_gh = which("gh") is not None
    to_github = has_gh and (options.assume_yes or options.from_env or console.confirm(
        "\nSave as GitHub repository secrets with `gh`?", True))
    if not has_gh:
        console.say(manual_secrets_help(values, options.repo))
    code = 0
    if to_github:
        failed = push_github_secrets(values, options.repo, run)
        if failed:
            console.say(f"  ✘ Could not set: {', '.join(failed)}. Run `gh auth login` and retry.")
            code = 1
        else:
            console.say("  ✔ GitHub secrets saved.")
    write_env = options.assume_yes or console.confirm(
        f"Also write {options.env_file} for local runs?", not has_gh
    )
    if not options.from_env and write_env:
        write_env_file(options.env_file, values)
        console.say(f"  ✔ Wrote {options.env_file} (kept out of git by .gitignore).")
    if not options.from_env and console.confirm("Send a test message now?", True):
        if not send_test_message(values, console):
            code = 1
    if to_github and code == 0 and console.confirm("Trigger a test run on GitHub now?", False):
        command = ["gh", "workflow", "run", WORKFLOW_NAME, "-f", "test_latest=true"]
        if options.repo:
            command += ["--repo", options.repo]
        result = run(command, text=True, capture_output=True)
        console.say("  ✔ Workflow started." if result.returncode == 0
                    else "  ✘ Could not start the workflow.")
    console.say("\nDone.")
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="youtube-summarizer init",
        description="Guided setup: validate keys and save them as GitHub secrets and/or .env.",
    )
    parser.add_argument("--repo", help="GitHub repo as owner/name (default: current checkout)")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--no-validate", action="store_true", help="skip live key checks")
    parser.add_argument("--from-env", action="store_true",
                        help="non-interactive: read env vars / .env and push them to GitHub")
    parser.add_argument("--yes", action="store_true", help="accept default answers")
    return parser


def init_main(
    argv: Sequence[str] | None = None,
    *,
    console: Console | None = None,
    environ: Mapping[str, str] | None = None,
    run: Runner = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> int:
    args = build_parser().parse_args(list(argv or []))
    console = console or TerminalConsole()
    options = Options(
        repo=args.repo, env_file=args.env_file, validate=not args.no_validate,
        from_env=args.from_env, assume_yes=args.yes,
    )
    try:
        if options.from_env:
            values = gather_from_env(
                os.environ if environ is None else environ, options.env_file, console, options
            )
        else:
            values = gather_interactive(console, options)
    except (KeyboardInterrupt, EOFError):
        console.say("\nCancelled; nothing was saved.")
        return 130
    required = ("YT_CHANNEL", "YOUTUBE_API_KEY", "ANTHROPIC_API_KEY")
    missing = [name for name in required if not values.get(name)]
    if missing:
        console.say(f"Missing required values: {', '.join(missing)}")
        return 2
    return finish(values, console, options, run, which)
