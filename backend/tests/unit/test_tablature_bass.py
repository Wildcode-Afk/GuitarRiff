"""Tests du mapping manche pour la basse (Étape 12) : accordages, limites de
cases, changements de position, séquences, notes répétées, silences et notes
impossibles. Le mapper est celui de la guitare ; seul le profil change."""

from __future__ import annotations

import random

from guitarriff.model import InstrumentKind, NoteEvent, Track
from guitarriff.tablature.cost import DEFAULT_WEIGHTS
from guitarriff.tablature.fretboard import (
    STANDARD_BASS_5_TUNING,
    STANDARD_BASS_6_TUNING,
    STANDARD_BASS_TUNING,
    STANDARD_GUITAR_TUNING,
    FretboardConfig,
)
from guitarriff.tablature.mapper import map_track_to_fretboard
from guitarriff.tablature.profiles import BASS_PROFILE, GUITAR_PROFILE, profile_for

BASS4 = FretboardConfig(tuning=STANDARD_BASS_TUNING)


def _note(pitch: int, start: float, duration: float = 0.4) -> NoteEvent:
    return NoteEvent(midi_pitch=pitch, start_seconds=start, duration_seconds=duration, velocity=90)


def _map(notes, config=BASS4, *, rest_reset_seconds=BASS_PROFILE.rest_reset_seconds, weights=None):
    track = Track(id="b", instrument=InstrumentKind.BASS, name="Basse", notes=tuple(notes))
    return map_track_to_fretboard(
        track, config, weights or BASS_PROFILE.weights, rest_reset_seconds=rest_reset_seconds
    )


def _positions(result) -> list[tuple[int, int]]:
    return [(n.instrument_info.string_index, n.instrument_info.fret) for n in result.track.notes]


def _line(pitches, step: float = 0.3) -> list[NoteEvent]:
    return [_note(p, i * step) for i, p in enumerate(pitches)]


# --- Profils ---------------------------------------------------------------


def test_profile_for_supported_instruments_and_none_otherwise() -> None:
    assert profile_for(InstrumentKind.BASS) is BASS_PROFILE
    assert profile_for(InstrumentKind.GUITAR) is GUITAR_PROFILE
    assert profile_for(InstrumentKind.DRUMS) is None
    assert profile_for(InstrumentKind.PIANO) is None


def test_bass_profile_defaults_to_four_string_standard_tuning() -> None:
    assert BASS_PROFILE.default_tuning == STANDARD_BASS_TUNING
    assert GUITAR_PROFILE.default_tuning == STANDARD_GUITAR_TUNING


def test_bass_profile_penalizes_movement_and_stretch_more_than_guitar() -> None:
    assert BASS_PROFILE.weights.movement_weight > GUITAR_PROFILE.weights.movement_weight
    assert BASS_PROFILE.weights.span_weight > GUITAR_PROFILE.weights.span_weight
    assert BASS_PROFILE.weights.string_change_weight > 0
    # Le profil guitare (Étape 11) est inchangé : pas de terme de changement de corde,
    # pas de réinitialisation après silence.
    assert GUITAR_PROFILE.weights == DEFAULT_WEIGHTS
    assert GUITAR_PROFILE.weights.string_change_weight == 0
    assert GUITAR_PROFILE.rest_reset_seconds is None


# --- Accordages et nombre de cordes ---------------------------------------


def test_each_open_string_of_standard_bass_is_played_open() -> None:
    result = _map(_line([28, 33, 38, 43]))
    assert result.placed_count == 4
    assert _positions(result) == [(0, 0), (1, 0), (2, 0), (3, 0)]


def test_five_string_bass_reaches_the_low_b() -> None:
    config = FretboardConfig(tuning=STANDARD_BASS_5_TUNING)
    result = _map([_note(23, 0.0)], config)
    assert _positions(result) == [(0, 0)]
    assert result.track.tuning == STANDARD_BASS_5_TUNING


def test_low_b_is_unplaced_on_four_string_but_placed_on_five_string() -> None:
    four = _map([_note(23, 0.0)])
    five = _map([_note(23, 0.0)], FretboardConfig(tuning=STANDARD_BASS_5_TUNING))
    assert four.placed_count == 0 and len(four.unplaced) == 1
    assert five.placed_count == 1 and len(five.unplaced) == 0


def test_six_string_bass_high_c_string_played_open() -> None:
    config = FretboardConfig(tuning=STANDARD_BASS_6_TUNING)
    result = _map([_note(48, 0.0)], config)
    assert _positions(result) == [(5, 0)]


