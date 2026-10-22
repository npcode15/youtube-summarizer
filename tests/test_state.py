import json

from youtube_summarizer.state import MAX_SEEN, State, StateStore


def test_missing_file_gives_fresh_state(tmp_path):
    state = StateStore(tmp_path / "state.json").load()
    assert state == State()
    assert not state.initialized


def test_roundtrip_creates_parent_directories(tmp_path):
    store = StateStore(tmp_path / "nested" / "state.json")
    original = State(initialized=True, seen=["a", "b"], pending={"c": 2})
    store.save(original)
    assert store.load() == original


def test_legacy_list_format_is_migrated(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(["a", "b"]))
    assert StateStore(path).load() == State(initialized=True, seen=["a", "b"])


def test_corrupt_file_falls_back_to_fresh_state(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    assert StateStore(path).load() == State()


def test_seen_list_is_capped_keeping_the_newest(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.save(State(initialized=True, seen=[str(i) for i in range(MAX_SEEN + 10)]))
    loaded = store.load()
    assert len(loaded.seen) == MAX_SEEN
    assert loaded.seen[-1] == str(MAX_SEEN + 9)


def test_mark_seen_clears_pending():
    state = State(pending={"a": 2})
    state.mark_seen("a")
    state.mark_seen("a")
    assert state.seen == ["a"]
    assert state.pending == {}
