"""Tests de `tablature/cost.py`."""

from __future__ import annotations

from guitarriff.tablature.cost import (
    DEFAULT_WEIGHTS,
    group_cost,
    position_cost,
    reference_fret_after,
)
from guitarriff.tablature.fretboard import Position


def test_open_string_has_negative_bonus_cost() -> None:
    cost = position_cost(Position(string_index=0, fret=0), previous_reference_fret=None)
    assert cost == DEFAULT_WEIGHTS.open_string_bonus


def test_higher_fret_costs_more_without_reference() -> None:
    low = position_cost(Position(string_index=0, fret=2), previous_reference_fret=None)
    high = position_cost(Position(string_index=0, fret=10), previous_reference_fret=None)
    assert high > low


def test_movement_cost_penalizes_distance_from_reference() -> None:
    close = position_cost(Position(string_index=0, fret=7), previous_reference_fret=7.0)
    far = position_cost(Position(string_index=0, fret=1), previous_reference_fret=7.0)
    assert close < far


def test_closer_but_higher_fret_can_beat_lower_but_distant_fret() -> None:
    """Cas vérifié manuellement avant ce test : avec une référence à 7.0, la
    case 7 (coût de déplacement nul) doit l'emporter sur la case 2 (coût de
    déplacement important), même si 2 < 7 en valeur absolue."""

    near_reference = position_cost(Position(string_index=1, fret=7), previous_reference_fret=7.0)
    far_but_lower = position_cost(Position(string_index=2, fret=2), previous_reference_fret=7.0)
    assert near_reference < far_but_lower


def test_group_cost_penalizes_wide_finger_span() -> None:
    narrow = group_cost(
        (Position(string_index=0, fret=5), Position(string_index=1, fret=6)),
        previous_reference_fret=None,
    )
    wide = group_cost(
        (Position(string_index=0, fret=1), Position(string_index=1, fret=15)),
        previous_reference_fret=None,
    )
    assert wide > narrow


def test_group_cost_ignores_open_strings_in_span() -> None:
    # Une corde à vide ne doit pas compter dans l'écartement des doigts.
    with_open = group_cost(
        (Position(string_index=0, fret=0), Position(string_index=1, fret=3)),
        previous_reference_fret=None,
    )
    both_pressed_same_span = group_cost(
        (Position(string_index=0, fret=0), Position(string_index=1, fret=3)),
        previous_reference_fret=None,
    )
    assert (
        with_open == both_pressed_same_span
    )  # pas de pénalité de span ajoutée par la corde à vide


def test_reference_fret_after_uses_mean_of_pressed_frets() -> None:
    ref = reference_fret_after(
        (Position(string_index=0, fret=2), Position(string_index=1, fret=4)),
        previous_reference_fret=None,
    )
    assert ref == 3.0


def test_reference_fret_after_keeps_previous_when_all_open() -> None:
    ref = reference_fret_after((Position(string_index=0, fret=0),), previous_reference_fret=5.0)
    assert ref == 5.0


def test_reference_fret_after_none_and_all_open_stays_none() -> None:
    ref = reference_fret_after((Position(string_index=0, fret=0),), previous_reference_fret=None)
    assert ref is None
