"""Tests du modèle d'accords (`model/chord.py`) et de son intégration au `Song`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from guitarriff.model import (
    AudioMetadata,
    ChordCandidate,
    ChordEvent,
    ChordQuality,
    EstimationSource,
    MusicalPosition,
    Song,
    TempoChange,
)
from guitarriff.model.chord import (
    CHORD_INTERVALS,
    chord_pitch_classes,
    chord_symbol,
    validate_chords_non_overlapping,
)


def _chord(root=0, quality=ChordQuality.MAJOR, start=0.0, duration=2.0, **kwargs) -> ChordEvent:
    return ChordEvent(
        root_pitch_class=root,
        quality=quality,
        start_seconds=start,
        duration_seconds=duration,
        **kwargs,
    )


def _song(**kwargs) -> Song:
    return Song(
        duration_seconds=20.0,
        audio=AudioMetadata(source_file_id="f1", sample_rate=22050, channels=1),
        **kwargs,
    )


# --- Représentation ---------------------------------------------------------


@pytest.mark.parametrize(
    ("root", "quality", "expected"),
    [
        (0, ChordQuality.MAJOR, "C"),
        (9, ChordQuality.MINOR, "Am"),
        (7, ChordQuality.DOMINANT_7, "G7"),
        (0, ChordQuality.MAJOR_7, "Cmaj7"),
        (2, ChordQuality.MINOR_7, "Dm7"),
        (6, ChordQuality.DIMINISHED, "F#dim"),
        (8, ChordQuality.AUGMENTED, "G#aug"),
        (0, ChordQuality.SUS2, "Csus2"),
        (7, ChordQuality.SUS4, "Gsus4"),
        (0, ChordQuality.POWER, "C5"),
        (10, ChordQuality.MAJOR, "A#"),
    ],
)
def test_chord_symbol(root: int, quality: ChordQuality, expected: str) -> None:
    assert chord_symbol(root, quality) == expected


def test_symbol_shows_slash_bass_only_when_different_from_root() -> None:
    assert _chord(0, bass_pitch_class=4).symbol == "C/E"
    assert _chord(0, bass_pitch_class=0).symbol == "C"
    assert _chord(0).symbol == "C"


def test_pitch_classes_are_ordered_by_degree() -> None:
    assert chord_pitch_classes(0, ChordQuality.MAJOR) == (0, 4, 7)
    assert chord_pitch_classes(7, ChordQuality.DOMINANT_7) == (7, 11, 2, 5)
    assert chord_pitch_classes(9, ChordQuality.MINOR) == (9, 0, 4)


def test_every_quality_has_intervals_and_symbol() -> None:
    for quality in ChordQuality:
        assert quality in CHORD_INTERVALS
        assert chord_symbol(0, quality)


# --- Renversements ----------------------------------------------------------


@pytest.mark.parametrize(
    ("bass", "expected_inversion"),
    [(0, 0), (4, 1), (7, 2), (None, None), (2, None)],  # 2 (ré) n'est pas une note de do majeur
)
def test_inversion_from_bass(bass: int | None, expected_inversion: int | None) -> None:
    assert _chord(0, bass_pitch_class=bass).inversion == expected_inversion


def test_seventh_chord_third_inversion() -> None:
    assert _chord(7, ChordQuality.DOMINANT_7, bass_pitch_class=5).inversion == 3  # G7/F


def test_power_chord_fifth_in_bass_is_first_inversion() -> None:
    assert _chord(0, ChordQuality.POWER, bass_pitch_class=7).inversion == 1


# --- Validation -------------------------------------------------------------


@pytest.mark.parametrize("field", ["root_pitch_class", "bass_pitch_class"])
@pytest.mark.parametrize("value", [-1, 12])
def test_pitch_class_out_of_range_rejected(field: str, value: int) -> None:
    data = {
        "root_pitch_class": 0,
        "quality": ChordQuality.MAJOR,
        "start_seconds": 0.0,
        "duration_seconds": 1.0,
    }
    data[field] = value
    with pytest.raises(ValidationError):
        ChordEvent(**data)


def test_duration_must_be_positive_and_start_non_negative() -> None:
    with pytest.raises(ValidationError):
        _chord(duration=0.0)
    with pytest.raises(ValidationError):
        _chord(start=-0.1)


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_confidence_out_of_range_rejected(confidence: float) -> None:
    with pytest.raises(ValidationError):
        _chord(confidence=confidence)


def test_manual_chord_cannot_carry_confidence_ambiguity_or_alternatives() -> None:
    manual = {"source": EstimationSource.MANUAL}
    _chord(**manual)  # valide
    with pytest.raises(ValidationError):
        _chord(confidence=0.9, **manual)
    with pytest.raises(ValidationError):
        _chord(ambiguous=True, **manual)
    with pytest.raises(ValidationError):
        _chord(
            alternatives=(
                ChordCandidate(root_pitch_class=9, quality=ChordQuality.MINOR, score=0.8),
            ),
            **manual,
        )


def test_detected_chord_may_carry_uncertainty() -> None:
    chord = _chord(
        confidence=0.2,
        ambiguous=True,
        alternatives=(ChordCandidate(root_pitch_class=9, quality=ChordQuality.MINOR, score=0.8),),
    )
    assert chord.alternatives[0].symbol == "Am"


def test_chord_is_frozen_and_with_position_returns_a_copy() -> None:
    chord = _chord()
    with pytest.raises(ValidationError):
        chord.root_pitch_class = 5
    positioned = chord.with_position(MusicalPosition(bar=2, beat=1.0))
    assert chord.position is None and positioned.position == MusicalPosition(bar=2, beat=1.0)


def test_end_seconds() -> None:
    assert _chord(start=1.5, duration=2.0).end_seconds == 3.5


# --- Non-chevauchement ------------------------------------------------------


def test_adjacent_chords_are_valid_even_with_float_rounding() -> None:
    first = _chord(0, start=0.0, duration=0.1 + 0.2)
    second = _chord(5, start=0.30000000000000004 + 1e-9, duration=1.0)
    validate_chords_non_overlapping((first, second))


def test_gaps_between_chords_are_valid_they_mean_no_chord() -> None:
    validate_chords_non_overlapping((_chord(0, start=0.0), _chord(5, start=10.0)))


def test_overlap_and_disorder_are_rejected() -> None:
    with pytest.raises(ValueError, match="chevaucher"):
        validate_chords_non_overlapping((_chord(0, start=0.0, duration=3.0), _chord(5, start=2.0)))
    with pytest.raises(ValueError, match="trié"):
        validate_chords_non_overlapping((_chord(0, start=5.0), _chord(5, start=0.0)))


# --- Intégration au Song ----------------------------------------------------


def test_song_has_no_chords_by_default() -> None:
    assert _song().chords == ()


def test_song_rejects_overlapping_chords() -> None:
    with pytest.raises(ValidationError):
        _song(chords=(_chord(0, start=0.0, duration=3.0), _chord(5, start=2.0)))


def test_song_computes_chord_positions_without_mutating_the_original() -> None:
    song = _song(chords=(_chord(0, start=0.0), _chord(5, start=2.0), _chord(7, start=5.0)))

    computed = song.with_computed_positions()

    # 120 BPM en 4/4 : un temps = 0.5 s, une mesure = 2 s. 5.0 s = début de la
    # mesure 3 (4.0 s) + 1.0 s = 2 temps plus loin, donc le temps 3.
    assert [(c.position.bar, c.position.beat) for c in computed.chords] == [
        (1, 1.0),
        (2, 1.0),
        (3, 3.0),
    ]
    assert all(c.position is None for c in song.chords)


def test_chord_positions_follow_the_tempo_map() -> None:
    song = _song(
        chords=(_chord(0, start=0.0), _chord(5, start=4.0)),
        tempo_changes=(TempoChange(time_seconds=0.0, bpm=60.0),),
    )
    # 60 BPM en 4/4 : une mesure = 4 s.
    assert song.with_computed_positions().chords[1].position.bar == 2


def test_song_with_chords_survives_json_round_trip() -> None:
    song = _song(
        chords=(
            _chord(0, confidence=0.9, bass_pitch_class=4),
            _chord(
                9,
                ChordQuality.MINOR,
                start=2.0,
                confidence=0.3,
                ambiguous=True,
                alternatives=(
                    ChordCandidate(root_pitch_class=0, quality=ChordQuality.MAJOR_7, score=0.9),
                ),
            ),
            _chord(7, ChordQuality.DOMINANT_7, start=4.0, source=EstimationSource.MANUAL),
        )
    )

    restored = Song.model_validate_json(song.model_dump_json())

    assert restored == song
    assert restored.chords[0].inversion == 1


def test_song_saved_before_chords_existed_still_loads() -> None:
    legacy = {
        "id": "s1",
        "duration_seconds": 10.0,
        "audio": {"source_file_id": "f1", "sample_rate": 22050, "channels": 1},
    }
    assert Song.model_validate(legacy).chords == ()
