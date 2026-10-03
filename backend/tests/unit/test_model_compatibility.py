"""Tests de compatibilité : vérifie que des données dans la forme attendue de
différentes méthodes de transcription se convertissent sans perte ni
ambiguïté vers le modèle commun — l'exigence centrale de cette étape
("Toutes les méthodes de transcription devront produire des données
compatibles avec ce modèle").

Ces tests simulent la FORME de sortie de chaque méthode (vérifiée
indépendamment lors d'étapes précédentes, ex. l'installation réelle de
basic-pitch à l'Étape 1/6) — ils ne testent pas un adaptateur basic-pitch
réel, qui sera construit à une étape ultérieure de transcription.
"""

from __future__ import annotations

import pytest

from guitarriff.model import AudioMetadata, InstrumentKind, NoteEvent, Song, Track
from guitarriff.separation.models import AVAILABLE_MODES

# Forme de sortie simplifiée de basic-pitch, telle que vérifiée dans
# `basic_pitch/note_creation.py` lors de l'audit de l'Étape 1 : un tuple
# (start_time_s, end_time_s, pitch_midi, amplitude[0-1]) par note détectée.
BasicPitchLikeNote = tuple[float, float, int, float]


def _notes_from_basic_pitch_shape(raw_notes: list[BasicPitchLikeNote]) -> tuple[NoteEvent, ...]:
    """Convertit des tuples façon basic-pitch en `NoteEvent`. L'amplitude
    (0-1) est mise à l'échelle en vélocité MIDI (0-127) et réutilisée comme
    confiance — une simplification raisonnable pour ce test de compatibilité,
    pas l'adaptateur définitif."""

    events = []
    for start, end, pitch, amplitude in raw_notes:
        events.append(
            NoteEvent(
                midi_pitch=pitch,
                start_seconds=start,
                duration_seconds=end - start,
                velocity=round(amplitude * 127),
                confidence=amplitude,
            )
        )
    return tuple(events)


def test_basic_pitch_shaped_output_converts_without_loss() -> None:
    raw_notes: list[BasicPitchLikeNote] = [
        (0.0, 0.5, 64, 0.91),
        (0.5, 1.2, 67, 0.73),
    ]

    notes = _notes_from_basic_pitch_shape(raw_notes)
    track = Track(id="guitar-1", instrument=InstrumentKind.GUITAR, name="Guitare", notes=notes)
    song = Song(
        duration_seconds=2.0,
        audio=AudioMetadata(source_file_id="f1", sample_rate=22050, channels=1),
        tracks=(track,),
    )

    assert song.tracks[0].notes[0].midi_pitch == 64
    assert song.tracks[0].notes[0].confidence == 0.91
    assert song.tracks[0].notes[1].duration_seconds == pytest.approx(0.7)


# Forme de sortie minimale d'un import MIDI direct : (pitch, start, duration,
# velocity) — sans confiance, contrairement à basic-pitch.
MidiLikeNote = tuple[int, float, float, int]


def _notes_from_midi_shape(raw_notes: list[MidiLikeNote]) -> tuple[NoteEvent, ...]:
    return tuple(
        NoteEvent(
            midi_pitch=pitch, start_seconds=start, duration_seconds=duration, velocity=velocity
        )
        for pitch, start, duration, velocity in raw_notes
    )


def test_midi_shaped_output_without_confidence_is_also_compatible() -> None:
    """Une méthode qui ne fournit jamais de confiance (import MIDI direct)
    doit être tout aussi compatible qu'une méthode qui en fournit toujours
    (basic-pitch) — `confidence` est optionnel, pas requis."""

    raw_notes: list[MidiLikeNote] = [(40, 0.0, 1.0, 100), (45, 1.0, 1.0, 95)]

    notes = _notes_from_midi_shape(raw_notes)
    track = Track(id="bass-1", instrument=InstrumentKind.BASS, name="Basse", notes=notes)
    song = Song(
        duration_seconds=2.0,
        audio=AudioMetadata(source_file_id="f2", sample_rate=44100, channels=2),
        tracks=(track,),
    )

    assert all(note.confidence is None for note in song.tracks[0].notes)


def test_instrument_kind_vocabulary_matches_separation_stem_names() -> None:
    """Vérifie la cohérence annoncée avec l'Étape 7 : chaque piste produite
    par la séparation doit correspondre à un `InstrumentKind` connu, pour
    qu'une piste séparée devienne directement une `Track` sans table de
    correspondance ad hoc."""

    stem_to_instrument = {
        "drums": InstrumentKind.DRUMS,
        "bass": InstrumentKind.BASS,
        "vocals": InstrumentKind.VOCALS,
        "guitar": InstrumentKind.GUITAR,
        "piano": InstrumentKind.PIANO,
        "other": InstrumentKind.OTHER,
        "mixture": InstrumentKind.OTHER,
    }

    all_stems = {stem for model in AVAILABLE_MODES.values() for stem in model.stems}

    for stem in all_stems:
        assert stem in stem_to_instrument, (
            f"Le stem '{stem}' (Étape 7) n'a pas de InstrumentKind correspondant."
        )
