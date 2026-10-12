"""Tests de `tablature/fretboard.py` — accordages différents, capodastre,
limite de cases, configuration du nombre de cordes."""

from __future__ import annotations

import pytest

from guitarriff.tablature.fretboard import (
    STANDARD_BASS_TUNING,
    STANDARD_GUITAR_TUNING,
    FretboardConfig,
    candidate_positions,
)


def test_standard_guitar_tuning_has_six_strings() -> None:
    assert len(STANDARD_GUITAR_TUNING) == 6
    assert STANDARD_GUITAR_TUNING[0] == 40  # E2


def test_standard_bass_tuning_has_four_strings() -> None:
    assert len(STANDARD_BASS_TUNING) == 4
    assert STANDARD_BASS_TUNING[0] == 28  # E1


def test_candidate_positions_finds_all_valid_strings() -> None:
    config = FretboardConfig(tuning=STANDARD_GUITAR_TUNING)
    # Mi aigu (midi 64) : corde à vide E4, ou plus haut sur les autres cordes.
    candidates = candidate_positions(64, config)
    strings = {c.string_index for c in candidates}
    assert 5 in strings  # E4 à vide
    assert all(0 <= c.fret <= config.max_fret for c in candidates)


def test_candidate_positions_empty_when_pitch_too_low() -> None:
    config = FretboardConfig(tuning=STANDARD_GUITAR_TUNING)
    assert candidate_positions(20, config) == ()


def test_candidate_positions_empty_when_pitch_too_high_for_max_fret() -> None:
    config = FretboardConfig(tuning=STANDARD_GUITAR_TUNING, max_fret=12)
    # E4 (64) + 12 cases = 76, donc 77 est hors de portée avec max_fret=12.
    assert candidate_positions(77, config) == ()
    assert candidate_positions(76, config) != ()


def test_capo_raises_the_lowest_reachable_pitch() -> None:
    config_no_capo = FretboardConfig(tuning=STANDARD_GUITAR_TUNING, capo_fret=0)
    config_capo_2 = FretboardConfig(tuning=STANDARD_GUITAR_TUNING, capo_fret=2)

    # 41 est jouable sans capo (corde E2, case 1) mais plus avec capo=2.
    assert candidate_positions(41, config_no_capo) != ()
    assert candidate_positions(41, config_capo_2) == ()

    # 44 nécessite case 2 avec capo=2 (= case 4 réelle), cohérent.
    candidates = candidate_positions(44, config_capo_2)
    assert any(c.string_index == 0 and c.fret == 2 for c in candidates)


def test_fret_is_relative_to_capo() -> None:
    config = FretboardConfig(tuning=STANDARD_GUITAR_TUNING, capo_fret=3)
    # Avec capo=3, jouer la corde E2 à vide (case relative 0) donne 40+3=43.
    candidates = candidate_positions(43, config)
    assert any(c.string_index == 0 and c.fret == 0 for c in candidates)


def test_seven_string_guitar_tuning_supported() -> None:
    seven_string = (35, 40, 45, 50, 55, 59, 64)  # B1 E2 A2 D3 G3 B3 E4
    config = FretboardConfig(tuning=seven_string)
    assert config.n_strings == 7
    candidates = candidate_positions(35, config)
    assert any(c.string_index == 0 and c.fret == 0 for c in candidates)


def test_four_string_bass_configurable() -> None:
    config = FretboardConfig(tuning=STANDARD_BASS_TUNING)
    assert config.n_strings == 4


@pytest.mark.parametrize("bad_tuning", [(), (200,), (-1, 40)])
def test_rejects_invalid_tuning(bad_tuning: tuple[int, ...]) -> None:
    with pytest.raises(ValueError):
        FretboardConfig(tuning=bad_tuning)


def test_rejects_negative_capo() -> None:
    with pytest.raises(ValueError):
        FretboardConfig(tuning=STANDARD_GUITAR_TUNING, capo_fret=-1)


def test_rejects_max_fret_below_capo() -> None:
    with pytest.raises(ValueError):
        FretboardConfig(tuning=STANDARD_GUITAR_TUNING, capo_fret=10, max_fret=5)


def test_max_relative_fret_accounts_for_capo() -> None:
    config = FretboardConfig(tuning=STANDARD_GUITAR_TUNING, capo_fret=3, max_fret=24)
    assert config.max_relative_fret == 21
