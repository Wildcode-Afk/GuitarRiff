"""Tests bout-en-bout (TestClient) de l'API de transcription."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from guitarriff.api.app import create_app
from guitarriff.transcription import service as transcription_service
from guitarriff.transcription.basic_pitch_adapter import RawNoteEvent

FAKE_RAW_NOTES = [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=64, amplitude=0.8)]


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
            "44100",
            "-ac",
            "2",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _client(monkeypatch, tmp_path, **env: str) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return TestClient(create_app())


def _upload_and_normalize(client: TestClient, tmp_path: Path) -> str:
    source = tmp_path / "gen.wav"
    _generate_test_wav(source)
    upload = client.post(
        "/audio-files", files={"file": ("chanson.wav", source.read_bytes(), "audio/wav")}
    )
    file_id = upload.json()["file_id"]
    normalize_response = client.post(f"/audio-files/{file_id}/normalize")
    assert normalize_response.status_code == 200
    return file_id


def test_transcribe_mixture_returns_song_with_disclaimer(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload_and_normalize(client, tmp_path)

    with patch.object(transcription_service, "run_basic_pitch", return_value=FAKE_RAW_NOTES):
        response = client.post(
            f"/audio-files/{file_id}/transcribe", json={"instrument": "guitar", "source": "mixture"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["track_id"] == "guitar"
    assert len(body["song"]["tracks"]) == 1
    assert body["song"]["tracks"][0]["notes"][0]["midi_pitch"] == 64
    assert "basic-pitch" in body["notes"]


def test_get_song_before_transcription_returns_404(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload_and_normalize(client, tmp_path)

    response = client.get(f"/audio-files/{file_id}/song")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_song_after_transcription_matches(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload_and_normalize(client, tmp_path)

    with patch.object(transcription_service, "run_basic_pitch", return_value=FAKE_RAW_NOTES):
        client.post(
            f"/audio-files/{file_id}/transcribe", json={"instrument": "bass", "source": "mixture"}
        )

    response = client.get(f"/audio-files/{file_id}/song")

    assert response.status_code == 200
    assert response.json()["tracks"][0]["instrument"] == "bass"


def test_transcribe_rejects_unsupported_instrument(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload_and_normalize(client, tmp_path)

    response = client.post(
        f"/audio-files/{file_id}/transcribe", json={"instrument": "drums", "source": "mixture"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_instrument_for_transcription"


def test_transcribe_mixture_without_normalization_returns_409(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    source = tmp_path / "gen.wav"
    _generate_test_wav(source)
    upload = client.post(
        "/audio-files", files={"file": ("chanson.wav", source.read_bytes(), "audio/wav")}
    )
    file_id = upload.json()["file_id"]

    response = client.post(
        f"/audio-files/{file_id}/transcribe", json={"instrument": "guitar", "source": "mixture"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "audio_not_normalized"


def test_transcribe_missing_separated_stem_returns_404(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload_and_normalize(client, tmp_path)

    response = client.post(
        f"/audio-files/{file_id}/transcribe", json={"instrument": "bass", "source": "bass"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "separated_stem_not_found"


def test_transcribe_unknown_file_returns_404(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.post(
        "/audio-files/11111111-1111-1111-1111-111111111111/transcribe",
        json={"instrument": "guitar", "source": "mixture"},
    )

    assert response.status_code == 404


def test_health_verbose_reports_basic_pitch_available(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.get("/health", params={"verbose": True})

    assert response.status_code == 200
    assert response.json()["checks"]["basic_pitch_available"] is True


# --- Test d'intégration (modèle réel, exclu par défaut) -------------------


@pytest.mark.integration
def test_real_transcription_end_to_end_through_api(monkeypatch, tmp_path) -> None:
    """Pas de mock ici : exécute une vraie inférence basic-pitch via l'API
    complète, sur une sinusoïde à 440 Hz (donc hauteur MIDI 69 attendue)."""

    client = _client(monkeypatch, tmp_path)
    file_id = _upload_and_normalize(client, tmp_path)

    response = client.post(
        f"/audio-files/{file_id}/transcribe", json={"instrument": "guitar", "source": "mixture"}
    )

    assert response.status_code == 200
    notes = response.json()["song"]["tracks"][0]["notes"]
    assert len(notes) >= 1
    assert notes[0]["midi_pitch"] == 69
