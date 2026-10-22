import pytest

from youtube_summarizer.config import DEFAULT_MODEL, ConfigError, Settings


def test_empty_values_fall_back_to_defaults():
    settings = Settings.from_env(
        {"ANTHROPIC_MODEL": "", "MAX_VIDEOS_PER_RUN": "  ", "YT_CHANNEL": " UCabc "}
    )
    assert settings.anthropic_model == DEFAULT_MODEL
    assert settings.max_videos_per_run == 3
    assert settings.channel == "UCabc"


def test_invalid_integer_raises():
    with pytest.raises(ConfigError):
        Settings.from_env({"MIN_DURATION_SEC": "ten"})


def test_problems_lists_every_missing_required_value():
    problems = Settings.from_env({}).problems()
    assert any("YT_CHANNEL" in p for p in problems)
    assert any("ANTHROPIC_API_KEY" in p for p in problems)
    assert any("No output is configured" in p for p in problems)


def test_dry_run_does_not_require_an_output():
    settings = Settings.from_env({"YT_CHANNEL": "x", "ANTHROPIC_API_KEY": "k"})
    assert settings.problems(dry_run=True) == []
    assert any("No output" in p for p in settings.problems())


def test_outputs_are_auto_detected():
    settings = Settings.from_env(
        {
            "YT_CHANNEL": "x",
            "ANTHROPIC_API_KEY": "k",
            "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1/abc",
            "TELEGRAM_BOT_TOKEN": "123:abcdef",
            "TELEGRAM_CHAT_ID": "42",
        }
    )
    assert settings.enabled_outputs() == ["discord", "telegram"]
    assert settings.problems() == []


def test_explicit_outputs_require_their_variables():
    settings = Settings.from_env(
        {"YT_CHANNEL": "x", "ANTHROPIC_API_KEY": "k", "OUTPUTS": "slack, email"}
    )
    problems = settings.problems()
    assert any("SLACK_WEBHOOK_URL" in p for p in problems)
    assert any("SMTP_HOST" in p for p in problems)


def test_unknown_output_name_is_rejected():
    with pytest.raises(ConfigError):
        Settings.from_env({"OUTPUTS": "discord,fax"})


def test_partly_configured_output_produces_a_warning():
    settings = Settings.from_env({"TELEGRAM_BOT_TOKEN": "123:abcdef"})
    assert any("telegram" in w and "TELEGRAM_CHAT_ID" in w for w in settings.warnings())


def test_secret_values_skip_short_and_empty_values():
    settings = Settings.from_env(
        {"ANTHROPIC_API_KEY": "sk-ant-secret", "YOUTUBE_API_KEY": "abc", "SMTP_PASSWORD": ""}
    )
    assert settings.secret_values() == ["sk-ant-secret"]
