"""Tests bout-en-bout (TestClient) de la normalisation audio via l'API —
FFmpeg réel, fichiers audio réels générés."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from guitarriff.api.app import create_app
from guitarriff.audio import ffmpeg


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


def _client(monkeypatch, tmp_path, **env: str) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return TestClient(create_app())


def _upload(client: TestClient, tmp_path: Path, **gen_kwargs: object) -> str:
    source = tmp_path / "gen_source.wav"
    _generate_test_wav(source, **gen_kwargs)  # type: ignore[arg-type]
    response = client.post(
        "/audio-files", files={"file": ("chanson.wav", source.read_bytes(), "audio/wav")}
    )
    assert response.status_code == 201
    return response.json()["file_id"]


def test_normalize_endpoint_returns_updated_metadata(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, duration=2.0, rate=44100, channels=2)

    response = client.post(f"/audio-files/{file_id}/normalize")

    assert response.status_code == 200
    body = response.json()
    assert body["normalized"] is True
    assert body["normalized_sample_rate"] == 22050
    assert body["normalized_channels"] == 1
    assert body["duration_seconds"] is not None


def test_get_after_normalize_reflects_persisted_metadata(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path)

    client.post(f"/audio-files/{file_id}/normalize")
    response = client.get(f"/audio-files/{file_id}")

    assert response.json()["normalized"] is True


def test_normalize_unknown_file_id_returns_404(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.post(
        "/audio-files/11111111-1111-1111-1111-111111111111/normalize"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_normalize_rejects_audio_exceeding_max_duration(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path, AUDIO_MAX_DURATION_SECONDS="1")
    file_id = _upload(client, tmp_path, duration=3.0)

    response = client.post(f"/audio-files/{file_id}/normalize")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "audio_too_long"


def test_normalize_returns_503_when_ffmpeg_unavailable(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path)

    with patch.object(ffmpeg.shutil, "which", return_value=None):
        response = client.post(f"/audio-files/{file_id}/normalize")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ffmpeg_unavailable"


def test_health_verbose_reports_ffmpeg_availability(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.get("/health", params={"verbose": True})

    assert response.status_code == 200
    assert response.json()["checks"]["ffmpeg_available"] is True
