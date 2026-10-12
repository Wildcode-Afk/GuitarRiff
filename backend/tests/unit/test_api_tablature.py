"""Tests bout-en-bout (TestClient) de l'API de mapping manche."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from guitarriff.api.app import create_app
from guitarriff.transcription import service as transcription_service
from guitarriff.transcription.basic_pitch_adapter import RawNoteEvent


def _client(monkeypatch, tmp_path, **env: str) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return TestClient(create_app())


def _transcribed_file(client: TestClient, tmp_path: Path, notes: list[RawNoteEvent]) -> str:
    source = tmp_path / "gen.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1.0",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    upload = client.post(
        "/audio-files", files={"file": ("chanson.wav", source.read_bytes(), "audio/wav")}
    )
    file_id = upload.json()["file_id"]
    client.post(f"/audio-files/{file_id}/normalize")

    with patch.object(transcription_service, "run_basic_pitch", return_value=notes):
        response = client.post(
            f"/audio-files/{file_id}/transcribe", json={"instrument": "guitar", "source": "mixture"}
        )
    assert response.status_code == 200
    return file_id


def test_map_fretboard_returns_positions_and_disclaimer(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _transcribed_file(
        client,
        tmp_path,
        [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=69, amplitude=0.8)],
    )

    response = client.post(f"/audio-files/{file_id}/map-fretboard", json={"instrument": "guitar"})

    assert response.status_code == 200
    body = response.json()
    assert body["placed_count"] == 1
    assert body["unplaced_count"] == 0
    note = body["song"]["tracks"][0]["notes"][0]
    assert note["instrument_info"]["string_index"] is not None
    assert "doigté" in body["notes"]


def test_map_fretboard_reports_unplaced_notes(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _transcribed_file(
        client,
        tmp_path,
        [
            RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=69, amplitude=0.8),
            RawNoteEvent(
                start_seconds=1.0, end_seconds=1.5, midi_pitch=10, amplitude=0.8
            ),  # hors de portée
        ],
    )

    response = client.post(f"/audio-files/{file_id}/map-fretboard", json={"instrument": "guitar"})

    body = response.json()
    assert body["placed_count"] == 1
    assert body["unplaced_count"] == 1
    assert len(body["unplaced_reasons"]) == 1
    assert "hors de portée" in body["unplaced_reasons"][0]


def test_map_fretboard_accepts_custom_capo(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _transcribed_file(
        client,
        tmp_path,
        [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=44, amplitude=0.8)],
    )

    response = client.post(
        f"/audio-files/{file_id}/map-fretboard", json={"instrument": "guitar", "capo_fret": 2}
    )

    assert response.status_code == 200
    info = response.json()["song"]["tracks"][0]["notes"][0]["instrument_info"]
    assert info["fret"] == 2


def test_map_fretboard_accepts_custom_tuning(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _transcribed_file(
        client,
        tmp_path,
        [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=38, amplitude=0.8)],
    )

    response = client.post(
        f"/audio-files/{file_id}/map-fretboard",
        json={"instrument": "guitar", "tuning": [38, 45, 50, 55, 59, 64]},  # drop D
    )

    assert response.status_code == 200
    track = response.json()["song"]["tracks"][0]
    assert track["tuning"] == [38, 45, 50, 55, 59, 64]
    info = track["notes"][0]["instrument_info"]
    assert (info["string_index"], info["fret"]) == (0, 0)


def test_map_fretboard_rejects_unsupported_instrument(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _transcribed_file(
        client,
        tmp_path,
        [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=69, amplitude=0.8)],
    )

    response = client.post(f"/audio-files/{file_id}/map-fretboard", json={"instrument": "drums"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_instrument_for_fretboard_mapping"


def test_map_fretboard_rejects_capo_above_max_fret(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _transcribed_file(
        client,
        tmp_path,
        [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=69, amplitude=0.8)],
    )

    response = client.post(
        f"/audio-files/{file_id}/map-fretboard",
        json={"instrument": "guitar", "capo_fret": 10, "max_fret": 5},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_map_fretboard_rejects_invalid_tuning(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _transcribed_file(
        client,
        tmp_path,
        [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=69, amplitude=0.8)],
    )

    response = client.post(
        f"/audio-files/{file_id}/map-fretboard", json={"instrument": "guitar", "tuning": [40, 300]}
    )

    assert response.status_code == 422


def test_map_fretboard_without_transcription_returns_404(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    source = tmp_path / "gen.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1.0",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    upload = client.post(
        "/audio-files", files={"file": ("chanson.wav", source.read_bytes(), "audio/wav")}
    )
    file_id = upload.json()["file_id"]

    response = client.post(f"/audio-files/{file_id}/map-fretboard", json={"instrument": "guitar"})

    assert response.status_code == 404


def test_get_song_reflects_fretboard_mapping(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _transcribed_file(
        client,
        tmp_path,
        [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=69, amplitude=0.8)],
    )
    client.post(f"/audio-files/{file_id}/map-fretboard", json={"instrument": "guitar"})

    response = client.get(f"/audio-files/{file_id}/song")

    assert response.json()["tracks"][0]["notes"][0]["instrument_info"] is not None
