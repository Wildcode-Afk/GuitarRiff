"""Tests de `separation/service.py` — cache, mémoire, durée, concurrence,
progression. Le moteur Demucs (`engine.run_separation`) est simulé ; les
fichiers audio sont réels (générés par FFmpeg)."""

from __future__ import annotations

import subprocess
import threading
import time as time_module
from pathlib import Path
from unittest.mock import patch

import pytest

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.config import Settings
from guitarriff.errors import AudioTooLongError, InsufficientMemoryError, SeparationInProgressError
from guitarriff.separation import service
from guitarriff.separation.progress import Stage, progress_store


@pytest.fixture(autouse=True)
def _clear_progress_store():
    progress_store._entries.clear()
    yield
    progress_store._entries.clear()


def _generate_test_wav(path: Path, *, duration: float = 1.0) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path)


@pytest.fixture
def storage(settings: Settings) -> AudioFileStorage:
    return AudioFileStorage(settings)


def _upload(storage: AudioFileStorage, tmp_path: Path, *, duration: float = 1.0) -> str:
    source = tmp_path / "gen.wav"
    _generate_test_wav(source, duration=duration)
    record = storage.save(
        filename="chanson.wav", declared_content_type="audio/wav", content=source.read_bytes()
    )
    return record.file_id


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    deadline = time_module.time() + timeout
    while time_module.time() < deadline:
        if predicate():
            return True
        time_module.sleep(interval)
    return predicate()


def test_mode_none_completes_immediately_without_engine(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload(storage, tmp_path)

    with patch.object(service, "run_separation") as mock_engine:
        status = service.start_separation(file_id, "none", settings, storage)

    assert status.stage == "done"
    assert status.stems == ["mixture"]
    mock_engine.assert_not_called()


def test_start_separation_runs_engine_and_reaches_done(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload(storage, tmp_path)

    def fake_run_separation(
        source_path, output_dir, model_info, *, allow_model_download, on_stage=None
    ):
        if on_stage:
            on_stage(Stage.LOADING_MODEL)
            on_stage(Stage.SEPARATING)
            on_stage(Stage.WRITING_STEMS)
        output_dir.mkdir(parents=True, exist_ok=True)
        for stem in model_info.stems:
            (output_dir / f"{stem}.wav").write_bytes(b"RIFF....WAVEfmt ")
        return list(model_info.stems)

    with patch.object(service, "run_separation", side_effect=fake_run_separation):
        initial = service.start_separation(file_id, "htdemucs", settings, storage)
        assert initial.stage in ("queued", "loading_model", "separating", "writing_stems", "done")

        done = _wait_until(
            lambda: service.get_status(file_id, "htdemucs", settings, storage).stage == "done"
        )
        assert done

    final_status = service.get_status(file_id, "htdemucs", settings, storage)
    assert final_status.stems == ["drums", "bass", "other", "vocals"]
    assert "guitare" in final_status.notes.lower()

    # Les métadonnées persistées doivent refléter le mode calculé.
    record = storage.get(file_id)
    assert "htdemucs" in record.separated_modes


def test_cache_prevents_rerunning_engine(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload(storage, tmp_path)

    def fake_run_separation(
        source_path, output_dir, model_info, *, allow_model_download, on_stage=None
    ):
        output_dir.mkdir(parents=True, exist_ok=True)
        for stem in model_info.stems:
            (output_dir / f"{stem}.wav").write_bytes(b"fake")
        return list(model_info.stems)

    with patch.object(service, "run_separation", side_effect=fake_run_separation) as mock_engine:
        service.start_separation(file_id, "htdemucs", settings, storage)
        _wait_until(
            lambda: service.get_status(file_id, "htdemucs", settings, storage).stage == "done"
        )
        assert mock_engine.call_count == 1

        # Deuxième appel : doit être servi depuis le cache, sans relancer le moteur.
        second = service.start_separation(file_id, "htdemucs", settings, storage)
        assert second.stage == "done"
        assert mock_engine.call_count == 1


def test_concurrent_start_raises_in_progress(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload(storage, tmp_path)
    release_event = threading.Event()
    started_event = threading.Event()

    def blocking_run_separation(
        source_path, output_dir, model_info, *, allow_model_download, on_stage=None
    ):
        started_event.set()
        release_event.wait(timeout=5)
        output_dir.mkdir(parents=True, exist_ok=True)
        for stem in model_info.stems:
            (output_dir / f"{stem}.wav").write_bytes(b"fake")
        return list(model_info.stems)

    with patch.object(service, "run_separation", side_effect=blocking_run_separation):
        service.start_separation(file_id, "htdemucs", settings, storage)
        assert started_event.wait(timeout=5)

        with pytest.raises(SeparationInProgressError):
            service.start_separation(file_id, "htdemucs", settings, storage)

        release_event.set()
        _wait_until(
            lambda: service.get_status(file_id, "htdemucs", settings, storage).stage == "done"
        )


def test_insufficient_memory_blocks_before_engine_call(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload(storage, tmp_path)
    low_memory_settings = Settings(
        _env_file=None, data_dir=settings.data_dir, separation_min_available_memory_mb=10_000_000
    )

    with patch.object(service, "run_separation") as mock_engine:
        with pytest.raises(InsufficientMemoryError):
            service.start_separation(file_id, "htdemucs", low_memory_settings, storage)

    mock_engine.assert_not_called()


def test_audio_too_long_blocks_before_engine_call(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    short_settings = Settings(
        _env_file=None, data_dir=settings.data_dir, audio_max_duration_seconds=1
    )
    file_id = _upload(storage, tmp_path, duration=3.0)

    with patch.object(service, "run_separation") as mock_engine:
        with pytest.raises(AudioTooLongError):
            service.start_separation(file_id, "htdemucs", short_settings, storage)

    mock_engine.assert_not_called()


def test_engine_failure_sets_error_status_and_no_cache(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload(storage, tmp_path)

    def failing_run_separation(*args, **kwargs):
        raise RuntimeError("panne interne imprévue")

    with patch.object(service, "run_separation", side_effect=failing_run_separation):
        service.start_separation(file_id, "htdemucs", settings, storage)
        errored = _wait_until(
            lambda: service.get_status(file_id, "htdemucs", settings, storage).stage == "error"
        )

    assert errored
    status = service.get_status(file_id, "htdemucs", settings, storage)
    # Le message generique ne doit pas exposer le détail interne brut.
    assert "panne interne imprévue" not in (status.error or "")

    # Aucun cache ne doit avoir été écrit après un échec.
    assert not storage.separated_dir(file_id, "htdemucs").joinpath("meta.json").exists()


def test_get_status_not_started_for_unknown_mode_attempt(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload(storage, tmp_path)

    status = service.get_status(file_id, "htdemucs", settings, storage)

    assert status.stage == "not_started"


def test_get_status_reports_timeout_without_waiting_real_time(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload(storage, tmp_path)
    fast_timeout_settings = Settings(
        _env_file=None, data_dir=settings.data_dir, separation_timeout_seconds=1
    )

    progress_store.start(file_id, "htdemucs")
    # Simule un démarrage il y a longtemps, sans attendre pour de vrai.
    entry = progress_store.get(file_id, "htdemucs")
    entry.started_at = time_module.time() - 9999

    status = service.get_status(file_id, "htdemucs", fast_timeout_settings, storage)

    assert status.stage == "error"
    assert "délai" in (status.error or "").lower()
