"""Tests de `model/position.py` — scénarios vérifiés à la main (voir
commentaires), pas seulement "le code tourne sans erreur"."""

from __future__ import annotations

import pytest

from guitarriff.model import TempoChange, TimeSignatureChange
from guitarriff.model.position import compute_position

CONSTANT_120BPM_4_4 = (
    (TempoChange(time_seconds=0.0, bpm=120.0),),
    (TimeSignatureChange(time_seconds=0.0, numerator=4, denominator=4),),
)


def test_time_zero_is_bar_one_beat_one() -> None:
    tempo, sig = CONSTANT_120BPM_4_4
    position = compute_position(0.0, tempo, sig)
    assert (position.bar, position.beat) == (1, 1.0)


def test_constant_tempo_within_first_bar() -> None:
    # 120 bpm => 0.5s par temps. À 0.5s, on est au temps 2 de la mesure 1.
    tempo, sig = CONSTANT_120BPM_4_4
    position = compute_position(0.5, tempo, sig)
    assert (position.bar, position.beat) == (1, 2.0)


def test_constant_tempo_crosses_bar_boundary() -> None:
    # 1 mesure de 4/4 à 120bpm = 4 * 0.5s = 2.0s => début de la mesure 2.
    tempo, sig = CONSTANT_120BPM_4_4
    position = compute_position(2.0, tempo, sig)
    assert (position.bar, position.beat) == (2, 1.0)


def test_constant_tempo_several_bars() -> None:
    tempo, sig = CONSTANT_120BPM_4_4
    position = compute_position(4.0, tempo, sig)
    assert (position.bar, position.beat) == (3, 1.0)


def test_tempo_change_mid_stream_affects_subsequent_beats() -> None:
    # 120bpm jusqu'à t=1.0s (2 temps écoulés => temps 3 de la mesure 1),
    # puis 60bpm (1s/temps) : à t=1.5s, +0.5 temps => temps 3.5.
    tempo = (TempoChange(time_seconds=0.0, bpm=120.0), TempoChange(time_seconds=1.0, bpm=60.0))
    sig = (TimeSignatureChange(time_seconds=0.0, numerator=4, denominator=4),)

    at_one = compute_position(1.0, tempo, sig)
    assert (at_one.bar, at_one.beat) == (1, 3.0)

    at_one_point_five = compute_position(1.5, tempo, sig)
    assert (at_one_point_five.bar, at_one_point_five.beat) == (1, 3.5)


def test_time_signature_change_resets_bar_length() -> None:
    # 2 mesures de 4/4 à 120bpm = 4.0s, puis passage en 3/4 à t=4.0s.
    tempo = (TempoChange(time_seconds=0.0, bpm=120.0),)
    sig = (
        TimeSignatureChange(time_seconds=0.0, numerator=4, denominator=4),
        TimeSignatureChange(time_seconds=4.0, numerator=3, denominator=4),
    )

    at_four = compute_position(4.0, tempo, sig)
    assert (at_four.bar, at_four.beat) == (3, 1.0)

    # +1 temps en 3/4 à 120bpm (0.5s/temps) => t=4.5s => mesure 3 temps 2.
    at_four_point_five = compute_position(4.5, tempo, sig)
    assert (at_four_point_five.bar, at_four_point_five.beat) == (3, 2.0)


def test_compound_meter_6_8_uses_eighth_note_beats() -> None:
    # 6/8 à 120bpm (noire=0.5s) => croche = 0.25s/temps, 6 temps/mesure.
    tempo = (TempoChange(time_seconds=0.0, bpm=120.0),)
    sig = (TimeSignatureChange(time_seconds=0.0, numerator=6, denominator=8),)

    position = compute_position(6 * 0.25, tempo, sig)
    assert (position.bar, position.beat) == (2, 1.0)


def test_negative_time_raises() -> None:
    tempo, sig = CONSTANT_120BPM_4_4
    with pytest.raises(ValueError, match="positif"):
        compute_position(-1.0, tempo, sig)


def test_missing_tempo_at_zero_raises() -> None:
    tempo = (TempoChange(time_seconds=1.0, bpm=120.0),)
    sig = (TimeSignatureChange(time_seconds=0.0, numerator=4, denominator=4),)
    with pytest.raises(ValueError, match="tempo_changes"):
        compute_position(2.0, tempo, sig)


def test_missing_time_signature_at_zero_raises() -> None:
    tempo = (TempoChange(time_seconds=0.0, bpm=120.0),)
    sig = (TimeSignatureChange(time_seconds=1.0, numerator=4, denominator=4),)
    with pytest.raises(ValueError, match="time_signature_changes"):
        compute_position(2.0, tempo, sig)
