"""Tests de `transcription/basic_pitch_adapter.py`.

Deux familles :
1. Tests unitaires rapides, avec `predict` simulé (toujours exécutés).
2. Tests d'intégration marqués `integration`, qui appellent **le vrai**
   basic-pitch (installé comme dépendance requise de ce projet — voir
   pyproject.toml). Exclus de la suite par défaut (voir
   `[tool.pytest.ini_options]`), à lancer explicitement avec `pytest -m
   integration` quand on veut vérifier l'intégration réelle.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from guitarriff.errors import TranscriptionError, TranscriptionTimeoutError
from guitarriff.transcription import basic_pitch_adapter as adapter


def _generate_test_wav(path: Path, *, frequency: int = 440, duration: float = 1.0) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:duration={duration}",
            "-ar",
            "22050",
            "-ac",
            "1",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _generate_silence_wav(path: Path, *, duration: float = 1.0) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=22050:cl=mono",
            "-t",
            str(duration),
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_basic_pitch_available_is_true_in_this_environment() -> None:
    # basic-pitch est une dépendance requise du projet (pas optionnelle,
    # contrairement à Demucs) — fait vérifié, pas supposé.
    assert adapter.basic_pitch_available() is True


def test_run_basic_pitch_converts_raw_tuples(tmp_path: Path) -> None:
    fake_note_events = [(0.1, 0.6, 69, 0.6, [1, 1]), (0.6, 1.0, 72, 0.5, None)]

    def fake_predict(path: str):
        return ({}, None, fake_note_events)

    with patch.object(adapter, "_import_predict", return_value=fake_predict):
        results = adapter.run_basic_pitch(tmp_path / "audio.wav", timeout_seconds=10)

    assert results == [
        adapter.RawNoteEvent(start_seconds=0.1, end_seconds=0.6, midi_pitch=69, amplitude=0.6),
        adapter.RawNoteEvent(start_seconds=0.6, end_seconds=1.0, midi_pitch=72, amplitude=0.5),
    ]


def test_run_basic_pitch_returns_empty_list_for_silence_shape(tmp_path: Path) -> None:
    def fake_predict(path: str):
        return ({}, None, [])

    with patch.object(adapter, "_import_predict", return_value=fake_predict):
        results = adapter.run_basic_pitch(tmp_path / "audio.wav", timeout_seconds=10)

    assert results == []


def test_run_basic_pitch_wraps_generic_failure(tmp_path: Path) -> None:
    def failing_predict(path: str):
        raise RuntimeError("panne interne du modèle")

    with patch.object(adapter, "_import_predict", return_value=failing_predict):
        with pytest.raises(TranscriptionError):
            adapter.run_basic_pitch(tmp_path / "audio.wav", timeout_seconds=10)


def test_run_basic_pitch_wraps_file_not_found(tmp_path: Path) -> None:
    def missing_file_predict(path: str):
        raise FileNotFoundError(path)

    with patch.object(adapter, "_import_predict", return_value=missing_file_predict):
        with pytest.raises(TranscriptionError):
            adapter.run_basic_pitch(tmp_path / "does_not_exist.wav", timeout_seconds=10)


def test_run_basic_pitch_times_out_cleanly(tmp_path: Path) -> None:
    def slow_predict(path: str):
        time.sleep(5)
        return ({}, None, [])

    with patch.object(adapter, "_import_predict", return_value=slow_predict):
        with pytest.raises(TranscriptionTimeoutError):
            adapter.run_basic_pitch(tmp_path / "audio.wav", timeout_seconds=1)


def test_import_predict_raises_transcription_error_when_library_absent() -> None:
    with patch.dict("sys.modules", {"basic_pitch": None, "basic_pitch.inference": None}):
        with pytest.raises(TranscriptionError):
            adapter._import_predict()


# --- Tests d'intégration (modèle réel, exclus par défaut) ---------------


@pytest.mark.integration
def test_real_basic_pitch_detects_known_pitch(tmp_path: Path) -> None:
    """Vérifié manuellement avant d'écrire ce test : une sinusoïde à 440 Hz
    doit être détectée comme la hauteur MIDI 69 (A4)."""

    audio_path = tmp_path / "a440.wav"
    _generate_test_wav(audio_path, frequency=440, duration=1.0)

    results = adapter.run_basic_pitch(audio_path, timeout_seconds=60)

    assert len(results) >= 1
    assert results[0].midi_pitch == 69
    assert 0.0 <= results[0].amplitude <= 1.0


@pytest.mark.integration
def test_real_basic_pitch_returns_empty_for_silence(tmp_path: Path) -> None:
    audio_path = tmp_path / "silence.wav"
    _generate_silence_wav(audio_path, duration=1.0)

    results = adapter.run_basic_pitch(audio_path, timeout_seconds=60)

    assert results == []
