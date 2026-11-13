"""Tests de `harmony/analyzer.py` sur des **signaux synthétiques** à accords
connus (voir `synth_audio.py`) : accords nets, accords ambigus, basse et
renversements, enchaînements, absence d'accord, bruit.

Ces tests décrivent le comportement sur le **meilleur cas** (timbres propres,
2 s par accord) : ils ne disent rien de la précision sur de vrais
enregistrements, qui n'a pas été mesurée."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

from guitarriff.errors import ChordAnalysisError, ChordAnalysisTimeoutError
from guitarriff.harmony import analyzer
from guitarriff.harmony.analyzer import _analyze, estimate_chords
from guitarriff.harmony.templates import POWER_CONFIDENCE
from guitarriff.model import ChordQuality
from guitarriff.model.chord import (
    CHORD_INTERVALS,
    chord_pitch_classes,
    validate_chords_non_overlapping,
)
from tests.unit.synth_audio import SR, sequence, voicing

CLEAR_QUALITIES = [
    ChordQuality.MAJOR,
    ChordQuality.MINOR,
    ChordQuality.DOMINANT_7,
    ChordQuality.DIMINISHED,
    ChordQuality.MAJOR_7,
    ChordQuality.MINOR_7,
]
EQUIVALENT_QUALITIES = [ChordQuality.AUGMENTED, ChordQuality.SUS2, ChordQuality.SUS4]


def _analyze_chord(midis: list[int], seconds: float = 2.0):
    return _analyze(sequence([(midis, seconds)]), SR).chords


# --- Accords nets -----------------------------------------------------------


@pytest.mark.parametrize("root", range(12))
@pytest.mark.parametrize("quality", [ChordQuality.MAJOR, ChordQuality.MINOR])
def test_major_and_minor_triads_are_found_on_every_root(root: int, quality: ChordQuality) -> None:
    chords = _analyze_chord(voicing(root, CHORD_INTERVALS[quality]))
    assert len(chords) == 1
    chord = chords[0]
    assert (chord.root_pitch_class, chord.quality) == (root, quality)
    assert not chord.ambiguous
    assert chord.confidence >= 0.85  # mesuré : 0.88 à 0.99 selon la racine
    assert chord.start_seconds == pytest.approx(0.0, abs=0.1)
    assert chord.duration_seconds == pytest.approx(2.0, abs=0.15)


@pytest.mark.parametrize("root", [0, 3, 6, 9])
@pytest.mark.parametrize(
    "quality",
    [ChordQuality.DOMINANT_7, ChordQuality.DIMINISHED, ChordQuality.MAJOR_7, ChordQuality.MINOR_7],
)
def test_seventh_and_diminished_chords_are_found(root: int, quality: ChordQuality) -> None:
    chords = _analyze_chord(voicing(root, CHORD_INTERVALS[quality]))
    assert len(chords) == 1
    assert (chords[0].root_pitch_class, chords[0].quality) == (root, quality)
    assert not chords[0].ambiguous
    assert chords[0].confidence >= 0.7


@pytest.mark.slow
def test_exhaustive_sweep_all_roots_and_qualities() -> None:
    exact = flagged = 0
    for quality in CLEAR_QUALITIES + EQUIVALENT_QUALITIES:
        for root in range(12):
            chords = _analyze_chord(voicing(root, CHORD_INTERVALS[quality]))
            assert len(chords) == 1
            if quality in EQUIVALENT_QUALITIES:
                flagged += chords[0].ambiguous
            else:
                exact += (chords[0].root_pitch_class, chords[0].quality) == (root, quality)
    assert exact == 72  # 12 racines x 6 qualités sans équivalent
    assert flagged == 36  # les 36 accords aug/sus2/sus4 sont tous signalés ambigus


# --- Accords ambigus par nature ---------------------------------------------


@pytest.mark.parametrize("root", [0, 5])
@pytest.mark.parametrize("quality", EQUIVALENT_QUALITIES)
def test_equivalent_chords_are_flagged_ambiguous_and_the_played_reading_is_listed(
    root: int, quality: ChordQuality
) -> None:
    chords = _analyze_chord(voicing(root, CHORD_INTERVALS[quality]))
    assert len(chords) == 1
    chord = chords[0]

    assert chord.ambiguous
    assert chord.confidence < 0.1  # jamais présenté comme certain
    # Les notes sont bien celles jouées, quelle que soit la lecture retenue...
    assert set(chord.pitch_classes) == set(chord_pitch_classes(root, quality))
    # ... et la lecture réellement jouée figure parmi les candidats.
    played = (root, quality)
    readings = {(chord.root_pitch_class, chord.quality)} | {
        (a.root_pitch_class, a.quality) for a in chord.alternatives
    }
    assert played in readings


# --- Basse et renversements -------------------------------------------------


def test_root_position_bass_gives_inversion_zero() -> None:
    chord = _analyze_chord([36, 60, 64, 67])[0]
    assert (chord.symbol, chord.inversion) == ("C", 0)


def test_first_inversion_is_found_from_the_bass_note() -> None:
    chord = _analyze_chord([40, 60, 64, 67])[0]  # mi grave sous un accord de do
    assert (chord.symbol, chord.bass_pitch_class, chord.inversion) == ("C/E", 4, 1)
    assert not chord.ambiguous


def test_second_inversion_is_found_from_the_bass_note() -> None:
    chord = _analyze_chord([43, 60, 64, 67])[0]
    assert (chord.symbol, chord.inversion) == ("C/G", 2)


def test_without_a_bass_register_note_the_inversion_is_not_claimed() -> None:
    chord = _analyze_chord([60, 64, 67])[0]
    assert chord.symbol == "C"
    assert chord.bass_pitch_class is None
    assert chord.inversion is None


def _mid_register_inversions(qualities, roots):
    """Accords joués uniquement à partir de do4 (aucune note grave), dans tous
    leurs renversements, avec le renversement réellement joué."""

    for quality in qualities:
        tones = CHORD_INTERVALS[quality]
        for root in roots:
            for inversion in range(len(tones)):
                order = list(tones[inversion:]) + [t + 12 for t in tones[:inversion]]
                start = 60 + ((root + order[0]) % 12)
                yield quality, root, inversion, [start + (o - order[0]) for o in order]


def test_mid_register_chords_never_claim_a_false_inversion() -> None:
    """Régression : avec un seuil de basse à 10 %, des activations parasites une
    octave sous les notes réelles faisaient affirmer une basse — donc un
    renversement — sans aucune note grave (46 inversions fausses sur 120, ex. un
    do en 2e renversement annoncé en position fondamentale)."""

    cases = list(
        _mid_register_inversions([ChordQuality.MAJOR, ChordQuality.DOMINANT_7], roots=[0, 5, 8])
    )
    for quality, root, _, midis in cases:
        chords = _analyze_chord(midis)
        assert len(chords) == 1
        assert (chords[0].root_pitch_class, chords[0].quality) == (root, quality)
        assert chords[0].bass_pitch_class is None
        assert chords[0].inversion is None


@pytest.mark.slow
def test_mid_register_sweep_never_claims_an_inversion() -> None:
    qualities = [ChordQuality.MAJOR, ChordQuality.MINOR, ChordQuality.DOMINANT_7]
    cases = list(_mid_register_inversions(qualities, roots=range(12)))
    assert len(cases) == 120
    for _, _, _, midis in cases:
        chords = _analyze_chord(midis)
        assert len(chords) == 1 and chords[0].inversion is None


def test_a_bass_much_weaker_than_the_chord_is_not_claimed() -> None:
    """Choix assumé : on préfère ne pas affirmer le renversement que d'en
    affirmer un faux. Une vraie basse à 15 % de l'amplitude de chaque note de
    l'accord (0.05 contre 0.33) n'est donc pas retenue."""

    from tests.unit.synth_audio import chord, tone

    weak_bass = tone(40, 2.0, amp=0.05)  # mi2 discret sous un accord de do
    signal = (chord([60, 64, 67], 2.0) + weak_bass).astype("float32")
    chords = _analyze(signal, SR).chords
    assert len(chords) == 1 and chords[0].symbol == "C"
    assert chords[0].bass_pitch_class is None


def test_bass_outside_the_chord_is_never_asserted_as_a_slash_chord() -> None:
    chords = _analyze_chord([38, 60, 64, 67])  # ré grave sous un accord de do
    assert len(chords) == 1
    chord = chords[0]
    assert chord.ambiguous
    assert chord.confidence < 0.1
    assert chord.bass_pitch_class is None or chord.bass_pitch_class in chord.pitch_classes


def test_low_bass_of_a_minor_chord() -> None:
    chord = _analyze_chord([33, 57, 60, 64])[0]  # la1 + la minor
    assert (chord.symbol, chord.inversion) == ("Am", 0)


# --- Enchaînements ----------------------------------------------------------


def test_progression_is_segmented_at_the_right_times() -> None:
    parts = [
        ([48, 64, 67, 72], 2.0),  # C
        ([41, 60, 65, 69], 2.0),  # F
        ([43, 62, 67, 71], 2.0),  # G
        ([45, 60, 64, 69], 2.0),  # Am
    ]

    chords = _analyze(sequence(parts), SR).chords

    assert [c.symbol for c in chords] == ["C", "F", "G", "Am"]
    for chord, expected_start in zip(chords, (0.0, 2.0, 4.0, 6.0), strict=True):
        assert chord.start_seconds == pytest.approx(expected_start, abs=0.12)
    assert chords[-1].end_seconds == pytest.approx(8.0, abs=0.12)
    validate_chords_non_overlapping(chords)
    assert not any(c.ambiguous for c in chords)


def test_silence_between_chords_is_a_gap_not_a_chord() -> None:
    parts = [([48, 64, 67, 72], 2.0), ([], 2.0), ([41, 60, 65, 69], 2.0)]

    chords = _analyze(sequence(parts), SR).chords

    assert [c.symbol for c in chords] == ["C", "F"]
    assert chords[0].end_seconds < 2.3
    assert chords[1].start_seconds > 3.7


def test_random_progressions_never_produce_overlapping_chords() -> None:
    rng = np.random.default_rng(4)
    qualities = [ChordQuality.MAJOR, ChordQuality.MINOR, ChordQuality.DOMINANT_7]
    for _ in range(6):
        parts = [
            (voicing(int(rng.integers(12)), CHORD_INTERVALS[qualities[int(rng.integers(3))]]), 1.5)
            for _ in range(4)
        ]
        chords = _analyze(sequence(parts), SR).chords
        validate_chords_non_overlapping(chords)
        assert all(c.duration_seconds > 0 for c in chords)


# --- Pas d'accord : jamais d'accord inventé ---------------------------------


def test_silence_gives_no_chord() -> None:
    assert _analyze(np.zeros(3 * SR, dtype="float32"), SR).chords == ()


def test_white_noise_gives_no_chord() -> None:
    noise = (0.1 * np.random.default_rng(0).normal(size=3 * SR)).astype("float32")
    assert _analyze(noise, SR).chords == ()


@pytest.mark.parametrize("pitch", [36, 60, 57])
def test_a_single_note_is_not_a_chord(pitch: int) -> None:
    assert _analyze_chord([pitch]) == ()


def test_a_major_third_dyad_is_not_a_chord() -> None:
    assert _analyze_chord([60, 64]) == ()


def test_a_fifth_is_a_power_chord_but_always_ambiguous_with_capped_confidence() -> None:
    chords = _analyze_chord([48, 55])
    assert len(chords) == 1
    chord = chords[0]
    assert (chord.root_pitch_class, chord.quality) == (0, ChordQuality.POWER)
    assert chord.ambiguous
    assert chord.confidence == pytest.approx(POWER_CONFIDENCE)


def test_empty_audio_gives_no_chord() -> None:
    assert _analyze(np.zeros(0, dtype="float32"), SR).chords == ()


# --- Bruit ajouté -----------------------------------------------------------


def _noisy_c_major(snr_db: float):
    rng = np.random.default_rng(1)
    clean = sequence([([60, 64, 67], 3.0)])
    noise = rng.normal(size=len(clean))
    noise *= np.sqrt(np.mean(clean**2)) / np.sqrt(np.mean(noise**2)) / (10 ** (snr_db / 20))
    return _analyze((clean + noise).astype("float32"), SR).chords


@pytest.mark.parametrize("snr_db", [20, 10])
def test_moderate_noise_keeps_the_right_unambiguous_chord(snr_db: int) -> None:
    chords = _noisy_c_major(snr_db)
    assert [c.symbol for c in chords] == ["C"]
    assert not chords[0].ambiguous


@pytest.mark.parametrize("snr_db", [5, 0])
def test_heavy_noise_degrades_into_doubt_not_into_false_certainty(snr_db: int) -> None:
    for chord in _noisy_c_major(snr_db):
        # Tout accord autre que le bon doit être signalé ; le bon peut l'être.
        if chord.symbol != "C":
            assert chord.ambiguous or chord.confidence < 0.5


# --- Fichier, délai, erreurs ------------------------------------------------


def test_estimate_chords_reads_a_wav_file(tmp_path: Path) -> None:
    path = tmp_path / "c.wav"
    sf.write(str(path), sequence([([48, 64, 67, 72], 2.0)]), SR)

    result = estimate_chords(path, timeout_seconds=60)

    assert [c.symbol for c in result.chords] == ["C"]
    assert result.duration_seconds == pytest.approx(2.0, abs=0.01)


def test_estimate_chords_times_out_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "c.wav"
    sf.write(str(path), sequence([([48, 64, 67, 72], 1.0)]), SR)

    def slow_load(*args: object, **kwargs: object):
        time.sleep(5)
        return np.zeros(100, dtype="float32"), SR

    with patch("librosa.load", side_effect=slow_load):
        with pytest.raises(ChordAnalysisTimeoutError):
            estimate_chords(path, timeout_seconds=1)


def test_estimate_chords_wraps_failures_without_inventing_a_result(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.wav"
    path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 4)
    with pytest.raises(ChordAnalysisError):
        estimate_chords(path, timeout_seconds=30)


# --- Briques internes -------------------------------------------------------


def test_majority_filter_removes_isolated_flicker() -> None:
    labels = np.array([1, 1, 1, 2, 1, 1, 1, 3, 3, 3, 3])
    assert list(analyzer._majority_filter(labels, 5)[:7]) == [1] * 7


def test_runs_and_short_run_merging() -> None:
    runs = analyzer._runs(np.array([1, 1, 1, 1, 2, 1, 1, 1, 1]))
    assert runs == [[1, 0, 4], [2, 4, 5], [1, 5, 9]]
    assert analyzer._merge_short_runs(runs, min_length=2) == [[1, 0, 9]]


def test_note_dictionary_places_harmonics_where_expected() -> None:
    dictionary = analyzer._note_dictionary()
    assert dictionary.shape == (analyzer.N_BINS, analyzer.N_NOTES)
    note = 12  # do2
    assert dictionary[3 * note, note] == pytest.approx(1.0)  # fondamentale
    assert dictionary[3 * note + 36, note] == pytest.approx(analyzer.HARMONIC_DECAY)  # octave
    assert dictionary[3 * note + 1, note] == pytest.approx(0.5)  # étalement mesuré


def test_bass_estimation_returns_none_without_energy() -> None:
    assert analyzer._estimate_bass(np.zeros((analyzer.N_NOTES, 5)), 0, 5) is None
