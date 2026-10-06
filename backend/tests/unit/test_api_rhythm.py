"""Tests bout-en-bout (TestClient) de l'API d'analyse rythmique."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from guitarriff.api.app import create_app

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


def _client(monkeypatch, tmp_path, **env: str) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return TestClient(create_app())


def _upload_and_normalize(client: TestClient, tmp_path: Path, **kwargs: object) -> str:
    source = tmp_path / "gen.wav"
    _generate_click_wav(source, **kwargs)  # type: ignore[arg-type]
    upload = client.post(
        "/audio-files", files={"file": ("chanson.wav", source.read_bytes(), "audio/wav")}
    )
    file_id = upload.json()["file_id"]
    normalize_response = client.post(f"/audio-files/{file_id}/normalize")
    assert normalize_response.status_code == 200
    return file_id


def test_analyze_rhythm_returns_detected_tempo(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload_and_normalize(client, tmp_path, bpm=120.0, duration=8.0)

    response = client.post(f"/audio-files/{file_id}/analyze-rhythm")

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] > 0.9
    assert len(body["beat_times"]) > 0
    tempo_change = body["song"]["tempo_changes"][0]
    assert tempo_change["source"] == "detected"
    assert "métrique" in body["notes"].lower()


def test_analyze_rhythm_without_normalization_returns_409(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    source = tmp_path / "gen.wav"
    _generate_click_wav(source)
    upload = client.post(
        "/audio-files", files={"file": ("chanson.wav", source.read_bytes(), "audio/wav")}
    )
    file_id = upload.json()["file_id"]

    response = client.post(f"/audio-files/{file_id}/analyze-rhythm")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "audio_not_normalized"


def test_analyze_rhythm_on_silence_returns_422(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    source = tmp_path / "silence.wav"
    sf.write(str(source), np.zeros(_SAMPLE_RATE * 4, dtype="float32"), _SAMPLE_RATE)
    upload = client.post(
        "/audio-files", files={"file": ("silence.wav", source.read_bytes(), "audio/wav")}
    )
    file_id = upload.json()["file_id"]
    client.post(f"/audio-files/{file_id}/normalize")

    response = client.post(f"/audio-files/{file_id}/analyze-rhythm")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_rhythm_detected"


def test_set_tempo_manually(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload_and_normalize(client, tmp_path)

    response = client.post(f"/audio-files/{file_id}/tempo", json={"bpm": 128.0})

    assert response.status_code == 200
    tempo_change = response.json()["tempo_changes"][0]
    assert tempo_change["bpm"] == 128.0
    assert tempo_change["source"] == "manual"
    assert tempo_change["confidence"] is None


def test_set_tempo_rejects_non_positive_bpm(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload_and_normalize(client, tmp_path)

    response = client.post(f"/audio-files/{file_id}/tempo", json={"bpm": 0})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_set_time_signature_manually(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload_and_normalize(client, tmp_path)

    response = client.post(
        f"/audio-files/{file_id}/time-signature", json={"numerator": 6, "denominator": 8}
    )

    assert response.status_code == 200
    sig = response.json()["time_signature_changes"][0]
    assert (sig["numerator"], sig["denominator"]) == (6, 8)
    assert sig["source"] == "manual"


def test_set_time_signature_rejects_non_power_of_two_denominator(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload_and_normalize(client, tmp_path)

    response = client.post(
        f"/audio-files/{file_id}/time-signature", json={"numerator": 4, "denominator": 5}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_manual_time_signature_then_analyze_rhythm_keeps_manual_value(
    monkeypatch, tmp_path
) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload_and_normalize(client, tmp_path, bpm=120.0, duration=8.0)

    client.post(f"/audio-files/{file_id}/time-signature", json={"numerator": 3, "denominator": 4})
    response = client.post(f"/audio-files/{file_id}/analyze-rhythm")

    sig = response.json()["song"]["time_signature_changes"][0]
    assert (sig["numerator"], sig["denominator"]) == (3, 4)
    assert sig["source"] == "manual"


def test_get_song_reflects_rhythm_analysis(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload_and_normalize(client, tmp_path, bpm=100.0, duration=8.0)

    client.post(f"/audio-files/{file_id}/analyze-rhythm")
    response = client.get(f"/audio-files/{file_id}/song")

    assert response.status_code == 200
    assert response.json()["tempo_changes"][0]["source"] == "detected"
