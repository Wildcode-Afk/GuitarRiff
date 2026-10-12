"""Tests de `tablature/mapper.py` — notes simples, accords, changements de
position, accordages différents, notes impossibles."""

from __future__ import annotations

from guitarriff.model import InstrumentKind, NoteEvent, Track
from guitarriff.tablature.fretboard import (
    STANDARD_BASS_TUNING,
    STANDARD_GUITAR_TUNING,
    FretboardConfig,
)
from guitarriff.tablature.mapper import map_track_to_fretboard


def _note(pitch: int, start: float, duration: float = 0.5) -> NoteEvent:
    return NoteEvent(midi_pitch=pitch, start_seconds=start, duration_seconds=duration, velocity=90)


def _track(*notes: NoteEvent, instrument: InstrumentKind = InstrumentKind.GUITAR) -> Track:
    return Track(id="t", instrument=instrument, name="T", notes=notes)


STANDARD = FretboardConfig(tuning=STANDARD_GUITAR_TUNING)


# --- Notes simples ---------------------------------------------------------


def test_single_note_gets_a_valid_position() -> None:
    track = _track(_note(69, 0.0))  # A4

    result = map_track_to_fretboard(track, STANDARD)

    assert result.placed_count == 1
    assert len(result.unplaced) == 0
    info = result.track.notes[0].instrument_info
    assert info is not None
    assert STANDARD.tuning[info.string_index] + info.fret == 69


def test_track_tuning_is_set_on_result() -> None:
    track = _track(_note(60, 0.0))
    result = map_track_to_fretboard(track, STANDARD)
    assert result.track.tuning == STANDARD_GUITAR_TUNING


def test_open_string_preferred_when_available_and_no_movement_pressure() -> None:
    # 40 (E2) n'est jouable qu'à vide sur l'accordage standard.
    track = _track(_note(40, 0.0))
    result = map_track_to_fretboard(track, STANDARD)
    info = result.track.notes[0].instrument_info
    assert (info.string_index, info.fret) == (0, 0)


def test_does_not_always_pick_the_first_candidate_string() -> None:
    """69 (A4) a des candidats sur plusieurs cordes ; la case la plus basse
    (corde aiguë) doit être préférée à la première corde trouvée (grave)."""

    track = _track(_note(69, 0.0))
    result = map_track_to_fretboard(track, STANDARD)
    info = result.track.notes[0].instrument_info
    # Le premier candidat trouvé en parcourant les cordes dans l'ordre serait
    # la corde la plus grave praticable (A2, case 24) ; le coût doit plutôt
    # choisir la corde E4 (case 5), bien plus confortable.
    assert info.string_index == 5
    assert info.fret == 5


# --- Accords (notes simultanées) -------------------------------------------


def test_chord_notes_get_distinct_strings() -> None:
    chord = (_note(40, 1.0), _note(47, 1.0), _note(52, 1.0))  # power chord + tierce
    track = _track(*chord)

    result = map_track_to_fretboard(track, STANDARD)

    assert result.placed_count == 3
    strings_used = [n.instrument_info.string_index for n in result.track.notes]
    assert len(set(strings_used)) == 3


def test_chord_with_near_but_not_exactly_equal_onsets_is_grouped() -> None:
    # Micro-gigue réaliste d'une transcription audio : débuts proches mais
    # pas rigoureusement identiques (< 50ms de tolérance).
    chord = (_note(40, 1.000), _note(47, 1.012), _note(52, 1.030))
    track = _track(*chord)

    result = map_track_to_fretboard(track, STANDARD)

    strings_used = [n.instrument_info.string_index for n in result.track.notes]
    assert len(set(strings_used)) == 3  # traité comme un accord, pas 3 notes isolées


def test_notes_far_apart_in_time_are_not_grouped_into_a_chord() -> None:
    track = _track(_note(40, 0.0), _note(47, 5.0))
    result = map_track_to_fretboard(track, STANDARD)
    # Pas de contrainte de cordes distinctes ici : chaque note choisie
    # indépendamment pourrait tout à fait retomber sur la même corde.
    assert result.placed_count == 2


# --- Changements de position (cohérence avec la note précédente) ----------


def test_sequence_prefers_staying_near_previous_position() -> None:
    """Vérifié manuellement : avec une première note en case 7, la note
    suivante (candidats aux cases 2/7/12) doit rester en case 7 plutôt que
    de sauter à la case 2, pourtant plus basse en valeur absolue."""

    track = _track(_note(71, 0.0), _note(52, 0.5))
    result = map_track_to_fretboard(track, STANDARD)

    first, second = result.track.notes
    assert first.instrument_info.fret == 7
    assert second.instrument_info.fret == 7
    assert second.instrument_info.string_index != first.instrument_info.string_index


