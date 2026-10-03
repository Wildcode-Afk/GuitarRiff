"""Tests de `model/note_event.py` : validation, immutabilité, sérialisation,
notes simultanées."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from guitarriff.model import InstrumentSpecificInfo, MusicalPosition, NoteEvent


def _note(**overrides: object) -> NoteEvent:
    defaults: dict[str, object] = dict(
        midi_pitch=60, start_seconds=1.0, duration_seconds=0.5, velocity=80
    )
    defaults.update(overrides)
    return NoteEvent(**defaults)  # type: ignore[arg-type]


@pytest.mark.parametrize("pitch", [0, 60, 127])
def test_accepts_valid_midi_pitch_range(pitch: int) -> None:
    assert _note(midi_pitch=pitch).midi_pitch == pitch


@pytest.mark.parametrize("pitch", [-1, 128, 200])
def test_rejects_out_of_range_midi_pitch(pitch: int) -> None:
    with pytest.raises(ValidationError):
        _note(midi_pitch=pitch)


@pytest.mark.parametrize("velocity", [-1, 128])
def test_rejects_out_of_range_velocity(velocity: int) -> None:
    with pytest.raises(ValidationError):
        _note(velocity=velocity)


def test_rejects_negative_start() -> None:
    with pytest.raises(ValidationError):
        _note(start_seconds=-0.1)


def test_rejects_zero_or_negative_duration() -> None:
    with pytest.raises(ValidationError):
        _note(duration_seconds=0.0)
    with pytest.raises(ValidationError):
        _note(duration_seconds=-0.5)


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0, None])
def test_accepts_valid_confidence_or_none(confidence: float | None) -> None:
    assert _note(confidence=confidence).confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_rejects_out_of_range_confidence(confidence: float) -> None:
    with pytest.raises(ValidationError):
        _note(confidence=confidence)


def test_is_frozen() -> None:
    note = _note()
    with pytest.raises(ValidationError):
        note.midi_pitch = 61


def test_end_seconds_computed_correctly() -> None:
    note = _note(start_seconds=1.0, duration_seconds=0.5)
    assert note.end_seconds == 1.5


def test_overlaps_detects_simultaneous_notes_on_same_track() -> None:
    chord_root = _note(midi_pitch=60, start_seconds=1.0, duration_seconds=1.0)
    chord_third = _note(midi_pitch=64, start_seconds=1.0, duration_seconds=1.0)
    chord_fifth = _note(midi_pitch=67, start_seconds=1.2, duration_seconds=0.5)

    assert chord_root.overlaps(chord_third) is True
    assert chord_root.overlaps(chord_fifth) is True


def test_overlaps_false_for_sequential_notes() -> None:
    first = _note(start_seconds=0.0, duration_seconds=0.5)
    second = _note(start_seconds=0.5, duration_seconds=0.5)
    assert first.overlaps(second) is False


def test_with_position_returns_new_instance_without_mutating_original() -> None:
    note = _note()
    position = MusicalPosition(bar=2, beat=3.0)

    updated = note.with_position(position)

    assert note.position is None
    assert updated.position == position
    assert updated is not note


def test_instrument_info_requires_string_and_fret_together() -> None:
    with pytest.raises(ValidationError):
        InstrumentSpecificInfo(string_index=0, fret=None)
    with pytest.raises(ValidationError):
        InstrumentSpecificInfo(string_index=None, fret=3)
    # Les deux absents, ou les deux présents, sont valides.
    InstrumentSpecificInfo(string_index=None, fret=None)
    InstrumentSpecificInfo(string_index=0, fret=3)


def test_serialization_round_trip() -> None:
    note = _note(
        midi_pitch=64,
        confidence=0.87,
        position=MusicalPosition(bar=1, beat=1.0),
        instrument_info=InstrumentSpecificInfo(string_index=1, fret=2),
    )

    payload = note.model_dump_json()
    restored = NoteEvent.model_validate_json(payload)

    assert restored == note


def test_serialization_omits_nothing_important() -> None:
    note = _note(confidence=0.5)
    data = note.model_dump()
    assert data["midi_pitch"] == 60
    assert data["confidence"] == 0.5
    assert "position" in data
    assert "instrument_info" in data
