"""Tests de `separation/progress.py`."""

from __future__ import annotations

from guitarriff.separation.progress import ProgressStore, Stage


def test_start_then_get_shows_queued() -> None:
    store = ProgressStore()
    store.start("file1", "htdemucs")

    entry = store.get("file1", "htdemucs")

    assert entry is not None
    assert entry.stage == Stage.QUEUED
    assert entry.progress_percent == 0


def test_set_stage_updates_progress_and_keeps_started_at() -> None:
    store = ProgressStore()
    store.start("file1", "htdemucs")
    first_started_at = store.get("file1", "htdemucs").started_at

    store.set_stage("file1", "htdemucs", Stage.SEPARATING)
    entry = store.get("file1", "htdemucs")

    assert entry.stage == Stage.SEPARATING
    assert entry.progress_percent == 50
    assert entry.started_at == first_started_at


def test_set_done_records_stems() -> None:
    store = ProgressStore()
    store.start("file1", "htdemucs")

    store.set_done("file1", "htdemucs", ["drums", "bass"])
    entry = store.get("file1", "htdemucs")

    assert entry.stage == Stage.DONE
    assert entry.progress_percent == 100
    assert entry.stems == ["drums", "bass"]


def test_set_error_records_message() -> None:
    store = ProgressStore()
    store.start("file1", "htdemucs")

    store.set_error("file1", "htdemucs", "panne simulée")
    entry = store.get("file1", "htdemucs")

    assert entry.stage == Stage.ERROR
    assert entry.error_message == "panne simulée"


def test_is_running_true_while_in_progress_false_once_done() -> None:
    store = ProgressStore()
    store.start("file1", "htdemucs")
    assert store.is_running("file1", "htdemucs") is True

    store.set_done("file1", "htdemucs", [])
    assert store.is_running("file1", "htdemucs") is False


def test_is_running_false_for_unknown_entry() -> None:
    store = ProgressStore()
    assert store.is_running("unknown", "htdemucs") is False


def test_entries_are_isolated_per_file_and_mode() -> None:
    store = ProgressStore()
    store.start("file1", "htdemucs")
    store.start("file1", "htdemucs_6s")
    store.start("file2", "htdemucs")

    store.set_done("file1", "htdemucs", ["bass"])

    assert store.get("file1", "htdemucs").stage == Stage.DONE
    assert store.get("file1", "htdemucs_6s").stage == Stage.QUEUED
    assert store.get("file2", "htdemucs").stage == Stage.QUEUED