def test_open_string_note_does_not_reset_hand_position_memory() -> None:
    """Une corde à vide entre deux notes pressées ne doit pas faire oublier
    la position de main précédente."""

    track = _track(_note(71, 0.0), _note(40, 0.5), _note(52, 1.0))
    result = map_track_to_fretboard(track, STANDARD)

    first, middle, last = result.track.notes
    assert first.instrument_info.fret == 7
    assert (middle.instrument_info.string_index, middle.instrument_info.fret) == (0, 0)
    # La référence de 7 (première note) doit toujours s'appliquer à la troisième.
    assert last.instrument_info.fret == 7


# --- Accordages différents --------------------------------------------------


def test_bass_track_uses_four_string_tuning() -> None:
    track = _track(_note(28, 0.0), instrument=InstrumentKind.BASS)
    config = FretboardConfig(tuning=STANDARD_BASS_TUNING)

    result = map_track_to_fretboard(track, config)

    assert result.track.tuning == STANDARD_BASS_TUNING
    info = result.track.notes[0].instrument_info
    assert (info.string_index, info.fret) == (0, 0)


def test_capo_changes_chosen_position() -> None:
    track = _track(_note(44, 0.0))
    config_no_capo = FretboardConfig(tuning=STANDARD_GUITAR_TUNING, capo_fret=0)
    config_capo_2 = FretboardConfig(tuning=STANDARD_GUITAR_TUNING, capo_fret=2)

    without_capo = map_track_to_fretboard(track, config_no_capo).track.notes[0].instrument_info
    with_capo = map_track_to_fretboard(track, config_capo_2).track.notes[0].instrument_info

    assert without_capo.fret == 4  # E2 + 4 = 44
    assert with_capo.fret == 2  # E2 + capo(2) + 2 = 44


def test_custom_drop_d_tuning_supported() -> None:
    drop_d = (38, 45, 50, 55, 59, 64)  # D2 A2 D3 G3 B3 E4
    track = _track(_note(38, 0.0))
    result = map_track_to_fretboard(track, FretboardConfig(tuning=drop_d))
    info = result.track.notes[0].instrument_info
    assert (info.string_index, info.fret) == (0, 0)


# --- Notes impossibles ------------------------------------------------------


def test_pitch_out_of_range_is_reported_not_silently_dropped() -> None:
    too_low = _note(10, 0.0)
    track = _track(too_low)

    result = map_track_to_fretboard(track, STANDARD)

    assert result.placed_count == 0
    assert len(result.unplaced) == 1
    assert result.unplaced[0].note == too_low
    assert "hors de portée" in result.unplaced[0].reason


def test_out_of_range_note_keeps_instrument_info_none_in_resulting_track() -> None:
    track = _track(_note(10, 0.0))
    result = map_track_to_fretboard(track, STANDARD)
    assert result.track.notes[0].instrument_info is None


def test_chord_exceeding_string_count_is_entirely_reported() -> None:
    # 5 notes simultanées sur une basse à 4 cordes : aucune ne doit être
    # placée arbitrairement, toutes sont signalées.
    chord = tuple(_note(p, 1.0) for p in (28, 33, 38, 43, 48))
    track = _track(*chord, instrument=InstrumentKind.BASS)
    config = FretboardConfig(tuning=STANDARD_BASS_TUNING)

    result = map_track_to_fretboard(track, config)

    assert result.placed_count == 0
    assert len(result.unplaced) == 5
    assert all("impossible de toutes les jouer" in u.reason for u in result.unplaced)


def test_unreachable_chord_does_not_corrupt_later_reference_position() -> None:
    too_many = tuple(_note(p, 1.0) for p in (28, 33, 38, 43, 48))
    later_note = _note(33, 3.0)
    track = _track(*too_many, later_note, instrument=InstrumentKind.BASS)
    config = FretboardConfig(tuning=STANDARD_BASS_TUNING)

    result = map_track_to_fretboard(track, config)

    # La dernière note doit toujours être placée normalement malgré l'échec précédent.
    placed_later = next(n for n in result.track.notes if n.start_seconds == 3.0)
    assert placed_later.instrument_info is not None


def test_mixed_group_partially_out_of_range_places_reachable_notes() -> None:
    # Un accord où une note est hors de portée mais les autres sont jouables :
    # les notes jouables doivent tout de même être placées.
    reachable = _note(40, 1.0)
    out_of_range = _note(10, 1.0)
    track = _track(reachable, out_of_range)

    result = map_track_to_fretboard(track, STANDARD)

    assert result.placed_count == 1
    assert len(result.unplaced) == 1
    assert result.unplaced[0].note == out_of_range


def test_empty_track_returns_empty_result() -> None:
    track = _track()
    result = map_track_to_fretboard(track, STANDARD)
    assert result.placed_count == 0
    assert result.unplaced == ()
    assert result.track.notes == ()
