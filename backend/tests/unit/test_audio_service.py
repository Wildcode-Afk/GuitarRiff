"""Tests de `audio/service.py` — orchestration réelle avec FFmpeg et le
stockage, sur de vrais fichiers audio générés."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.audio.service import normalize_stored_audio
from guitarriff.config import Settings
from guitarriff.errors import AudioTooLongError, InvalidAudioFileError


def _generate_test_wav(
    path: Path, *, duration: float = 2.0, rate: int = 44100, channels: int = 2
) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-ar",
            str(rate),
            "-ac",
            str(channels),
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


def _upload_real_wav(storage: AudioFileStorage, tmp_path: Path, **gen_kwargs: object) -> str:
    source = tmp_path / "gen_source.wav"
    _generate_test_wav(source, **gen_kwargs)  # type: ignore[arg-type]
    record = storage.save(
        filename="ma_chanson.wav",
        declared_content_type="audio/wav",
        content=source.read_bytes(),
    )
    return record.file_id


def test_normalize_stored_audio_updates_metadata(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_real_wav(storage, tmp_path, duration=2.0, rate=44100, channels=2)

    record = normalize_stored_audio(file_id, settings, storage)

    assert record.normalized is True
    assert record.normalized_sample_rate == 22050
    assert record.normalized_channels == 1
    assert record.duration_seconds is not None
    assert 1.9 <= record.duration_seconds <= 2.1


def test_normalize_stored_audio_persists_to_disk(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    file_id = _upload_real_wav(storage, tmp_path)

    normalize_stored_audio(file_id, settings, storage)

    # Les métadonnées doivent être relisibles, pas seulement renvoyées en mémoire.
    fetched = storage.get(file_id)
    assert fetched.normalized is True

    normalized_path = storage.normalized_path(file_id)
    assert normalized_path.is_file()


def test_normalize_stored_audio_rejects_video_exceeding_max_duration(
    storage: AudioFileStorage, tmp_path: Path
) -> None:
    short_settings = Settings(_env_file=None, data_dir=tmp_path, audio_max_duration_seconds=1)
    short_storage = AudioFileStorage(short_settings)
    file_id = _upload_real_wav(short_storage, tmp_path, duration=3.0)

    with pytest.raises(AudioTooLongError):
        normalize_stored_audio(file_id, short_settings, short_storage)

    # Aucun fichier normalisé ne doit avoir été créé : le rejet intervient
    # avant toute conversion.
    assert not short_storage.normalized_path(file_id).exists()


def test_normalize_stored_audio_rejects_corrupted_stored_file(
    settings: Settings, storage: AudioFileStorage
) -> None:
    # Un en-tête WAV plausible (passe la détection par contenu de l'Étape 4)
    # mais un corps corrompu/tronqué : rejeté seulement à la normalisation,
    # quand FFmpeg tente réellement de le lire.
    corrupted_wav = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
    record = storage.save(
        filename="corrompu.wav", declared_content_type="audio/wav", content=corrupted_wav
    )

    with pytest.raises(InvalidAudioFileError):
        normalize_stored_audio(record.file_id, settings, storage)
