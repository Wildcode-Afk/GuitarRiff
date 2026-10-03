"""Tests de `model/rhythm_event.py` — événements de batterie."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from guitarriff.model import DrumPiece, RhythmEvent


def test_accepts_known_drum_piece() -> None:
    event = RhythmEvent(
        drum_piece=DrumPiece.KICK, start_seconds=0.0, duration_seconds=0.1, velocity=100
    )
    assert event.drum_piece == DrumPiece.KICK


def test_rejects_unknown_drum_piece_string() -> None:
    with pytest.raises(ValidationError):
        RhythmEvent(drum_piece="triangle", start_seconds=0.0, duration_seconds=0.1, velocity=100)  # type: ignore[arg-type]


def test_zero_duration_is_valid_for_an_instant_hit() -> None:
    # Contrairement à NoteEvent, une durée nulle est légitime pour un coup de
    # batterie instantané.
    event = RhythmEvent(
        drum_piece=DrumPiece.SNARE, start_seconds=1.0, duration_seconds=0.0, velocity=90
    )
    assert event.duration_seconds == 0.0
    assert event.end_seconds == 1.0


def test_rejects_negative_duration() -> None:
    with pytest.raises(ValidationError):
        RhythmEvent(
            drum_piece=DrumPiece.SNARE, start_seconds=0.0, duration_seconds=-0.1, velocity=90
        )


def test_rejects_negative_start() -> None:
    with pytest.raises(ValidationError):
        RhythmEvent(
            drum_piece=DrumPiece.SNARE, start_seconds=-0.1, duration_seconds=0.0, velocity=90
        )


def test_is_frozen() -> None:
    event = RhythmEvent(
        drum_piece=DrumPiece.HIHAT_CLOSED, start_seconds=0.0, duration_seconds=0.0, velocity=70
    )
    with pytest.raises(ValidationError):
        event.velocity = 127


def test_serialization_round_trip() -> None:
    event = RhythmEvent(
        drum_piece=DrumPiece.CRASH,
        start_seconds=3.0,
        duration_seconds=0.0,
        velocity=110,
        confidence=0.6,
    )
    restored = RhythmEvent.model_validate_json(event.model_dump_json())
    assert restored == event
