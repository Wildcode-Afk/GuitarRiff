"""Tests bout-en-bout (TestClient) de l'analyse harmonique : estimation
d'accords, déduction depuis des notes, correction manuelle, piste clavier."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from guitarriff.api.app import create_app
from guitarriff.transcription import service as transcription_service
from guitarriff.transcription.basic_pitch_adapter import RawNoteEvent
from tests.unit.synth_audio import SR, sequence

PROGRESSION = [
    ([48, 64, 67, 72], 2.0),  # C
    ([41, 60, 65, 69], 2.0),  # F
    ([43, 62, 67, 71], 2.0),  # G
    ([45, 60, 64, 69], 2.0),  # Am
]
CSUS2 = [([48, 50, 55, 60], 3.0)]  # notes identiques à Gsus4 : ambigu par nature


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return TestClient(create_app())


def _upload(
    client: TestClient, tmp_path: Path, signal: np.ndarray, *, normalize: bool = True
) -> str:
    source = tmp_path / "gen.wav"
    sf.write(str(source), signal, SR)
    response = client.post(
        "/audio-files", files={"file": ("morceau.wav", source.read_bytes(), "audio/wav")}
    )
    assert response.status_code == 201
    file_id = response.json()["file_id"]
    if normalize:
        assert client.post(f"/audio-files/{file_id}/normalize").status_code == 200
    return file_id


def _raw(pitch: int, start: float, duration: float = 1.0) -> RawNoteEvent:
    return RawNoteEvent(
        start_seconds=start, end_seconds=start + duration, midi_pitch=pitch, amplitude=0.8
    )


def _chord_input(root: int, quality: str, start: float, duration: float = 2.0, **extra) -> dict:
    return {
        "root_pitch_class": root,
        "quality": quality,
        "start_seconds": start,
        "duration_seconds": duration,
        **extra,
    }


def _beats_from_start(chord: dict) -> float:
    return (chord["position"]["bar"] - 1) * 4 + chord["position"]["beat"] - 1


# --- Estimation à partir de l'audio -----------------------------------------


def test_estimate_chords_returns_the_progression_with_times_and_positions(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))

    response = client.post(f"/audio-files/{file_id}/estimate-chords", json={})

    assert response.status_code == 200
    body = response.json()
    assert [c["symbol"] for c in body["chords"]] == ["C", "F", "G", "Am"]
    assert body["ambiguous_count"] == 0
    assert body["chords"][0]["source"] == "detected"
    assert body["chords"][0]["confidence"] > 0.7
    assert body["chords"][1]["start_seconds"] == pytest.approx(2.0, abs=0.12)
    # Positions rythmiques calculées pour la réponse (120 BPM 4/4 : mesure = 2 s).
    # Une frontière détectée porte l'incertitude d'une trame d'analyse (~93 ms) :
    # le F, qui débute à 2.0 s, peut tomber juste avant la barre (mesure 1, temps
    # 4.99). On compare donc la distance au début en temps, pas la mesure exacte.
    assert _beats_from_start(body["chords"][0]) == pytest.approx(0.0, abs=0.3)
    assert _beats_from_start(body["chords"][1]) == pytest.approx(4.0, abs=0.3)
    assert "synthétiques" in body["notes"] and "ambigu" in body["notes"]


def test_chord_json_exposes_symbol_inversion_and_pitch_classes(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    signal = sequence([([40, 60, 64, 67], 2.0)])  # do/mi : basse mi2
    file_id = _upload(client, tmp_path, signal)

    chord = client.post(f"/audio-files/{file_id}/estimate-chords", json={}).json()["chords"][0]

    assert (chord["symbol"], chord["inversion"], chord["bass_pitch_class"]) == ("C/E", 1, 4)
    assert chord["pitch_classes"] == [0, 4, 7]


def test_positions_are_not_persisted_but_available_on_demand(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))
    client.post(f"/audio-files/{file_id}/estimate-chords", json={})

    stored = client.get(f"/audio-files/{file_id}/song").json()
    computed = client.get(f"/audio-files/{file_id}/song", params={"with_positions": True}).json()

    assert all(c["position"] is None for c in stored["chords"])
    assert all(c["position"] is not None for c in computed["chords"])
    assert len(stored["chords"]) == len(computed["chords"]) == 4


def test_ambiguous_chord_is_reported_as_ambiguous_with_alternatives(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(CSUS2))

    body = client.post(f"/audio-files/{file_id}/estimate-chords", json={}).json()

    assert body["ambiguous_count"] == 1
    chord = body["chords"][0]
    assert chord["ambiguous"] is True
    assert chord["confidence"] < 0.1
    assert {a["symbol"] for a in chord["alternatives"]} & {"Csus2", "Gsus4"}


def test_silence_gives_an_empty_chord_list_not_an_error(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, np.zeros(3 * SR, dtype="float32"))

    response = client.post(f"/audio-files/{file_id}/estimate-chords", json={})

    assert response.status_code == 200
    assert response.json()["chords"] == []


def test_estimate_chords_requires_normalization_for_the_mixture(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION), normalize=False)

    response = client.post(f"/audio-files/{file_id}/estimate-chords", json={})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "audio_not_normalized"


def test_estimate_chords_on_a_separated_stem(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION), normalize=False)
    stem_dir = tmp_path / "uploads" / file_id / "separated" / "htdemucs"
    stem_dir.mkdir(parents=True)
    sf.write(str(stem_dir / "other.wav"), sequence([([48, 64, 67, 72], 2.0)]), SR)

    response = client.post(f"/audio-files/{file_id}/estimate-chords", json={"source": "other"})

    assert response.status_code == 200
    assert [c["symbol"] for c in response.json()["chords"]] == ["C"]


def test_estimate_chords_missing_stem_returns_404(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))

    response = client.post(f"/audio-files/{file_id}/estimate-chords", json={"source": "bass"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "separated_stem_not_found"


def test_estimate_chords_unknown_file_returns_404(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/audio-files/11111111-1111-1111-1111-111111111111/estimate-chords", json={}
    )
    assert response.status_code == 404


def test_re_estimating_replaces_the_previous_chords(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))
    client.post(f"/audio-files/{file_id}/estimate-chords", json={})
    client.post(f"/audio-files/{file_id}/estimate-chords", json={})

    assert len(client.get(f"/audio-files/{file_id}/song").json()["chords"]) == 4


# --- Déduction depuis des notes transcrites ---------------------------------


def _transcribe(client, file_id, raw_notes, instrument="guitar") -> None:
    with patch.object(transcription_service, "run_basic_pitch", return_value=raw_notes):
        response = client.post(
            f"/audio-files/{file_id}/transcribe",
            json={"instrument": instrument, "source": "mixture"},
        )
    assert response.status_code == 200


def test_chords_from_notes_gives_exact_bass_and_inversion(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))
    notes = [
        _raw(52, 0.0),
        _raw(60, 0.0),
        _raw(67, 0.0),
        _raw(65, 2.0),
        _raw(69, 2.0),
        _raw(72, 2.0),
    ]
    _transcribe(client, file_id, notes)

    response = client.post(
        f"/audio-files/{file_id}/chords-from-notes", json={"instrument": "guitar"}
    )

    assert response.status_code == 200
    chords = response.json()["chords"]
    assert [(c["symbol"], c["inversion"]) for c in chords] == [("C/E", 1), ("F", 0)]
    assert "exacts" in response.json()["notes"]


def test_chords_from_notes_rejects_drums(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))
    _transcribe(client, file_id, [_raw(60, 0.0)])

    response = client.post(
        f"/audio-files/{file_id}/chords-from-notes", json={"instrument": "drums"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_chord_source"


def test_chords_from_notes_without_transcription_or_track_returns_404(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))
    no_song = client.post(
        f"/audio-files/{file_id}/chords-from-notes", json={"instrument": "guitar"}
    )
    assert no_song.status_code == 404

    _transcribe(client, file_id, [_raw(60, 0.0)], instrument="guitar")
    no_track = client.post(f"/audio-files/{file_id}/chords-from-notes", json={"instrument": "bass"})
    assert no_track.status_code == 404


# --- Correction manuelle ----------------------------------------------------


def test_manual_chords_are_certain_and_replace_detected_ones(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))
    client.post(f"/audio-files/{file_id}/estimate-chords", json={})

    response = client.put(
        f"/audio-files/{file_id}/chords",
        json={
            "chords": [_chord_input(2, "min", 0.0), _chord_input(7, "7", 2.0, bass_pitch_class=11)]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [(c["symbol"], c["source"]) for c in body["chords"]] == [
        ("Dm", "manual"),
        ("G7/B", "manual"),
    ]
    assert all(c["confidence"] is None and c["ambiguous"] is False for c in body["chords"])
    assert body["chords"][1]["inversion"] == 1
    assert body["ambiguous_count"] == 0
    assert len(client.get(f"/audio-files/{file_id}/song").json()["chords"]) == 2


def test_manual_chords_work_without_any_prior_analysis(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION), normalize=False)

    response = client.put(
        f"/audio-files/{file_id}/chords", json={"chords": [_chord_input(0, "maj", 0.0)]}
    )

    assert response.status_code == 200
    assert response.json()["song"]["duration_seconds"] == pytest.approx(8.0, abs=0.05)


def test_empty_chord_list_clears_the_chords(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))
    client.post(f"/audio-files/{file_id}/estimate-chords", json={})

    response = client.put(f"/audio-files/{file_id}/chords", json={"chords": []})

    assert response.status_code == 200 and response.json()["chords"] == []


@pytest.mark.parametrize(
    "chords",
    [
        [_chord_input(0, "maj", 0.0, 3.0), _chord_input(5, "maj", 2.0)],  # chevauchement
        [_chord_input(0, "maj", 5.0), _chord_input(5, "maj", 0.0)],  # non triés
        [_chord_input(0, "13th", 0.0)],  # qualité inconnue
        [_chord_input(12, "maj", 0.0)],  # classe de hauteur hors bornes
        [_chord_input(0, "maj", 0.0, 0.0)],  # durée nulle
        [_chord_input(0, "maj", -1.0)],  # début négatif
        [_chord_input(0, "maj", 0.0, bass_pitch_class=12)],
    ],
)
def test_invalid_manual_chords_are_rejected_with_422(monkeypatch, tmp_path, chords):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))

    response = client.put(f"/audio-files/{file_id}/chords", json={"chords": chords})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --- Piste clavier ----------------------------------------------------------


def test_keyboard_requires_chords(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))

    response = client.post(f"/audio-files/{file_id}/generate-keyboard", json={})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_chords"


def test_keyboard_from_estimated_chords_has_two_hands_and_a_disclaimer(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))
    client.post(f"/audio-files/{file_id}/estimate-chords", json={})

    response = client.post(f"/audio-files/{file_id}/generate-keyboard", json={})

    assert response.status_code == 200
    body = response.json()
    tracks = {t["id"]: t for t in body["song"]["tracks"]}
    assert set(tracks) == {"piano-rh", "piano-lh"}
    assert tracks["piano-rh"]["display"]["clef"] == "treble"
    assert tracks["piano-lh"]["display"]["clef"] == "bass"
    assert body["chord_count"] == 4 and body["left_hand_note_count"] == 4
    assert body["right_hand_note_count"] == 3 + 3 + 3 + 3
    assert "pas une transcription" in body["notes"]
    # Les notes héritent de la confiance de leur accord.
    assert all(n["confidence"] is not None for n in tracks["piano-rh"]["notes"])


def test_keyboard_from_corrected_chords_has_no_confidence(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))
    client.put(
        f"/audio-files/{file_id}/chords",
        json={"chords": [_chord_input(0, "maj", 0.0), _chord_input(7, "7", 2.0)]},
    )

    body = client.post(f"/audio-files/{file_id}/generate-keyboard", json={}).json()

    rh = next(t for t in body["song"]["tracks"] if t["id"] == "piano-rh")
    assert all(n["confidence"] is None for n in rh["notes"])
    assert body["low_confidence_chord_count"] == 0


def test_keyboard_can_skip_ambiguous_chords(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(CSUS2))
    client.post(f"/audio-files/{file_id}/estimate-chords", json={})

    included = client.post(f"/audio-files/{file_id}/generate-keyboard", json={}).json()
    skipped = client.post(
        f"/audio-files/{file_id}/generate-keyboard", json={"include_ambiguous": False}
    ).json()

    assert included["chord_count"] == 1 and included["low_confidence_chord_count"] == 1
    assert skipped["chord_count"] == 0 and skipped["skipped_ambiguous_count"] == 1
    assert skipped["right_hand_note_count"] == 0


def test_regenerating_the_keyboard_replaces_the_tracks_and_keeps_others(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))
    _transcribe(client, file_id, [_raw(64, 0.0), _raw(67, 0.0), _raw(60, 0.0)])
    client.put(f"/audio-files/{file_id}/chords", json={"chords": [_chord_input(0, "maj", 0.0)]})

    client.post(f"/audio-files/{file_id}/generate-keyboard", json={})
    body = client.post(f"/audio-files/{file_id}/generate-keyboard", json={}).json()

    ids = [t["id"] for t in body["song"]["tracks"]]
    assert sorted(ids) == ["guitar", "piano-lh", "piano-rh"]  # ni doublon, ni perte de la guitare


def test_keyboard_positions_are_computed_in_the_response(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path, sequence(PROGRESSION))
    client.put(
        f"/audio-files/{file_id}/chords",
        json={"chords": [_chord_input(0, "maj", 0.0), _chord_input(5, "maj", 2.0)]},
    )

    body = client.post(f"/audio-files/{file_id}/generate-keyboard", json={}).json()

    rh = next(t for t in body["song"]["tracks"] if t["id"] == "piano-rh")
    assert {n["position"]["bar"] for n in rh["notes"]} == {1, 2}
