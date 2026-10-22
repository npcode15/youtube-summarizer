# Instructions for AI coding agents

This repository is a small Python bot: it watches one YouTube channel and posts tiered AI
summaries of new videos to Discord, Slack, Telegram and/or email, on a GitHub Actions schedule. The README is the
user-facing documentation; this file tells you how to help someone set it up or change it.

## Hard rules about secrets

- **Never ask the user to paste an API key, webhook URL or token into the chat.** Never print,
  echo, log or commit one.
- Never create or edit a committed file containing a real secret. `.env` is git-ignored and is
  for local runs only.
- **Never read `.env`** or print environment variables.
- To put secrets on GitHub, have the user run `youtube-summarizer init` in their own terminal
  (hidden prompts, keys are validated and saved with `gh secret set`). If they already have the
  values in `.env` or their environment, `youtube-summarizer init --from-env` pushes them without
  you seeing them. Plain `gh secret set NAME` also prompts privately.
- Do not fetch or visit URLs that contain a secret.

## Helping a user set the project up

Do these yourself where you can, and tell the user plainly which steps are theirs.

**You can do:**
1. Check prerequisites: Python 3.10+, `git`, and the GitHub CLI (`gh --version`, `gh auth status`).
2. Create a virtualenv and install: `pip install -e ".[dev,local]"`.
3. Run the tests: `pytest` and `ruff check .`.
4. Create their own repository from this code (`gh repo create --private --source . --push`) after
   asking them which account or organization to use.
5. Ask the user to run `youtube-summarizer init` themselves (it needs their keys), or
   `youtube-summarizer init --from-env` if the values are already in their environment.
6. Trigger and watch the test run: `gh workflow run "Summarize new videos" -f test_latest=true`,
   then `gh run watch`.

**Only the user can do** (guide them with the README's *Detailed setup*):
- Create the Anthropic key, the YouTube Data API key and a webhook/bot for the output they pick.
- Decide which channel to watch and find its `UC...` channel ID.

Confirm success by checking that a summary of the channel's newest video arrived in their output.
If it did not, use the README's Troubleshooting table and the run logs
(`gh run view --log-failed`).

## Working on the code

- Layout: `src/youtube_summarizer/` (one module per job, see README), tests in `tests/`.
- Configuration is read once, in `config.Settings.from_env`. Do not read `os.environ` elsewhere.
- Style: type hints, short docstrings, `ruff` with the rules in `pyproject.toml`
  (line length 100). Keep modules small and single-purpose.
- Tests must not use the network or real keys. `pipeline.process_video` takes `fetch` and
  `summarize_fn` hooks and a sink (the `Dispatcher`) for this; follow that pattern. The setup
  wizard takes injectable console, runner and `which` for the same reason.
- Each output is a `Notifier` in `notifiers/` (render, preview, post). To add one: write the
  subclass, add its config dataclass in `config.py`, register it in `notifiers/__init__.py`,
  `OUTPUT_FIELDS` in `setup_wizard.py`, the workflow env block and the README table.
- Platform limits live in each notifier (Discord 10 embeds / 6000 chars, Slack 3000-char blocks,
  Telegram 4096-char messages). Keep their tests passing when you change rendering.
- The ranking behaviour lives in `PROMPT_TEMPLATE` in `summarizer.py`. Changes there should keep
  the JSON output shape that `parse_summary` expects.
- Before finishing a change: `ruff check .` and `pytest`.

## Do not

- Add features that send transcripts or user data anywhere except the configured model provider
  and the outputs the user configured.
- Commit `.env`, API keys, webhook URLs or personal channel IDs into examples.
- Remove the "verify key numbers" footer: auto-captions mis-hear numbers.
