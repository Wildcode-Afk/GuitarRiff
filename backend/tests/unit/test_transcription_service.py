"""Tests de `transcription/service.py` — basic-pitch simulé, fichiers audio
réels (générés par FFmpeg), stockage réel."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.audio.service import normalize_stored_audio
from guitarriff.config import Settings
from guitarriff.errors import (
    AudioNotNormalizedError,
    InvalidInstrumentForTranscriptionError,
    SeparatedStemNotFoundError,
)
from guitarriff.model import InstrumentKind
from guitarriff.transcription import service
from guitarriff.transcription.basic_pitch_adapter import RawNoteEvent


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


def _upload_and_normalize(storage: AudioFileStorage, settings: Settings, tmp_path: Path) -> str:
    source = tmp_path / "gen.wav"
    _generate_test_wav(source)
    record = storage.save(
        filename="chanson.wav", declared_content_type="audio/wav", content=source.read_bytes()
    )
    normalize_stored_audio(record.file_id, settings, storage)
    return record.file_id


FAKE_RAW_NOTES = [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=64, amplitude=0.8)]


def test_rejects_unsupported_instrument(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_and_normalize(storage, settings, tmp_path)

    with pytest.raises(InvalidInstrumentForTranscriptionError):
        service.transcribe(file_id, InstrumentKind.DRUMS, "mixture", settings, storage)


def test_mixture_source_requires_prior_normalization(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    source = tmp_path / "gen.wav"
    _generate_test_wav(source)
    record = storage.save(
        filename="chanson.wav", declared_content_type="audio/wav", content=source.read_bytes()
    )

    with pytest.raises(AudioNotNormalizedError):
        service.transcribe(record.file_id, InstrumentKind.GUITAR, "mixture", settings, storage)


def test_separated_stem_source_requires_prior_separation(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_and_normalize(storage, settings, tmp_path)

    with pytest.raises(SeparatedStemNotFoundError):
        service.transcribe(file_id, InstrumentKind.BASS, "bass", settings, storage)


def test_successful_transcription_creates_song(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_and_normalize(storage, settings, tmp_path)

    with patch.object(service, "run_basic_pitch", return_value=FAKE_RAW_NOTES):
        result = service.transcribe(file_id, InstrumentKind.GUITAR, "mixture", settings, storage)

    assert result.track_id == "guitar"
    assert len(result.song.tracks) == 1
    assert result.song.tracks[0].notes[0].midi_pitch == 64
    assert "basic-pitch" in result.notes

    # Persisté : relisible depuis le stockage.
    persisted = storage.read_song(file_id)
    assert persisted == result.song


def test_second_instrument_adds_a_second_track(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_and_normalize(storage, settings, tmp_path)

    with patch.object(service, "run_basic_pitch", return_value=FAKE_RAW_NOTES):
        service.transcribe(file_id, InstrumentKind.GUITAR, "mixture", settings, storage)
        result = service.transcribe(file_id, InstrumentKind.BASS, "mixture", settings, storage)

    assert len(result.song.tracks) == 2
    assert {t.instrument for t in result.song.tracks} == {
        InstrumentKind.GUITAR,
        InstrumentKind.BASS,
    }


def test_retranscribing_same_instrument_replaces_track_not_duplicates(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_and_normalize(storage, settings, tmp_path)
    second_notes = [RawNoteEvent(start_seconds=0.0, end_seconds=1.0, midi_pitch=40, amplitude=0.9)]

    with patch.object(service, "run_basic_pitch", return_value=FAKE_RAW_NOTES):
        service.transcribe(file_id, InstrumentKind.GUITAR, "mixture", settings, storage)

    with patch.object(service, "run_basic_pitch", return_value=second_notes):
        result = service.transcribe(file_id, InstrumentKind.GUITAR, "mixture", settings, storage)

    assert len(result.song.tracks) == 1
    assert result.song.tracks[0].notes[0].midi_pitch == 40


def test_disclaimer_mentions_separation_when_using_mixture(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_and_normalize(storage, settings, tmp_path)

    with patch.object(service, "run_basic_pitch", return_value=FAKE_RAW_NOTES):
        result = service.transcribe(file_id, InstrumentKind.GUITAR, "mixture", settings, storage)

    assert "séparée" in result.notes


def test_disclaimer_warns_other_stem_is_not_isolated_guitar(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_and_normalize(storage, settings, tmp_path)
    other_stem_dir = storage.separated_dir(file_id, "htdemucs")
    other_stem_dir.mkdir(parents=True, exist_ok=True)
    _generate_test_wav(other_stem_dir / "other.wav")

    with patch.object(service, "run_basic_pitch", return_value=FAKE_RAW_NOTES):
        result = service.transcribe(file_id, InstrumentKind.GUITAR, "other", settings, storage)

    assert "isolée" in result.notes


def test_prefers_htdemucs_6s_stem_over_htdemucs_when_both_cached(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_and_normalize(storage, settings, tmp_path)

    htdemucs_dir = storage.separated_dir(file_id, "htdemucs")
    htdemucs_dir.mkdir(parents=True, exist_ok=True)
    _generate_test_wav(htdemucs_dir / "bass.wav", duration=1.0)

    htdemucs_6s_dir = storage.separated_dir(file_id, "htdemucs_6s")
    htdemucs_6s_dir.mkdir(parents=True, exist_ok=True)
    _generate_test_wav(
        htdemucs_6s_dir / "bass.wav", duration=2.0
    )  # distincte pour vérifier laquelle est prise

    captured_paths = []

    def fake_run(path, *, timeout_seconds):
        captured_paths.append(path)
        return FAKE_RAW_NOTES

    with patch.object(service, "run_basic_pitch", side_effect=fake_run):
        service.transcribe(file_id, InstrumentKind.BASS, "bass", settings, storage)

    assert captured_paths[0] == htdemucs_6s_dir / "bass.wav"