def test_drop_d_bass_plays_low_d_open() -> None:
    drop_d = (26, 33, 38, 43)
    result = _map([_note(26, 0.0)], FretboardConfig(tuning=drop_d))
    assert _positions(result) == [(0, 0)]
    assert result.track.tuning == drop_d


def test_capo_is_recorded_on_the_resulting_track() -> None:
    config = FretboardConfig(tuning=STANDARD_BASS_TUNING, capo_fret=2)
    result = _map([_note(32, 0.0)], config)  # E1 + capo 2 + 2 = 32
    assert result.track.capo_fret == 2
    assert _positions(result) == [(0, 2)]


# --- Limites de cases -------------------------------------------------------


def test_highest_reachable_pitch_follows_max_fret() -> None:
    config = FretboardConfig(tuning=STANDARD_BASS_TUNING, max_fret=12)
    reachable = _map([_note(55, 0.0)], config)  # G2 (43) + 12
    beyond = _map([_note(56, 0.0)], config)
    assert _positions(reachable) == [(3, 12)]
    assert beyond.placed_count == 0
    assert "hors de portée" in beyond.unplaced[0].reason


def test_fret_limit_changes_which_strings_are_candidates() -> None:
    # 46 : G fret3 / D fret8 / A fret13 / E fret18 ; avec max_fret=7 seuls G3 reste jouable.
    config = FretboardConfig(tuning=STANDARD_BASS_TUNING, max_fret=7)
    result = _map([_note(46, 0.0)], config)
    assert _positions(result) == [(3, 3)]


# --- Changements de position et séquences ----------------------------------


def test_walking_line_stays_in_one_position() -> None:
    # Ligne ascendante E1 -> A1 : tout se joue en première position.
    result = _map(_line([28, 30, 31, 33, 35, 36]))
    frets = [fret for _, fret in _positions(result)]
    assert max(frets) <= 5


def test_bass_profile_keeps_a_line_on_one_string_where_guitar_weights_jump() -> None:
    """Cas trouvé par recherche sur les séquences de 3 notes : avec les poids
    guitare, la dernière note saute à la corde de ré (case 1) ; avec le profil
    basse, la ligne reste sur la corde de la (cases 0, 4, 6)."""

    notes = _line([33, 37, 39])
    bass = _map(notes)
    guitar = _map(notes, rest_reset_seconds=None, weights=DEFAULT_WEIGHTS)
    assert _positions(bass) == [(1, 0), (1, 4), (1, 6)]
    assert _positions(guitar) == [(1, 0), (1, 4), (2, 1)]


def _travel(positions: list[tuple[int, int]]) -> tuple[int, int]:
    hand = strings = 0
    previous_fret = previous_string = None
    for string_index, fret in positions:
        if fret > 0:
            if previous_fret is not None:
                hand += abs(fret - previous_fret)
            previous_fret = fret
        if previous_string is not None:
            strings += abs(string_index - previous_string)
        previous_string = string_index
    return hand, strings


def test_bass_profile_limits_hand_travel_and_string_changes_on_simulated_lines() -> None:
    """Sur 300 lignes simulées (marche aléatoire de petits intervalles, graine
    fixe), le profil basse déplace moins la main et change moins de corde que
    les poids guitare. Mesure sur des données SIMULÉES, pas sur de vraies
    lignes de basse."""

    rng = random.Random(11)
    bass_hand = bass_strings = guitar_hand = guitar_strings = 0
    for _ in range(300):
        pitch = rng.randint(30, 44)
        pitches = [pitch]
        for _ in range(rng.randint(5, 12) - 1):
            pitch = max(28, min(60, pitch + rng.choice([-5, -3, -2, -1, 0, 0, 1, 2, 3, 5, 7])))
            pitches.append(pitch)
        notes = _line(pitches)
        bass_h, bass_s = _travel(_positions(_map(notes)))
        guitar_h, guitar_s = _travel(
            _positions(_map(notes, rest_reset_seconds=None, weights=DEFAULT_WEIGHTS))
        )
        bass_hand += bass_h
        bass_strings += bass_s
        guitar_hand += guitar_h
        guitar_strings += guitar_s

    assert bass_hand <= guitar_hand
    assert bass_strings <= guitar_strings
    assert (bass_hand, bass_strings) != (guitar_hand, guitar_strings)


# --- Notes répétées ---------------------------------------------------------


def test_repeated_open_string_note_stays_on_the_same_string() -> None:
    result = _map(_line([28, 28, 28, 28]))
    assert set(_positions(result)) == {(0, 0)}


