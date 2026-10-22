"""Persistent record of which videos have already been handled."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

MAX_SEEN = 500


@dataclass
class State:
    """What the bot remembers between runs."""

    initialized: bool = False
    seen: list[str] = field(default_factory=list)
    pending: dict[str, int] = field(default_factory=dict)  # video id -> failed attempts

    def mark_seen(self, video_id: str) -> None:
        if video_id not in self.seen:
            self.seen.append(video_id)
        self.pending.pop(video_id, None)


class StateStore:
    """Reads and writes :class:`State` as a small JSON file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> State:
        """Load state; a missing or unreadable file yields a fresh, uninitialized state."""
        if not self.path.exists():
            return State()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return State()
        if isinstance(data, list):  # legacy format: a bare list of video IDs
            return State(initialized=True, seen=[str(v) for v in data])
        if not isinstance(data, dict):
            return State()
        return State(
            initialized=bool(data.get("initialized", False)),
            seen=[str(v) for v in data.get("seen", [])],
            pending={str(k): int(v) for k, v in dict(data.get("pending", {})).items()},
        )

    def save(self, state: State) -> None:
        """Write state atomically, keeping only the most recent ``MAX_SEEN`` IDs."""
        state.seen = state.seen[-MAX_SEEN:]
        payload = {
            "initialized": state.initialized,
            "seen": state.seen,
            "pending": state.pending,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
