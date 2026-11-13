"""Tests de `harmony/templates.py` : classement, ambiguïtés inévitables,
rôle de la basse, confiance."""

from __future__ import annotations

import numpy as np
import pytest

from guitarriff.harmony.templates import (
    ALL_QUALITIES,
    AMBIGUITY_MARGIN,
    AUDIO_QUALITIES,
    BASS_ROOT_BONUS,
    FULL_CONFIDENCE_MARGIN,
    assess,
    rank_chords,
)
from guitarriff.model import ChordQuality
from guitarriff.model.chord import CHORD_INTERVALS

EQUIVALENT = {ChordQuality.AUGMENTED, ChordQuality.SUS2, ChordQuality.SUS4}


def _vector(pitch_classes: list[int]) -> np.ndarray:
    vector = np.zeros(12)
    vector[pitch_classes] = 1.0
    return vector


def _exact(root: int, quality: ChordQuality) -> np.ndarray:
    return _vector([(root + i) % 12 for i in CHORD_INTERVALS[quality]])


@pytest.mark.parametrize("quality", [q for q in AUDIO_QUALITIES if q not in EQUIVALENT])
@pytest.mark.parametrize("root", range(12))
def test_exact_pitch_classes_rank_the_right_chord_first(root: int, quality: ChordQuality) -> None:
    ranked = rank_chords(_exact(root, quality))
    assert (ranked[0].root_pitch_class, ranked[0].quality) == (root, quality)
    assert ranked[0].score == pytest.approx(1.0)


@pytest.mark.parametrize("quality", [q for q in AUDIO_QUALITIES if q not in EQUIVALENT])
def test_exact_chord_is_not_ambiguous_and_fully_confident(quality: ChordQuality) -> None:
    result = assess(rank_chords(_exact(0, quality)))
    assert result is not None
    assert not result.ambiguous
    assert result.confidence == pytest.approx(1.0)


def test_confidence_margin_matches_triad_versus_seventh_geometry() -> None:
    """La marge d'une triade exacte face à l'accord de septième correspondant est
    1 - sqrt(3/4) = 0.134 : c'est ce qui justifie FULL_CONFIDENCE_MARGIN = 0.13."""

    result = assess(rank_chords(_exact(0, ChordQuality.MAJOR)))
    assert result.margin == pytest.approx(1 - np.sqrt(0.75))
    assert result.margin >= FULL_CONFIDENCE_MARGIN


# --- Ambiguïtés inévitables -------------------------------------------------


def test_sus2_and_sus4_with_same_notes_are_flagged_ambiguous_with_equivalent_listed() -> None:
    result = assess(rank_chords(_exact(0, ChordQuality.SUS2)))  # C D G == Gsus4
    assert result.ambiguous
    assert {c.symbol for c in (result.best, *result.alternatives)} >= {"Csus2", "Gsus4"}


def test_augmented_chord_lists_all_three_equivalent_roots() -> None:
    result = assess(rank_chords(_exact(0, ChordQuality.AUGMENTED)))
    assert result.ambiguous
    assert {c.symbol for c in (result.best, *result.alternatives)} == {"Caug", "Eaug", "G#aug"}


def test_ambiguous_chord_has_almost_no_confidence() -> None:
    result = assess(rank_chords(_exact(0, ChordQuality.SUS2)))
    assert result.confidence < 0.01


def test_diminished_triad_is_a_subset_of_a_dominant_seventh() -> None:
    ranked = rank_chords(_exact(0, ChordQuality.DIMINISHED))
    assert ranked[0].symbol == "Cdim"
    assert "G#7" in {c.symbol for c in ranked[1:4]}  # C dim ⊂ G#7 (sans sa fondamentale)


# --- Basse ------------------------------------------------------------------


def test_bass_breaks_ties_but_never_hides_the_ambiguity() -> None:
    vector = _exact(0, ChordQuality.SUS2)  # Csus2 == Gsus4
    with_c_bass = assess(rank_chords(vector, bass_pitch_class=0))
    with_g_bass = assess(rank_chords(vector, bass_pitch_class=7))

    assert with_c_bass.best.symbol == "Csus2"
    assert with_g_bass.best.symbol == "Gsus4"
    assert with_c_bass.ambiguous and with_g_bass.ambiguous  # le doute reste affiché


def test_returned_scores_are_raw_similarities_not_bonused() -> None:
    vector = _exact(0, ChordQuality.MAJOR)
    plain = {(c.root_pitch_class, c.quality): c.score for c in rank_chords(vector, limit=200)}
    bassed = {
        (c.root_pitch_class, c.quality): c.score for c in rank_chords(vector, bass_pitch_class=0)
    }
    for key, score in bassed.items():
        assert score == pytest.approx(plain[key])


def test_bass_on_the_root_does_not_lower_the_confidence_of_an_exact_triad() -> None:
    """Régression : le bonus de basse s'ajoutait aux concurrents de même
    fondamentale (C7, Cmaj7) et rétrécissait la marge, d'où une confiance de 0.8
    en position fondamentale contre 1.0 en renversement."""

    root_position = assess(rank_chords(_exact(0, ChordQuality.MAJOR), bass_pitch_class=0))
    inversion = assess(rank_chords(_exact(0, ChordQuality.MAJOR), bass_pitch_class=4))
    assert root_position.confidence == pytest.approx(inversion.confidence)
    assert root_position.confidence == pytest.approx(1.0)


def test_bass_bonus_is_smaller_than_the_ambiguity_margin() -> None:
    assert BASS_ROOT_BONUS < AMBIGUITY_MARGIN


# --- Cas limites ------------------------------------------------------------


def test_zero_vector_yields_no_ranking() -> None:
    assert rank_chords(np.zeros(12)) == []
    assert assess([]) is None


def test_power_chord_only_ranks_when_explicitly_allowed() -> None:
    vector = _vector([0, 7])
    assert ChordQuality.POWER not in {
        c.quality for c in rank_chords(vector, qualities=AUDIO_QUALITIES)
    }
    assert rank_chords(vector, qualities=ALL_QUALITIES)[0].quality == ChordQuality.POWER


def test_scores_stay_within_unit_interval() -> None:
    rng = np.random.default_rng(0)
    for _ in range(50):
        for candidate in rank_chords(rng.random(12), bass_pitch_class=3):
            assert 0.0 <= candidate.score <= 1.0