def test_repeated_fretted_note_keeps_exactly_the_same_position() -> None:
    result = _map(_line([45] * 6))
    assert len(set(_positions(result))) == 1


def test_repeated_notes_inside_a_line_keep_their_position() -> None:
    result = _map(_line([40, 43, 43, 43, 45, 45, 40]))
    positions = _positions(result)
    assert positions[1] == positions[2] == positions[3]
    assert positions[4] == positions[5]


def test_repeated_notes_never_move_on_random_sequences() -> None:
    """Propriété vérifiée sur 500 séquences aléatoires avec répétitions
    immédiates (graine fixe)."""

    rng = random.Random(3)
    for _ in range(500):
        pitches: list[int] = []
        for _ in range(rng.randint(3, 8)):
            pitch = rng.randint(28, 58)
            pitches.append(pitch)
            if rng.random() < 0.5:
                pitches.append(pitch)
        positions = _positions(_map(_line(pitches, step=0.2)))
        for i in range(1, len(pitches)):
            if pitches[i] == pitches[i - 1]:
                assert positions[i] == positions[i - 1]


def test_identical_simultaneous_notes_are_both_placed_on_distinct_strings() -> None:
    twin = _note(45, 1.0)
    result = _map([twin, twin])
    assert result.placed_count == 2
    strings = {s for s, _ in _positions(result)}
    assert len(strings) == 2


# --- Silences ---------------------------------------------------------------


def _high_then_low(gap: float, **kwargs):
    # 52 n'est jouable qu'en position haute (G case 9 le moins haut) ; 41 a des
    # candidats case 13 / 8 / 3. Fin de la première note : 0.5.
    return _map([_note(52, 0.0, 0.5), _note(41, 0.5 + gap, 0.5)], **kwargs)


def test_short_silence_keeps_the_hand_in_position() -> None:
    result = _high_then_low(0.2)
    assert _positions(result) == [(3, 9), (1, 8)]


def test_long_silence_lets_the_hand_reposition() -> None:
    result = _high_then_low(3.0)
    assert _positions(result) == [(3, 9), (2, 3)]


def test_without_rest_rule_a_long_silence_changes_nothing() -> None:
    result = _high_then_low(3.0, rest_reset_seconds=None)
    assert _positions(result) == [(3, 9), (1, 8)]


def test_silence_threshold_is_inclusive() -> None:
    exactly = _high_then_low(1.0)
    just_below = _high_then_low(0.99)
    assert _positions(exactly)[1] == (2, 3)
    assert _positions(just_below)[1] == (1, 8)


def test_unplaced_note_during_a_silence_does_not_reset_or_break_context() -> None:
    notes = [_note(52, 0.0, 0.5), _note(5, 0.7), _note(41, 0.8, 0.5)]
    result = _map(notes)
    assert result.placed_count == 2
    assert len(result.unplaced) == 1
    assert _positions_by_index(result, 2) == (1, 8)  # contexte conservé


def _positions_by_index(result, index: int) -> tuple[int, int]:
    info = result.track.notes[index].instrument_info
    return (info.string_index, info.fret)


# --- Notes impossibles ------------------------------------------------------


def test_pitch_below_lowest_string_is_reported() -> None:
    result = _map([_note(27, 0.0)])  # un demi-ton sous le mi grave
    assert result.placed_count == 0
    assert result.unplaced[0].note.midi_pitch == 27
    assert result.track.notes[0].instrument_info is None


def test_five_simultaneous_notes_exceed_four_strings() -> None:
    chord = [_note(p, 1.0) for p in (28, 33, 38, 43, 48)]
    result = _map(chord)
    assert result.placed_count == 0
    assert len(result.unplaced) == 5


def test_five_simultaneous_notes_fit_on_a_five_string_bass() -> None:
    chord = [_note(p, 1.0) for p in (28, 33, 38, 43, 48)]
    result = _map(chord, FretboardConfig(tuning=STANDARD_BASS_5_TUNING))
    assert result.placed_count == 5
    assert len({s for s, _ in _positions(result)}) == 5


def test_double_stop_uses_two_distinct_strings() -> None:
    result = _map([_note(28, 1.0), _note(35, 1.0)])  # E1 + B1
    assert result.placed_count == 2
    assert len({s for s, _ in _positions(result)}) == 2


def test_mixed_reachable_and_unreachable_notes() -> None:
    result = _map(_line([28, 20, 33]))
    assert result.placed_count == 2
    assert [u.note.midi_pitch for u in result.unplaced] == [20]
