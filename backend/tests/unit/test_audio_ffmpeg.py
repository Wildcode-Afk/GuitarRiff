"""Tests du module `audio/ffmpeg.py` — utilise de vrais fichiers audio générés
par FFmpeg (pas des en-têtes factices) pour les cas valides, et simule les
pannes FFmpeg (timeout, échec) sans dépendre d'un vrai scénario de panne."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from guitarriff.audio import ffmpeg
from guitarriff.errors import (
    AudioProcessingError,
    AudioProcessingTimeoutError,
    FFmpegUnavailableError,
    InvalidAudioFileError,
)


def _generate_test_wav(
    path: Path, *, duration: float = 2.0, rate: int = 44100, channels: int = 2
) -> None:
    """Génère un vrai fichier WAV de test (sinusoïde) via FFmpeg — pas un
    en-tête simulé : on teste le module contre de l'audio réel."""

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
def real_wav(tmp_path: Path) -> Path:
    path = tmp_path / "source.wav"
    _generate_test_wav(path, duration=2.0, rate=44100, channels=2)
    return path


def test_ffmpeg_available_is_true_in_this_environment() -> None:
    assert ffmpeg.ffmpeg_available() is True


def test_require_ffmpeg_raises_when_binaries_missing() -> None:
    with patch.object(ffmpeg.shutil, "which", return_value=None):
        with pytest.raises(FFmpegUnavailableError):
            ffmpeg.require_ffmpeg()


def test_probe_audio_reads_real_metadata(real_wav: Path) -> None:
    probe = ffmpeg.probe_audio(real_wav, timeout_seconds=30)

    assert probe.sample_rate == 44100
    assert probe.channels == 2
    assert 1.9 <= probe.duration_seconds <= 2.1


def test_probe_audio_rejects_invalid_content(tmp_path: Path) -> None:
    fake = tmp_path / "not_audio.wav"
    fake.write_bytes(b"this is definitely not an audio file")

    with pytest.raises(InvalidAudioFileError):
        ffmpeg.probe_audio(fake, timeout_seconds=30)


def test_probe_audio_rejects_truncated_wav_header(tmp_path: Path) -> None:
    # En-tête RIFF/WAVE plausible (passerait la détection par magic bytes de
    # l'Étape 4) mais corps totalement absent/corrompu.
    truncated = tmp_path / "truncated.wav"
    truncated.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 4)

    with pytest.raises(InvalidAudioFileError):
        ffmpeg.probe_audio(truncated, timeout_seconds=30)


def test_probe_audio_times_out_cleanly(real_wav: Path) -> None:
    with patch.object(
        ffmpeg.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=1)
    ):
        with pytest.raises(AudioProcessingTimeoutError):
            ffmpeg.probe_audio(real_wav, timeout_seconds=1)


def test_normalize_audio_produces_target_format(real_wav: Path, tmp_path: Path) -> None:
    target = tmp_path / "normalized.wav"

    ffmpeg.normalize_audio(real_wav, target, timeout_seconds=30)

    assert target.is_file()
    probe = ffmpeg.probe_audio(target, timeout_seconds=30)
    assert probe.sample_rate == ffmpeg.TARGET_SAMPLE_RATE
    assert probe.channels == ffmpeg.TARGET_CHANNELS


def test_normalize_audio_leaves_no_temp_file_on_success(real_wav: Path, tmp_path: Path) -> None:
    target = tmp_path / "normalized.wav"

    ffmpeg.normalize_audio(real_wav, target, timeout_seconds=30)

    assert not target.with_name(target.name + ".tmp").exists()


def test_normalize_audio_raises_and_cleans_up_on_ffmpeg_failure(
    real_wav: Path, tmp_path: Path
) -> None:
    target = tmp_path / "normalized.wav"
    fake_result = subprocess.CompletedProcess(
        args=["ffmpeg"], returncode=1, stdout=b"", stderr=b"erreur simulee"
    )

    with patch.object(ffmpeg.subprocess, "run", return_value=fake_result):
        with pytest.raises(AudioProcessingError):
            ffmpeg.normalize_audio(real_wav, target, timeout_seconds=30)

    assert not target.exists()
    assert not target.with_name(target.name + ".tmp").exists()


def test_normalize_audio_times_out_and_cleans_up(real_wav: Path, tmp_path: Path) -> None:
    target = tmp_path / "normalized.wav"

    with patch.object(
        ffmpeg.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1)
    ):
        with pytest.raises(AudioProcessingTimeoutError):
            ffmpeg.normalize_audio(real_wav, target, timeout_seconds=1)

    assert not target.exists()
    assert not target.with_name(target.name + ".tmp").exists()


def test_ffmpeg_module_never_uses_shell() -> None:
    import inspect

    source = inspect.getsource(ffmpeg)
    assert "shell=True" not in source
    assert "os.system" not in source
