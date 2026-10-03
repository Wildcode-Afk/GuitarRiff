"""Tests de `model/track.py`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from guitarriff.model import Clef, InstrumentKind, NoteEvent, Track, TrackDisplaySettings

STANDARD_GUITAR_TUNING = (40, 45, 50, 55, 59, 64)


def test_minimal_track_has_empty_notes_and_rhythm_events_by_default() -> None:
    track = Track(id="t1", instrument=InstrumentKind.GUITAR, name="Guitare")
    assert track.notes == ()
    assert track.rhythm_events == ()
    assert track.tuning is None


def test_accepts_standard_guitar_tuning() -> None:
    track = Track(
        id="t1", instrument=InstrumentKind.GUITAR, name="Guitare", tuning=STANDARD_GUITAR_TUNING
    )
    assert track.tuning == STANDARD_GUITAR_TUNING


def test_rejects_empty_tuning_tuple() -> None:
    with pytest.raises(ValidationError):
        Track(id="t1", instrument=InstrumentKind.GUITAR, name="Guitare", tuning=())


def test_rejects_out_of_range_tuning_note() -> None:
    with pytest.raises(ValidationError):
        Track(id="t1", instrument=InstrumentKind.GUITAR, name="Guitare", tuning=(40, 200))


def test_display_settings_default_values() -> None:
    track = Track(id="t1", instrument=InstrumentKind.BASS, name="Basse")
    assert track.display.clef == Clef.TREBLE
    assert track.display.visible is True
    assert track.display.color.startswith("#")


def test_display_accepts_valid_hex_color() -> None:
    settings = TrackDisplaySettings(color="#ff00aa")
    assert settings.color == "#ff00aa"


@pytest.mark.parametrize("bad_color", ["blue", "#fff", "#gggggg", "123456", "#12345"])
def test_display_rejects_invalid_hex_color(bad_color: str) -> None:
    with pytest.raises(ValidationError):
        TrackDisplaySettings(color=bad_color)


def test_track_holds_notes_tuple_surviving_serialization() -> None:
    notes = (
        NoteEvent(midi_pitch=40, start_seconds=0.0, duration_seconds=1.0, velocity=90),
        NoteEvent(midi_pitch=45, start_seconds=1.0, duration_seconds=1.0, velocity=90),
    )
    track = Track(id="t1", instrument=InstrumentKind.BASS, name="Basse", notes=notes)

    restored = Track.model_validate_json(track.model_dump_json())

    assert isinstance(restored.notes, tuple)
    assert restored.notes == notes


def test_track_is_frozen() -> None:
    track = Track(id="t1", instrument=InstrumentKind.GUITAR, name="Guitare")
    with pytest.raises(ValidationError):
        track.name = "Autre nom"
