"""Tests de `model/tempo.py`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from guitarriff.model import TempoChange, TimeSignatureChange


def test_tempo_change_accepts_valid_bpm() -> None:
    tc = TempoChange(time_seconds=0.0, bpm=120.0)
    assert tc.bpm == 120.0


def test_tempo_change_rejects_zero_or_negative_bpm() -> None:
    with pytest.raises(ValidationError):
        TempoChange(time_seconds=0.0, bpm=0.0)
    with pytest.raises(ValidationError):
        TempoChange(time_seconds=0.0, bpm=-10.0)


def test_tempo_change_rejects_negative_time() -> None:
    with pytest.raises(ValidationError):
        TempoChange(time_seconds=-1.0, bpm=120.0)


def test_tempo_change_is_frozen() -> None:
    tc = TempoChange(time_seconds=0.0, bpm=120.0)
    with pytest.raises(ValidationError):
        tc.bpm = 100.0


@pytest.mark.parametrize("denominator", [1, 2, 4, 8, 16, 32, 64])
def test_time_signature_accepts_power_of_two_denominators(denominator: int) -> None:
    ts = TimeSignatureChange(time_seconds=0.0, numerator=4, denominator=denominator)
    assert ts.denominator == denominator


@pytest.mark.parametrize("denominator", [0, 3, 5, 6, 7, 9, 10, 12, -4])
def test_time_signature_rejects_non_power_of_two_denominators(denominator: int) -> None:
    with pytest.raises(ValidationError):
        TimeSignatureChange(time_seconds=0.0, numerator=4, denominator=denominator)


def test_time_signature_rejects_zero_numerator() -> None:
    with pytest.raises(ValidationError):
        TimeSignatureChange(time_seconds=0.0, numerator=0, denominator=4)


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected_factor"),
    [(4, 4, 1.0), (3, 4, 1.0), (6, 8, 0.5), (7, 8, 0.5), (4, 2, 2.0)],
)
def test_beat_seconds_factor(numerator: int, denominator: int, expected_factor: float) -> None:
    ts = TimeSignatureChange(time_seconds=0.0, numerator=numerator, denominator=denominator)
    assert ts.beat_seconds_factor == expected_factor
