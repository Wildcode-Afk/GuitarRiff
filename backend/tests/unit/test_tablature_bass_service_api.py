"""Tests du service et de l'API pour la basse (Étape 12) : mapping avec le
profil basse, rendu de la tablature, erreurs."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.api.app import create_app
from guitarriff.audio.service import normalize_stored_audio
from guitarriff.config import Settings
from guitarriff.errors import (
    FretboardNotMappedError,
    InvalidInstrumentForFretboardMappingError,
    NotFoundError,
)
from guitarriff.model import InstrumentKind
from guitarriff.tablature import service
from guitarriff.tablature.fretboard import STANDARD_BASS_TUNING
from guitarriff.transcription import service as transcription_service
from guitarriff.transcription.basic_pitch_adapter import RawNoteEvent


def _raw(pitch: int, start: float, duration: float = 0.2) -> RawNoteEvent:
    return RawNoteEvent(
        start_seconds=start, end_seconds=start + duration, midi_pitch=pitch, amplitude=0.8
    )


def _generate_wav(path: Path) -> None:
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
            str(path),
        ],
        check=True,
        capture_output=True,
    )


# --- Service ----------------------------------------------------------------


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path)


@pytest.fixture
def storage(settings: Settings) -> AudioFileStorage:
    return AudioFileStorage(settings)


def _transcribed_bass(storage, settings, tmp_path, raw_notes) -> str:
    source = tmp_path / "gen.wav"
    _generate_wav(source)
    record = storage.save(
        filename="basse.wav", declared_content_type="audio/wav", content=source.read_bytes()
    )
    normalize_stored_audio(record.file_id, settings, storage)
    with patch.object(transcription_service, "run_basic_pitch", return_value=raw_notes):
        transcription_service.transcribe(
            record.file_id, InstrumentKind.BASS, "mixture", settings, storage
        )
    return record.file_id


def test_bass_mapping_defaults_to_standard_four_string_tuning(settings, storage, tmp_path) -> None:
    file_id = _transcribed_bass(storage, settings, tmp_path, [_raw(28, 0.0)])

    outcome = service.map_fretboard(file_id, InstrumentKind.BASS, storage)

    assert outcome.song.tracks[0].tuning == STANDARD_BASS_TUNING
    assert outcome.placed_count == 1


def test_bass_mapping_uses_the_bass_profile(settings, storage, tmp_path) -> None:
    # Avec le profil basse la ligne reste sur la corde de la (voir test_tablature_bass).
    file_id = _transcribed_bass(
        storage, settings, tmp_path, [_raw(33, 0.0), _raw(37, 0.3), _raw(39, 0.6)]
    )

    outcome = service.map_fretboard(file_id, InstrumentKind.BASS, storage)

    infos = [
        (n.instrument_info.string_index, n.instrument_info.fret)
        for n in outcome.song.tracks[0].notes
    ]
    assert infos == [(1, 0), (1, 4), (1, 6)]


def test_bass_mapping_accepts_five_string_tuning_and_capo(settings, storage, tmp_path) -> None:
    file_id = _transcribed_bass(storage, settings, tmp_path, [_raw(23, 0.0)])

    outcome = service.map_fretboard(
        file_id, InstrumentKind.BASS, storage, tuning=(23, 28, 33, 38, 43)
    )
    assert outcome.placed_count == 1
    assert outcome.unplaced_count == 0

    with_capo = service.map_fretboard(
        file_id, InstrumentKind.BASS, storage, tuning=(23, 28, 33, 38, 43), capo_fret=1
    )
    assert with_capo.song.tracks[0].capo_fret == 1
    assert storage.read_song(file_id).tracks[0].capo_fret == 1


def test_render_requires_prior_mapping(settings, storage, tmp_path) -> None:
    file_id = _transcribed_bass(storage, settings, tmp_path, [_raw(28, 0.0)])
    with pytest.raises(FretboardNotMappedError):
        service.render_tablature(file_id, InstrumentKind.BASS, storage)


def test_render_returns_readable_tab_and_does_not_modify_the_song(
    settings, storage, tmp_path
) -> None:
    file_id = _transcribed_bass(storage, settings, tmp_path, [_raw(28, 0.0), _raw(33, 0.5)])
    service.map_fretboard(file_id, InstrumentKind.BASS, storage)
    before = storage.read_song(file_id)

    rendering = service.render_tablature(file_id, InstrumentKind.BASS, storage)

    assert rendering.text.splitlines()[0] == "Basse — accordage E A D G"
    assert rendering.placed_count == 2
    assert storage.read_song(file_id) == before  # lecture seule
    assert all(n.position is None for n in storage.read_song(file_id).tracks[0].notes)


def test_render_materializes_silences_using_the_song_tempo(settings, storage, tmp_path) -> None:
    # Tempo par défaut du Song : 120 BPM => 0.5 s par temps. Silence de 2.5 s => 5 colonnes vides.
    file_id = _transcribed_bass(
        storage, settings, tmp_path, [_raw(28, 0.0, 0.5), _raw(28, 3.0, 0.5)]
    )
    service.map_fretboard(file_id, InstrumentKind.BASS, storage)

    text = service.render_tablature(file_id, InstrumentKind.BASS, storage).text
    e_line = next(line for line in text.splitlines() if line.startswith("E|"))

    # 120 BPM en 4/4 : la note à 3 s tombe dans la mesure 2, d'où la barre de mesure
    # après les 5 colonnes vides.
    assert e_line == "E|-0-" + "---" * 5 + "|-0-|"


def test_render_draws_bar_lines_from_computed_positions(settings, storage, tmp_path) -> None:
    # 120 BPM en 4/4 : une mesure = 2 s. Notes aux mesures 1, 1 et 2.
    # Notes de 0,9 s : les écarts (0,1 s) restent inférieurs à un temps, pas de colonne vide.
    file_id = _transcribed_bass(
        storage,
        settings,
        tmp_path,
        [_raw(28, 0.0, 0.9), _raw(28, 1.0, 0.9), _raw(28, 2.0, 0.9)],
    )
    service.map_fretboard(file_id, InstrumentKind.BASS, storage)

    text = service.render_tablature(file_id, InstrumentKind.BASS, storage).text
    e_line = next(line for line in text.splitlines() if line.startswith("E|"))

    assert e_line == "E|-0--0-|-0-|"


def test_service_rejects_unsupported_instrument(settings, storage, tmp_path) -> None:
    file_id = _transcribed_bass(storage, settings, tmp_path, [_raw(28, 0.0)])
    with pytest.raises(InvalidInstrumentForFretboardMappingError):
        service.render_tablature(file_id, InstrumentKind.PIANO, storage)


def test_render_without_song_raises_not_found(settings, storage, tmp_path) -> None:
    source = tmp_path / "gen.wav"
    _generate_wav(source)
    record = storage.save(
        filename="basse.wav", declared_content_type="audio/wav", content=source.read_bytes()
    )
    with pytest.raises(NotFoundError):
        service.render_tablature(record.file_id, InstrumentKind.BASS, storage)


# --- API --------------------------------------------------------------------


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return TestClient(create_app())


def _api_transcribed(client, tmp_path, raw_notes, instrument="bass") -> str:
    source = tmp_path / "gen.wav"
    _generate_wav(source)
    upload = client.post(
        "/audio-files", files={"file": ("b.wav", source.read_bytes(), "audio/wav")}
    )
    file_id = upload.json()["file_id"]
    client.post(f"/audio-files/{file_id}/normalize")
    with patch.object(transcription_service, "run_basic_pitch", return_value=raw_notes):
        response = client.post(
            f"/audio-files/{file_id}/transcribe",
            json={"instrument": instrument, "source": "mixture"},
        )
    assert response.status_code == 200
    return file_id


def test_api_map_bass_mentions_bassist_not_guitarist(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _api_transcribed(client, tmp_path, [_raw(28, 0.0)])

    response = client.post(f"/audio-files/{file_id}/map-fretboard", json={"instrument": "bass"})

    assert response.status_code == 200
    notes = response.json()["notes"]
    assert "bassiste" in notes and "guitariste" not in notes
    assert response.json()["song"]["tracks"][0]["tuning"] == list(STANDARD_BASS_TUNING)


def test_api_map_guitar_message_still_mentions_guitarist(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _api_transcribed(client, tmp_path, [_raw(64, 0.0)], instrument="guitar")

    response = client.post(f"/audio-files/{file_id}/map-fretboard", json={"instrument": "guitar"})

    assert "guitariste" in response.json()["notes"]


def test_api_get_tablature_returns_text(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _api_transcribed(client, tmp_path, [_raw(28, 0.0), _raw(33, 0.5), _raw(10, 1.0)])
    client.post(f"/audio-files/{file_id}/map-fretboard", json={"instrument": "bass"})

    response = client.get(f"/audio-files/{file_id}/tablature", params={"instrument": "bass"})

    assert response.status_code == 200
    body = response.json()
    assert body["instrument"] == "bass"
    assert body["placed_count"] == 2
    assert body["unplaced_count"] == 1
    assert "E|" in body["text"] and "G|" in body["text"]
    assert "1 note(s) sans position" in body["text"]
    assert "durées" in body["notes"]


def test_api_get_tablature_before_mapping_returns_409(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _api_transcribed(client, tmp_path, [_raw(28, 0.0)])

    response = client.get(f"/audio-files/{file_id}/tablature", params={"instrument": "bass"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "fretboard_not_mapped"


def test_api_get_tablature_validates_max_width(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _api_transcribed(client, tmp_path, [_raw(28, 0.0)])
    client.post(f"/audio-files/{file_id}/map-fretboard", json={"instrument": "bass"})

    too_small = client.get(
        f"/audio-files/{file_id}/tablature", params={"instrument": "bass", "max_width": 5}
    )
    assert too_small.status_code == 422

    custom = client.get(
        f"/audio-files/{file_id}/tablature", params={"instrument": "bass", "max_width": 40}
    )
    assert custom.status_code == 200


def test_api_get_tablature_rejects_unsupported_instrument(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _api_transcribed(client, tmp_path, [_raw(28, 0.0)])

    response = client.get(f"/audio-files/{file_id}/tablature", params={"instrument": "drums"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_instrument_for_fretboard_mapping"


def test_api_get_tablature_without_instrument_param_is_a_validation_error(
    monkeypatch, tmp_path
) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _api_transcribed(client, tmp_path, [_raw(28, 0.0)])

    response = client.get(f"/audio-files/{file_id}/tablature")

    assert response.status_code == 422
