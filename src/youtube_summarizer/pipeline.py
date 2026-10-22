"""Orchestration: find new videos, summarize them, notify, track state."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from functools import partial

from .config import Settings
from .models import Summary, Video
from .notifiers import DiscordNotifier, Dispatcher, Sink, build_notifiers
from .state import State, StateStore
from .summarizer import ClaudeClient, summarize
from .transcript import Segment, fetch_segments, to_timestamped_text
from .youtube import fetch_recent_videos, resolve_channel_id

log = logging.getLogger(__name__)

FetchFn = Callable[[str], list[Segment] | None]
SummarizeFn = Callable[[Video, str], Summary]


def _summarize_with_claude(video: Video, transcript_text: str, *, settings: Settings) -> Summary:
    client = ClaudeClient(settings.anthropic_api_key, settings.anthropic_model)
    return summarize(video, transcript_text, client.complete, settings.reader_context)


def _default_dispatcher(settings: Settings, dry_run: bool) -> Dispatcher:
    notifiers = build_notifiers(settings)
    if not notifiers and dry_run:
        notifiers = [DiscordNotifier("")]  # nothing configured: preview using Discord's layout
    return Dispatcher(notifiers, dry_run=dry_run)


def select_new_videos(
    videos: Sequence[Video], state: State, min_duration_sec: int
) -> list[Video]:
    """Return unseen, finished, full-length videos, oldest first.

    Clips shorter than ``min_duration_sec`` are marked as seen on ``state`` so they
    are not reconsidered. Live streams and premieres are skipped but left unseen,
    so they are picked up once they finish.
    """
    todo = []
    for video in sorted(videos, key=lambda v: v.published):
        if video.id in state.seen:
            continue
        if video.live not in (None, "none"):
            log.info("Skipping %s (live or premiere not finished): %s", video.id, video.title)
            continue
        if video.duration_sec is not None and video.duration_sec < min_duration_sec:
            log.info("Skipping short video %s (%ds): %s", video.id, video.duration_sec, video.title)
            state.mark_seen(video.id)
            continue
        todo.append(video)
    return todo


def process_video(
    video: Video,
    state: State,
    settings: Settings,
    sink: Sink,
    *,
    fetch: FetchFn | None = None,
    summarize_fn: SummarizeFn | None = None,
) -> bool:
    """Summarize one video and hand the result to ``sink`` (the dispatcher).

    Returns ``True`` when the video is finished and should be marked as seen, and
    ``False`` when it should be retried on a later run (captions not published
    yet, or a model error). After ``settings.max_attempts`` failed attempts a short
    notice with the video link is sent instead, and the video counts as finished.

    The ``fetch`` and ``summarize_fn`` hooks exist for testing.
    """
    fetch = fetch or partial(fetch_segments, proxy_url=settings.transcript_proxy_url)
    summarize_fn = summarize_fn or partial(_summarize_with_claude, settings=settings)

    summary: Summary | None = None
    reason = ""
    segments = fetch(video.id)
    if not segments:
        reason = "captions not available"
    else:
        try:
            summary = summarize_fn(video, to_timestamped_text(segments))
        except Exception as exc:  # any model or network failure becomes a retry
            log.exception("Summarization failed for %s", video.id)
            reason = f"summary failed: {str(exc)[:120]}"

    if summary is not None:
        sink.summary(video, summary)
        state.pending.pop(video.id, None)
        return True

    attempts = state.pending.get(video.id, 0) + 1
    if attempts < settings.max_attempts:
        state.pending[video.id] = attempts
        log.info(
            "%s: %s; will retry next run (%d/%d)", video.id, reason, attempts, settings.max_attempts
        )
        return False
    sink.notice(video, reason)
    state.pending.pop(video.id, None)
    return True


def run(
    settings: Settings,
    *,
    test_latest: bool = False,
    dry_run: bool = False,
    store: StateStore | None = None,
    dispatcher: Dispatcher | None = None,
) -> int:
    """Run one polling cycle and return a process exit code.

    The exit code is 1 when any output failed, so scheduled runs surface problems.
    """
    store = store or StateStore(settings.state_file)
    dispatcher = dispatcher or _default_dispatcher(settings, dry_run)
    channel_id = resolve_channel_id(settings.channel, settings.youtube_api_key)
    videos = fetch_recent_videos(channel_id, settings.youtube_api_key)
    if not videos:
        log.info("No videos found.")
        return 0
    log.info("Channel %s: %d recent videos, newest: %s", channel_id, len(videos), videos[0].title)

    if test_latest:
        # Ignore saved state; force a result (a notice) even if captions are missing.
        scratch = State(pending={videos[0].id: settings.max_attempts - 1})
        process_video(videos[0], scratch, settings, dispatcher)
        return 1 if dispatcher.failures else 0

    state = store.load()
    if not state.initialized:
        state.seen = [video.id for video in videos]
        state.initialized = True
        if not dry_run:
            store.save(state)
        log.info("First run: recorded %d existing videos, nothing posted.", len(videos))
        return 0

    todo = select_new_videos(videos, state, settings.min_duration_sec)
    if not todo:
        log.info("No new videos.")
    for video in todo[: settings.max_videos_per_run]:
        log.info("New video: %s (%s)", video.title, video.id)
        try:
            if process_video(video, state, settings, dispatcher):
                state.mark_seen(video.id)
        except Exception:  # e.g. every output is down: leave it unseen and retry next run
            log.exception("Delivery failed for %s; will retry next run", video.id)
            dispatcher.failures.append("all outputs")
        if not dry_run:
            store.save(state)
    if not dry_run:
        store.save(state)  # also persists clips skipped by select_new_videos
    return 1 if dispatcher.failures else 0
