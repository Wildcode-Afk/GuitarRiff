"""Tests de `transcription/converter.py` — fonction pure, sorties simulées."""

from __future__ import annotations

from guitarriff.transcription.basic_pitch_adapter import RawNoteEvent
from guitarriff.transcription.converter import raw_notes_to_note_events


def test_converts_basic_fields_correctly() -> None:
    raw = [RawNoteEvent(start_seconds=1.0, end_seconds=1.5, midi_pitch=69, amplitude=0.6)]

    notes = raw_notes_to_note_events(raw)

    assert len(notes) == 1
    note = notes[0]
    assert note.midi_pitch == 69
    assert note.start_seconds == 1.0
    assert note.duration_seconds == 0.5
    assert note.velocity == round(0.6 * 127)
    assert note.confidence == 0.6


def test_empty_input_returns_empty_tuple() -> None:
    assert raw_notes_to_note_events([]) == ()


def test_amplitude_is_clamped_to_valid_range() -> None:
    raw = [
        RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=60, amplitude=1.2),
        RawNoteEvent(start_seconds=1.0, end_seconds=1.5, midi_pitch=60, amplitude=-0.3),
    ]

    notes = raw_notes_to_note_events(raw)

    assert notes[0].confidence == 1.0
    assert notes[0].velocity == 127
    assert notes[1].confidence == 0.0
    assert notes[1].velocity == 0


def test_zero_or_negative_duration_notes_are_dropped() -> None:
    raw = [
        RawNoteEvent(
            start_seconds=1.0, end_seconds=1.0, midi_pitch=60, amplitude=0.5
        ),  # durée nulle
        RawNoteEvent(
            start_seconds=2.0, end_seconds=1.9, midi_pitch=60, amplitude=0.5
        ),  # durée négative
        RawNoteEvent(start_seconds=3.0, end_seconds=3.5, midi_pitch=60, amplitude=0.5),  # valide
    ]

    notes = raw_notes_to_note_events(raw)

    assert len(notes) == 1
    assert notes[0].start_seconds == 3.0


def test_multiple_simultaneous_notes_all_preserved() -> None:
    raw = [
        RawNoteEvent(start_seconds=0.0, end_seconds=1.0, midi_pitch=60, amplitude=0.8),
        RawNoteEvent(start_seconds=0.0, end_seconds=1.0, midi_pitch=64, amplitude=0.7),
        RawNoteEvent(start_seconds=0.0, end_seconds=1.0, midi_pitch=67, amplitude=0.75),
    ]

    notes = raw_notes_to_note_events(raw)

    assert len(notes) == 3
    assert {n.midi_pitch for n in notes} == {60, 64, 67}
