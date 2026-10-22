# youtube-summarizer

Get a **tiered summary of every new video from a YouTube channel, delivered to Discord, Slack, Telegram or email.**

Long videos packed with statistics are hard to skim. This bot reads the video's captions, has an
AI model pull out the specific facts, ranks them by usefulness, and sends them to your
Discord, Slack, Telegram or inbox with clickable timestamps, so you can decide in 30 seconds what deserves a closer look.

It needs **no YouTube login** and uses **your own API keys**. Nothing runs on anyone else's
server. You can run it on GitHub Actions or on your own computer.

> **Important: where it runs matters.** To read a video's captions the bot uses YouTube's
> public caption endpoint, not the official API (the official API only gives captions to the
> channel's owner). YouTube **blocks most cloud and datacenter IP addresses**, including GitHub
> Actions runners, and allows ordinary home (residential) IPs. So a hosted run on GitHub often
> fails with *"YouTube is blocking requests from your IP"* and you get a plain link instead of a
> summary. The fix is either to **run it from a home computer**
> ([Running it locally](#running-it-locally)) or to **send caption requests through a
> residential proxy** (`TRANSCRIPT_PROXY_URL`, usually a few dollars a month). Everything else
> (finding videos, summarizing, delivering) works fine from GitHub.

- [What you get](#what-you-get)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Detailed setup](#detailed-setup)
- [Configuration](#configuration)
- [Customizing what counts as Important](#customizing-what-counts-as-important)
- [Running it locally](#running-it-locally)
- [Cost](#cost)
- [Security and privacy](#security-and-privacy)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [Limitations](#limitations)
- [Setting up with an AI coding agent](#setting-up-with-an-ai-coding-agent)
- [Development](#development)

## What you get

Each new video becomes one message in each output you enable. The facts are ranked into three tiers, and every
bullet links to the moment in the video where it was said.

| Tier | What goes here |
|---|---|
| 🔴 **Important** | Specific numbers, levels, dates and explicit calls that could change a decision |
| 🟠 **Medium** | Data that supports or qualifies the important points, plus the context to read them |
| ⚪ **Low** | Background, historical comparisons, trivia, "interesting but not actionable" |

An illustrative message (all numbers are made up):

```
Weekly Market Wrap                                    <- links to the video
Presenter expects choppy trading into the Fed meeting, with support
at the 50-day average the level to watch.
38 min - Oct 21, 2026

🔴 Important - could change a decision
- Presenter sees index support at 6,850; a close below targets 6,700 (4:12)
- Fed decision Wednesday 2 p.m.; presenter expects no change but a hawkish tone (12:40)
- Breadth warning: only 38% of stocks above their 50-day average (19:05)

🟠 Medium - supporting data & context
- Small caps lagged large caps by 2.1 points this week (8:30)
- Treasury 10-year yield rose to 4.3%, the highest since July (22:15)

⚪ Low - background / FYI
- The last time volatility spiked like this was in March 2023 (27:50)

Built from auto-captions - verify key numbers in the video
```

## Requirements

| What | Needed for | Notes |
|---|---|---|
| A GitHub account | Running on GitHub's schedule | Actions installs everything on its own. Caption fetching also needs a residential proxy (see the note at the top) |
| A computer on a home connection | Alternative to the proxy | Runs the bot from a residential IP, which YouTube allows |
| Anthropic API key | Always | Paid per use, see [Cost](#cost) |
| YouTube Data API key | Recommended | Free |
| An output | Always | Discord, Slack, Telegram or email |
| Python 3.10+ and `pip` | Only for `init` or local runs | `requests` and `youtube-transcript-api` install automatically |
| [GitHub CLI (`gh`)](https://cli.github.com/) | Optional | Lets `init` upload secrets for you. Without it, `init` lists the secrets to add by hand in GitHub's web UI |

You can skip the helper: add the secrets in GitHub's web UI
([step 5](#5-add-repository-secrets)) and run the workflow. Expect the hosted caption block
described above unless you also set `TRANSCRIPT_PROXY_URL`.

## Quick start

You need a GitHub account and about 15 minutes. Details for every step are in
[Detailed setup](#detailed-setup).

1. **Copy this repository** to your own GitHub account (*Use this template* or *Fork*).
   Make your copy **private** if you can.
2. **Pick where summaries go** (Discord, Slack, Telegram or email) and create the webhook or bot.
3. **Get two API keys:** Anthropic (for the AI) and YouTube Data API (free, read-only).
4. **Find the channel's ID** (the `UC...` string).
5. **Add your secrets.** The easy way is `youtube-summarizer init` (see
   [Guided setup](#guided-setup)), which asks for each value privately, checks it, and saves it
   to GitHub for you.
6. **Enable Actions**, then run the workflow once with **test_latest** ticked to confirm it
   works. A summary of the channel's newest video should arrive in your output.

After that it checks for new videos every 3 hours on its own.

## Detailed setup

### 1. Copy the repository

On the repository page click **Use this template -> Create a new repository** (or **Fork**).
Choose **Private** unless you want your copy to be public.

> GitHub does not run scheduled workflows on forks until you enable them (step 6), and it does
> not copy secrets to forks. You always add your own.

### 2. Choose where summaries go

Enable one or several. Every fully configured output is used automatically.

**Discord.** Needs the *Manage Webhooks* permission. **Server Settings -> Integrations -> Webhooks ->
New Webhook**, pick the channel, **Copy Webhook URL**. Secret: `DISCORD_WEBHOOK_URL`.

**Slack.** Create an app at <https://api.slack.com/apps>, turn on **Incoming Webhooks**, **Add New
Webhook to Workspace**, pick a channel, copy the URL. Secret: `SLACK_WEBHOOK_URL`.

**Telegram.** Message [@BotFather](https://t.me/BotFather), send `/newbot` and copy the token.
Send your new bot any message, then open
`https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `"chat":{"id":...}`. Secrets:
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

**Email.** Any SMTP server. For Gmail turn on 2-step verification and create an
[app password](https://myaccount.google.com/apppasswords). Secrets: `SMTP_HOST`
(`smtp.gmail.com`), `SMTP_PORT` (587 for STARTTLS, 465 for SSL), `SMTP_USER`, `SMTP_PASSWORD`,
`EMAIL_TO` (comma separated) and optionally `EMAIL_FROM`.

Webhook URLs, bot tokens and passwords are secrets: anyone who has a webhook URL can post to
that channel.

### 3. Get your API keys

**Anthropic (required).** Create an account at <https://console.anthropic.com/>, add some credit,
and create a key under **API Keys**. Consider setting a monthly spend limit there. See
[Cost](#cost).

**YouTube Data API (recommended, free).** This key reads public data only; it is not a login and
never touches your YouTube account.

1. Open the [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Go to **APIs & Services -> Library**, search for **YouTube Data API v3** and click **Enable**.
3. Go to **APIs & Services -> Credentials -> Create credentials -> API key**.
4. Optional but wise: click the key and restrict it to **YouTube Data API v3**.

Each run uses only a handful of the 10,000 free daily quota units. Without this key the bot falls
back to YouTube's RSS feed, which is unreliable (see [Limitations](#limitations)).

### 4. Find the channel ID

The channel ID is a 24-character string starting with `UC`.

- On the channel page open **About**, then **Share channel -> Copy channel ID**.
- Or, if you set `YOUTUBE_API_KEY`, you can use the `@handle` (for example `@somechannel`)
  as `YT_CHANNEL` and the bot will look the ID up for you.

### 5. Add repository secrets

#### Guided setup

The helper validates each key without posting anything, then saves them as GitHub secrets
(using the optional [GitHub CLI](https://cli.github.com/); run `gh auth login` first) and/or a local `.env`:

```bash
pip install .
youtube-summarizer init
```

Values are typed with hidden input and never echoed. If you already have them in your
environment or `.env`, `youtube-summarizer init --from-env` pushes them to GitHub with no
prompts. Without `gh` the helper lists the secret names to add by hand in GitHub's web UI and saves a `.env` instead. Useful flags: `--repo owner/name`, `--no-validate`, `--env-file PATH`.

#### Manual setup

In your repository go to **Settings -> Secrets and variables -> Actions -> New repository secret**
and add:

| Secret | Required | Value |
|---|---|---|
| `YT_CHANNEL` | yes | The `UC...` channel ID (or `@handle` with `YOUTUBE_API_KEY`) |
| `ANTHROPIC_API_KEY` | yes | Your Anthropic key |
| An output | yes, at least one | `DISCORD_WEBHOOK_URL`, `SLACK_WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, or `SMTP_HOST` + `SMTP_USER` + `SMTP_PASSWORD` + `EMAIL_TO` (see step 2) |
| `YOUTUBE_API_KEY` | recommended | The key from step 3 |
| `ANTHROPIC_MODEL` | no | Defaults to `claude-sonnet-5-5`; `claude-haiku-5-5` is cheaper |
| `USER_CONTEXT` | no | Who the summary is for. See [Customizing](#customizing-what-counts-as-important) |
| `TRANSCRIPT_PROXY_URL` | no | Only if YouTube blocks caption downloads. See [Troubleshooting](#troubleshooting) |

With the [GitHub CLI](https://cli.github.com/) you can set a secret without it appearing in your
shell history; it prompts for the value:

```bash
gh secret set ANTHROPIC_API_KEY
```

### 6. Enable Actions and test

1. Open the **Actions** tab and enable workflows if GitHub asks.
2. Choose **Summarize new videos** in the left sidebar -> **Run workflow**.
3. Tick **test_latest** and run it. Within a minute the newest video's summary should arrive in
   your output. This also proves that every secret is correct.

The first scheduled run only records the channel's existing videos and posts nothing, so you are
not flooded with old content. From the next upload onward you get a summary.

## Configuration

Everything is configured with environment variables. As GitHub secrets they go in the workflow;
locally they go in a `.env` file (copy [`.env.example`](.env.example)).

| Variable | Default | Purpose |
|---|---|---|
| `YT_CHANNEL` | | Channel ID, `@handle` or channel URL |
| `YOUTUBE_API_KEY` | | YouTube Data API key (recommended) |
| `ANTHROPIC_API_KEY` | | Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | Model used for summaries |
| `OUTPUTS` | auto | Comma list of `discord`, `slack`, `telegram`, `email`. Empty = every fully configured output |
| `DISCORD_WEBHOOK_URL` | | Discord webhook |
| `SLACK_WEBHOOK_URL` | | Slack incoming webhook |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | | Telegram bot and destination chat |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | port `587` | SMTP server for email |
| `EMAIL_FROM`, `EMAIL_TO` | from = user | Sender, and comma-separated recipients |
| `USER_CONTEXT` | generic reader | Who the summary is written for; steers the tiers |
| `TRANSCRIPT_PROXY_URL` | | Proxy URL for caption downloads |
| `MAX_VIDEOS_PER_RUN` | `3` | Cap on summaries per run, oldest first |
| `MIN_DURATION_SEC` | `600` | Videos shorter than this (Shorts, clips) are skipped |
| `MAX_TRANSCRIPT_ATTEMPTS` | `4` | Runs to wait for captions before posting a plain link |
| `STATE_FILE` | `state/seen_videos.json` | Where the list of handled videos is stored |

Empty values count as unset, so an unset GitHub secret falls back to the default. If one output
fails (say Slack is down) the others still deliver, and the run is marked failed so you notice.

To change **how often** it checks, edit the `cron` line in `.github/workflows/summarize.yml`
(default `17 */3 * * *`, every 3 hours in UTC). Checking more often does not cost more, because
the AI is only called when there is a new video.

## Customizing what counts as Important

What is "important" depends on who is reading. Describe the reader in `USER_CONTEXT`:

```
an active swing trader who wants price levels, dates and explicit calls
```

```
a software engineer who wants concrete benchmarks, version numbers and breaking changes
```

```
a student who wants definitions, formulas and worked examples
```

For deeper changes edit `PROMPT_TEMPLATE` in `src/youtube_summarizer/summarizer.py`. It defines
the tiers, the rules (exact figures, no invented numbers, skip sponsor reads) and how many bullets
each tier gets.

## Running it locally

Running at home is the free way around YouTube's block on cloud IPs, because a home connection
looks like an ordinary viewer. Requires Python 3.10 or newer.

**1. Install, from the project folder** (the folder that contains `pyproject.toml`):

```bash
# macOS / Linux
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

```powershell
# Windows (PowerShell)
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

Use `pip install -e .` (editable), not `pip install .`: the editable install always runs the code
in this folder, so updates you pull take effect immediately. After `git pull`, a plain install
would keep running the old copy.

**2. Create your `.env`.** Either run `youtube-summarizer init` and answer **yes** to *Also write
.env*, or copy the template and fill it in:

```bash
cp .env.example .env            # macOS / Linux
Copy-Item .env.example .env     # Windows (PowerShell)
```

The bot reads `.env` from the **folder you run it in**, so run the commands below from the
project folder. Real environment variables take priority over `.env`, and empty values count as
unset. No extra package is needed to load it.

**3. Run:**

```bash
python -m youtube_summarizer --test-latest --dry-run   # print what would be sent, post nothing
python -m youtube_summarizer --test-latest             # post the newest video's summary now
python -m youtube_summarizer                           # normal run (skips already-handled videos)
```

If you see `YT_CHANNEL is not set` while your `.env` exists, you are either in the wrong folder
(the error message prints the folder it looked in) or running an old installed copy: re-run
`pip install -e .` and check that
`python -c "import youtube_summarizer.config as c; print(c.__file__)"` prints a path inside this
project, not `site-packages`.

`--dry-run` still calls the AI (and costs a little) but sends nothing and saves no state.

**Running automatically.** The scheduled GitHub workflow cannot fetch captions without a
proxy, so to automate at home run the last command on a timer and keep
`state/seen_videos.json` between runs:

- **Windows:** Task Scheduler, a daily or hourly trigger, action *Start a program*:
  program `C:\path\to\project\.venv\Scripts\python.exe`, arguments
  `-m youtube_summarizer`, **Start in** the project folder (needed so `.env` is found).
- **macOS / Linux:** `crontab -e`, for example
  `17 */3 * * * cd /path/to/project && .venv/bin/python -m youtube_summarizer`.

The computer must be awake and online at those times. If you run locally, disable the GitHub
schedule (Actions tab > the workflow > **...** > **Disable workflow**) so two copies don't
both post.

## Cost

- **GitHub Actions:** free for this workload; a run takes about a minute.
- **YouTube Data API:** free; a run uses a few of the 10,000 daily units.
- **Discord, Slack, Telegram:** free. **Email:** whatever your mail provider charges (usually free).
- **Anthropic:** the only real cost, and only when a video is actually summarized. A 40-minute
  video is roughly 10,000 tokens in and about 1,000 tokens out. Multiply by your chosen model's
  per-token price on Anthropic's pricing page. `claude-haiku-5-5` is the cheaper option.

Set a monthly spend limit in the Anthropic console if you want a hard ceiling.

## Security and privacy

- **Never commit secrets.** `.env` is git-ignored. On GitHub, keys live in encrypted repository
  secrets and are not shown in logs.
- **Webhook URLs, bot tokens and SMTP passwords are secrets.** If one leaks, revoke it
  (delete the webhook, regenerate the token, change the password) and update the secret. Logs
  scrub known secret values automatically.
- **What leaves your machine:** the video's captions go to Anthropic to be summarized. Summaries go
  to the outputs you enabled. YouTube sees public API and caption requests. Nothing is sent anywhere
  else.
- **State is stored in your repository.** `state/seen_videos.json` contains only video IDs. If your
  repository is public, so is that file; it contains nothing sensitive.
- **Be a good citizen.** Summaries are for your own use. Respect YouTube's Terms of Service and the
  creators' rights, and don't republish their content.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Nothing posted after setup | Expected: the first run only records existing videos. Run the workflow with **test_latest** to confirm it works. |
| Workflow never runs on schedule | Actions are disabled on new forks and copies: enable them in the **Actions** tab. GitHub may also pause scheduled workflows in repositories with no recent activity; re-enable from the Actions tab. |
| `YT_CHANNEL is not set` (or another `... is not set`) | The secret is missing or misspelled. Names are case-sensitive. |
| `Could not resolve a channel ID` | Use the `UC...` channel ID, or add `YOUTUBE_API_KEY` if you used a `@handle`. |
| Log says *RSS feed unavailable* (404 or 500) | YouTube's RSS endpoint is unreliable. Set `YOUTUBE_API_KEY` so the bot uses the Data API. |
| Log says *YouTube is blocking requests from your IP* (`RequestBlocked` / `IpBlocked`) | YouTube blocks GitHub's servers. Set `TRANSCRIPT_PROXY_URL` to a residential proxy, or [run it locally](#running-it-locally) from a home connection. |
| Local run says `YT_CHANNEL is not set` but `.env` exists | Run from the folder containing `.env`, and use `pip install -e .`. See [Running it locally](#running-it-locally). |
| `captions not available` appears repeatedly | Captions may not be generated yet (common right after upload; the bot retries on later runs), may be disabled by the creator, or YouTube may be blocking GitHub's servers. If videos you know have captions keep failing, set `TRANSCRIPT_PROXY_URL` or run locally. |
| Plain link instead of a summary | After `MAX_TRANSCRIPT_ATTEMPTS` runs without usable captions, the bot posts the link so you don't miss the video. |
| `Anthropic API 401` | The API key is wrong or revoked. |
| `Anthropic API 404` or model error | `ANTHROPIC_MODEL` is not a valid model name; delete the secret to use the default. |
| `Anthropic API 429` or credit errors | Rate limit or no credit left. Check billing in the Anthropic console. |
| `Discord 404` or `401`, or a similar error from Slack | The webhook was deleted or the URL is wrong. Create a new one and update the secret. |
| Telegram `chat not found` | Send your bot a message first, and check the chat ID. |
| Email login fails | Use an app password, and check the port: 587 (STARTTLS) or 465 (SSL). |
| `partly configured and will be ignored` | An output has only some of its variables. Add the missing ones. |
| Same video posted twice | The state commit failed. Check the **Commit updated state** step. If it was rejected, go to **Settings -> Actions -> General -> Workflow permissions** and allow read and write access. |
| Shorts or clips are skipped | By design: videos under `MIN_DURATION_SEC` (default 10 minutes) are ignored. Lower the value to include them. |

Run locally with `-v` for debug logging.

## FAQ

**Does it need my YouTube account?** No. It only reads public data, with an API key or the public
RSS feed.

**Can it watch several channels?** Not yet: one copy watches one channel. For several channels,
make one copy per channel, each with its own secrets.

**Can I use a different AI provider?** Not currently; it calls the Anthropic API. The provider
code is isolated in `summarizer.py`, so adding another is a contained change. Contributions are
welcome.

**Other languages?** Captions are requested in English only (`en`, `en-US`, `en-GB`).

**Can I add another output (Teams, Matrix, ...)?** Each output is one small class in
`src/youtube_summarizer/notifiers/`. [`AGENTS.md`](AGENTS.md) lists the steps; contributions are
welcome.

**Why does it say "verify key numbers"?** Auto-captions mis-hear numbers and names. Treat the
summary as a triage tool and confirm anything you will act on in the video itself. Summaries are
machine-generated and can be wrong; nothing here is professional advice.

## Limitations

- Hosted runs (GitHub Actions) normally cannot fetch captions without a residential proxy,
  because YouTube blocks cloud IP ranges. Home computers work.
- Captions come from YouTube's auto-captions: English only, and numbers can be mis-heard.
- The RSS fallback cannot tell Shorts or live streams apart, so those filters only apply when
  `YOUTUBE_API_KEY` is set.
- Live streams and premieres are skipped until they finish.
- Scheduled GitHub Actions runs can start several minutes late.
- One channel per copy.

## Setting up with an AI coding agent

Open the repository in an AI coding agent (such as Claude Code, Codex or Cursor) and ask it to
set the project up. [`AGENTS.md`](AGENTS.md) tells the agent what it can automate (installing,
testing, creating the repository) and what only you can do (creating the keys). It also forbids
the agent from asking you to paste keys into the chat; you run `youtube-summarizer init`
yourself, which prompts you privately.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

The test suite needs no network and no API keys. `pipeline.process_video` accepts its fetch and
summarize steps as optional arguments and delivers through a small sink, so tests replace them.

```
src/youtube_summarizer/
|-- cli.py              command-line entry point
|-- config.py           Settings, read from environment variables
|-- models.py           Video, Point, Summary data classes
|-- youtube.py          find new uploads (Data API, RSS fallback)
|-- transcript.py       fetch captions, build timestamped text
|-- summarizer.py       prompt, Claude client, response parsing
|-- notifiers/          one module per output (discord, slack, telegram, email_smtp)
|   `-- base.py         Notifier interface and Dispatcher
|-- setup_wizard.py     `init` helper: validate keys, save to GitHub / .env
|-- logging_utils.py    log formatting that redacts secrets
|-- state.py            seen-videos persistence
|-- pipeline.py         ties it together
`-- formatting.py       small pure helpers
tests/                  pytest suite
.github/workflows/      ci.yml (lint + tests), summarize.yml (the scheduled bot)
```

Issues and pull requests are welcome. Please run `ruff check .` and `pytest` before opening one.

## License

[MIT](LICENSE)
