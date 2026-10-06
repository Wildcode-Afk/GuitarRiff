"""Tests de `rhythm/service.py` — distinction détecté/manuel, persistance du
Song, bootstrap sans transcription préalable."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.audio.service import normalize_stored_audio
from guitarriff.config import Settings
from guitarriff.errors import AudioNotNormalizedError
from guitarriff.model import EstimationSource
from guitarriff.rhythm import service

_SAMPLE_RATE = 22050


def _generate_click_wav(path: Path, *, bpm: float = 120.0, duration: float = 8.0) -> None:
    period = 60.0 / bpm
    sr = _SAMPLE_RATE
    n_clicks = int(duration / period)
    click = np.zeros(int(sr * period), dtype="float32")
    click_len = int(sr * 0.02)
    click[:click_len] = 0.8 * np.sin(2 * np.pi * 1000 * np.arange(click_len) / sr).astype("float32")
    track = np.tile(click, n_clicks)
    sf.write(str(path), track, sr)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path)


@pytest.fixture
def storage(settings: Settings) -> AudioFileStorage:
    return AudioFileStorage(settings)


def _upload_and_normalize(
    storage: AudioFileStorage, settings: Settings, tmp_path: Path, **kwargs: object
) -> str:
    source = tmp_path / "gen.wav"
    _generate_click_wav(source, **kwargs)  # type: ignore[arg-type]
    record = storage.save(
        filename="chanson.wav", declared_content_type="audio/wav", content=source.read_bytes()
    )
    normalize_stored_audio(record.file_id, settings, storage)
    return record.file_id


def test_analyze_requires_prior_normalization(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    source = tmp_path / "gen.wav"
    _generate_click_wav(source)
    record = storage.save(
        filename="chanson.wav", declared_content_type="audio/wav", content=source.read_bytes()
    )

    with pytest.raises(AudioNotNormalizedError):
        service.analyze(record.file_id, settings, storage)


def test_analyze_creates_song_with_detected_tempo(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_and_normalize(storage, settings, tmp_path, bpm=120.0, duration=8.0)

    outcome = service.analyze(file_id, settings, storage)

    tempo_change = outcome.song.tempo_changes[0]
    assert tempo_change.source == EstimationSource.DETECTED
    assert tempo_change.confidence is not None
    assert tempo_change.time_seconds == 0.0
    assert len(outcome.beat_times) > 0

    # Persisté.
    persisted = storage.read_song(file_id)
    assert persisted == outcome.song


def test_analyze_applies_default_unconfirmed_time_signature(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_and_normalize(storage, settings, tmp_path)

    outcome = service.analyze(file_id, settings, storage)

    signature = outcome.song.time_signature_changes[0]
    assert (signature.numerator, signature.denominator) == (4, 4)
    assert signature.source == EstimationSource.DETECTED
    # Jamais de confiance sur une métrique par défaut non analysée : ce
    # n'est pas une déduction, juste une convention assumée.
    assert signature.confidence is None


def test_set_manual_tempo_overrides_and_is_tagged_manual(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_and_normalize(storage, settings, tmp_path)
    service.analyze(file_id, settings, storage)  # un tempo détecté existe déjà

    song = service.set_manual_tempo(file_id, 140.0, settings, storage)

    assert len(song.tempo_changes) == 1
    assert song.tempo_changes[0].bpm == 140.0
    assert song.tempo_changes[0].source == EstimationSource.MANUAL
    assert song.tempo_changes[0].confidence is None


def test_set_manual_time_signature_overrides_and_is_tagged_manual(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_and_normalize(storage, settings, tmp_path)

    song = service.set_manual_time_signature(file_id, 3, 4, settings, storage)

    sig = song.time_signature_changes[0]
    assert (sig.numerator, sig.denominator) == (3, 4)
    assert sig.source == EstimationSource.MANUAL


def test_manual_time_signature_survives_a_later_rhythm_analysis(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    """Une métrique définie manuellement ne doit pas être écrasée par une
    analyse automatique ultérieure (qui ne détecte jamais la métrique)."""

    file_id = _upload_and_normalize(storage, settings, tmp_path)
    service.set_manual_time_signature(file_id, 3, 4, settings, storage)

    outcome = service.analyze(file_id, settings, storage)

    sig = outcome.song.time_signature_changes[0]
    assert (sig.numerator, sig.denominator) == (3, 4)
    assert sig.source == EstimationSource.MANUAL


def test_set_manual_tempo_without_prior_song_bootstraps_one(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_and_normalize(storage, settings, tmp_path)

    song = service.set_manual_tempo(file_id, 100.0, settings, storage)

    assert song.duration_seconds > 0
    assert song.tracks == ()


def test_set_manual_tempo_requires_normalization(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    source = tmp_path / "gen.wav"
    _generate_click_wav(source)
    record = storage.save(
        filename="chanson.wav", declared_content_type="audio/wav", content=source.read_bytes()
    )

    with pytest.raises(AudioNotNormalizedError):
        service.set_manual_tempo(record.file_id, 100.0, settings, storage)


def test_reanalyze_replaces_tempo_changes_entirely(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_and_normalize(storage, settings, tmp_path, bpm=120.0, duration=8.0)
    service.analyze(file_id, settings, storage)
    service.set_manual_tempo(file_id, 140.0, settings, storage)

    outcome = service.analyze(file_id, settings, storage)

    # Une nouvelle analyse automatique remplace la valeur manuelle.
    assert outcome.song.tempo_changes[0].source == EstimationSource.DETECTED
