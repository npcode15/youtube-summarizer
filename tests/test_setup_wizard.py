import subprocess
from pathlib import Path

from youtube_summarizer import setup_wizard as wizard


class ScriptedConsole:
    def __init__(self, asks=(), secrets=(), confirms=()):
        self.asks, self.secrets, self.confirms = list(asks), list(secrets), list(confirms)
        self.said = []

    def say(self, message):
        self.said.append(message)

    def ask(self, prompt, default=""):
        return self.asks.pop(0) if self.asks else default

    def secret(self, prompt):
        return self.secrets.pop(0)

    def confirm(self, prompt, default=True):
        return self.confirms.pop(0) if self.confirms else default


def test_parse_env_text_handles_quotes_and_comments():
    text = '# c\nA=1\nexport B="x y"\nC=\'z\'\nbad line\n'
    assert wizard.parse_env_text(text) == {"A": "1", "B": "x y", "C": "z"}


def test_write_env_file_merges_and_keeps_other_lines(tmp_path):
    path = tmp_path / ".env"
    path.write_text("# mine\nKEEP=1\nA=old\n")
    wizard.write_env_file(path, {"A": 'new "q"', "B": "2", "EMPTY": ""})
    parsed = wizard.parse_env_text(path.read_text())
    assert parsed == {"KEEP": "1", "A": 'new "q"', "B": "2"}
    assert "# mine" in path.read_text()


def test_push_github_secrets_passes_values_on_stdin_never_in_arguments():
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs["input"]))
        return subprocess.CompletedProcess(command, 1 if command[3] == "B" else 0)

    failed = wizard.push_github_secrets({"A": "va", "B": "vb", "C": ""}, "me/repo", run)
    assert failed == ["B"]
    assert calls[0] == (["gh", "secret", "set", "A", "--repo", "me/repo"], "va")
    assert all("va" not in part and "vb" not in part for command, _ in calls for part in command)


def test_slack_and_discord_format_checks():
    assert not wizard.check_slack({"SLACK_WEBHOOK_URL": "nope"})[0]
    assert wizard.check_slack({"SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/x"})[0]
    assert not wizard.check_discord({"DISCORD_WEBHOOK_URL": "https://example.com"})[0]


def test_collect_group_reasks_until_checker_passes():
    console = ScriptedConsole(secrets=["bad", "good"], confirms=[True])
    values = wizard._collect_group(
        console, "Discord", [("DISCORD_WEBHOOK_URL", "URL", "")],
        lambda v: (v["DISCORD_WEBHOOK_URL"] == "good", "msg"), {}, True,
    )
    assert values == {"DISCORD_WEBHOOK_URL": "good"}


def test_from_env_pushes_to_github_without_prompts(tmp_path):
    calls = []

    def run(command, **kwargs):
        calls.append(command[3])
        return subprocess.CompletedProcess(command, 0)

    environ = {"YT_CHANNEL": "UCabc", "YOUTUBE_API_KEY": "k1", "ANTHROPIC_API_KEY": "k2",
               "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1/x"}
    code = wizard.init_main(
        ["--from-env", "--no-validate", "--env-file", str(tmp_path / "none")],
        console=ScriptedConsole(confirms=[False]), environ=environ, run=run,
        which=lambda name: "/usr/bin/gh",
    )
    assert code == 0
    assert sorted(calls) == sorted(environ)


def test_from_env_reports_missing_required_values(tmp_path):
    console = ScriptedConsole()
    code = wizard.init_main(
        ["--from-env", "--no-validate", "--env-file", str(Path(tmp_path) / "none")],
        console=console, environ={"YT_CHANNEL": "x"}, which=lambda name: None,
    )
    assert code == 2
    assert any("ANTHROPIC_API_KEY" in line for line in console.said)


def test_without_gh_the_helper_lists_secret_names_not_values(tmp_path):
    console = ScriptedConsole(confirms=[True, False])  # write .env, skip test message
    options = wizard.Options(env_file=tmp_path / ".env", validate=False)
    code = wizard.finish({"YT_CHANNEL": "UCabc", "ANTHROPIC_API_KEY": "sk-secret-value"},
                         console, options, which=lambda name: None)
    said = "\n".join(console.said)
    assert code == 0
    assert "ANTHROPIC_API_KEY" in said and "sk-secret-value" not in said
    assert (tmp_path / ".env").exists()
