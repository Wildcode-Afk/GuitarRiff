"""Tests de `harmony/from_notes.py` : accords déduits de notes transcrites."""

from __future__ import annotations

import random

import pytest

from guitarriff.harmony.from_notes import chords_from_notes
from guitarriff.harmony.templates import POWER_CONFIDENCE
from guitarriff.model import AudioMetadata, ChordQuality, NoteEvent, Song
from guitarriff.model.chord import validate_chords_non_overlapping


def _n(pitch: int, start: float = 0.0, duration: float = 1.0, confidence: float | None = None):
    return NoteEvent(
        midi_pitch=pitch,
        start_seconds=start,
        duration_seconds=duration,
        velocity=90,
        confidence=confidence,
    )


def _one(pitches: list[int], **kwargs):
    chords = chords_from_notes(tuple(_n(p, **kwargs) for p in pitches))
    assert len(chords) == 1, [c.symbol for c in chords]
    return chords[0]


# --- Accords nets -----------------------------------------------------------


@pytest.mark.parametrize(
    ("pitches", "symbol"),
    [
        ([60, 64, 67], "C"),
        ([57, 60, 64], "Am"),
        ([43, 59, 62, 65], "G7"),
        ([48, 52, 55, 59], "Cmaj7"),
        ([50, 53, 57, 60], "Dm7"),
        ([59, 62, 65], "Bdim"),
    ],
)
def test_clear_chords_are_identified_with_full_confidence(pitches: list[int], symbol: str) -> None:
    chord = _one(pitches)
    assert chord.symbol == symbol
    assert not chord.ambiguous
    assert chord.confidence == pytest.approx(1.0)


# --- Basse et renversements : exacts avec des notes -------------------------


def test_root_position_has_inversion_zero() -> None:
    assert _one([48, 64, 67]).inversion == 0  # do grave


def test_first_inversion_is_determined_from_the_lowest_note() -> None:
    chord = _one([52, 60, 67])  # mi en bas
    assert (chord.symbol, chord.bass_pitch_class, chord.inversion) == ("C/E", 4, 1)


def test_second_inversion() -> None:
    chord = _one([43, 60, 64])
    assert (chord.symbol, chord.inversion) == ("C/G", 2)


def test_seventh_chord_third_inversion() -> None:
    chord = _one([41, 55, 59, 62])  # sol7 avec fa en bas
    assert (chord.symbol, chord.inversion) == ("G7/F", 3)


def test_bass_outside_the_chord_is_a_slash_chord_without_inversion_and_flagged() -> None:
    chord = _one([50, 60, 64, 67])  # ré en bas d'un do majeur
    assert chord.bass_pitch_class == 2
    assert chord.inversion is None
    assert chord.ambiguous
    assert chord.confidence < 0.1


# --- Ambiguïtés -------------------------------------------------------------


def test_sus2_and_sus4_equivalence_is_reported_and_bass_picks_the_reading() -> None:
    sus2 = _one([48, 50, 55])  # do ré sol, basse do
    sus4 = _one([43, 48, 50])  # sol do ré, basse sol
    assert sus2.symbol == "Csus2" and sus4.symbol == "Gsus4"
    assert sus2.ambiguous and sus4.ambiguous
    assert "Gsus4" in {a.symbol for a in sus2.alternatives}
    assert "Csus2" in {a.symbol for a in sus4.alternatives}


def test_power_chord_is_always_ambiguous_with_major_and_minor_alternatives() -> None:
    chord = _one([48, 55])
    assert chord.quality == ChordQuality.POWER
    assert chord.ambiguous
    assert chord.confidence == pytest.approx(POWER_CONFIDENCE)
    symbols = {a.symbol for a in chord.alternatives}
    assert {"C", "Cm"} <= symbols
    assert ChordQuality.POWER not in {a.quality for a in chord.alternatives}


def test_chromatic_cluster_is_flagged_because_the_label_does_not_explain_every_note() -> None:
    """Régression : un amas de 5 notes était étiqueté « D#m7/C » avec une
    confiance de 0.82 et sans ambiguïté, alors que 4 notes sur 5 seulement
    appartiennent à l'accord."""

    chord = _one([60, 61, 63, 66, 70])
    assert chord.ambiguous
    assert chord.confidence < 0.7


# --- Pas d'accord -----------------------------------------------------------


@pytest.mark.parametrize("pitches", [[60], [60, 64], [60, 65 + 1], [60, 60 + 12]])
def test_single_notes_and_non_fifth_dyads_are_not_chords(pitches: list[int]) -> None:
    assert chords_from_notes(tuple(_n(p) for p in pitches)) == ()


def test_empty_input() -> None:
    assert chords_from_notes(()) == ()


# --- Temps et durées --------------------------------------------------------


def test_onset_jitter_within_tolerance_still_forms_one_chord() -> None:
    notes = (_n(60, 0.0), _n(64, 0.02), _n(67, 0.01))
    chords = chords_from_notes(notes)
    assert [c.symbol for c in chords] == ["C"]
    assert chords[0].start_seconds == 0.0
    assert chords[0].duration_seconds == pytest.approx(1.02)


def test_successive_chords_keep_their_own_times() -> None:
    notes = tuple(_n(p, 0.0) for p in (60, 64, 67)) + tuple(_n(p, 2.0) for p in (65, 69, 72))
    chords = chords_from_notes(notes)
    assert [(c.symbol, c.start_seconds) for c in chords] == [("C", 0.0), ("F", 2.0)]


def test_sustained_chord_is_clipped_at_the_next_chord() -> None:
    notes = tuple(_n(p, 0.0, 5.0) for p in (60, 64, 67)) + tuple(
        _n(p, 2.0, 1.0) for p in (65, 69, 72)
    )
    chords = chords_from_notes(notes)
    assert chords[0].duration_seconds == pytest.approx(2.0)
    assert chords[1].duration_seconds == pytest.approx(1.0)


def test_note_confidences_lower_the_chord_confidence() -> None:
    assert _one([60, 64, 67], confidence=0.9).confidence == pytest.approx(0.9)
    assert _one([60, 64, 67], confidence=0.4).confidence == pytest.approx(0.4)


def test_chords_are_marked_as_detected_not_manual() -> None:
    assert _one([60, 64, 67]).source.value == "detected"


def test_random_notes_always_give_valid_ordered_non_overlapping_chords() -> None:
    rng = random.Random(8)
    for _ in range(200):
        notes = tuple(
            _n(rng.randint(36, 84), rng.uniform(0, 20), rng.uniform(0.1, 4.0))
            for _ in range(rng.randint(1, 25))
        )
        chords = chords_from_notes(notes)
        validate_chords_non_overlapping(chords)
        assert all(c.duration_seconds > 0 for c in chords)
        Song(
            duration_seconds=30.0,
            audio=AudioMetadata(source_file_id="f", sample_rate=22050, channels=1),
            chords=chords,
        )
