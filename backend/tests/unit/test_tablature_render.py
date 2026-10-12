"""Tests de `tablature/render.py` — lisibilité du rendu ASCII."""

from __future__ import annotations

import pytest

from guitarriff.model import (
    InstrumentKind,
    InstrumentSpecificInfo,
    MusicalPosition,
    NoteEvent,
    Track,
)
from guitarriff.tablature.fretboard import (
    STANDARD_BASS_5_TUNING,
    STANDARD_BASS_TUNING,
    STANDARD_GUITAR_TUNING,
    FretboardConfig,
)
from guitarriff.tablature.mapper import map_track_to_fretboard
from guitarriff.tablature.profiles import BASS_PROFILE
from guitarriff.tablature.render import MAX_REST_COLUMNS, render_ascii_tab, string_labels


def _placed(
    string_index: int, fret: int, start: float, duration: float = 0.4, *, bar: int | None = None
):
    return NoteEvent(
        midi_pitch=60,
        start_seconds=start,
        duration_seconds=duration,
        velocity=90,
        instrument_info=InstrumentSpecificInfo(string_index=string_index, fret=fret),
        position=MusicalPosition(bar=bar, beat=1.0) if bar is not None else None,
    )


def _bass_track(*notes: NoteEvent, capo_fret: int = 0, tuning=STANDARD_BASS_TUNING) -> Track:
    return Track(
        id="bass",
        instrument=InstrumentKind.BASS,
        name="Basse",
        tuning=tuning,
        capo_fret=capo_fret,
        notes=tuple(notes),
    )


def _string_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if "|" in line]


# --- Noms de cordes ---------------------------------------------------------


def test_string_labels_for_standard_guitar() -> None:
    assert string_labels(STANDARD_GUITAR_TUNING) == ("E", "A", "D", "G", "B", "e")


def test_string_labels_for_four_and_five_string_bass() -> None:
    assert string_labels(STANDARD_BASS_TUNING) == ("E", "A", "D", "G")
    assert string_labels(STANDARD_BASS_5_TUNING) == ("B", "E", "A", "D", "G")


def test_string_labels_for_seven_string_guitar() -> None:
    assert string_labels((35, 40, 45, 50, 55, 59, 64)) == ("B", "E", "A", "D", "G", "b", "e")


# --- Rendu de base ----------------------------------------------------------


def test_renders_exact_layout_for_notes_and_a_chord() -> None:
    track = _bass_track(
        _placed(0, 0, 0.0),
        _placed(1, 2, 0.5),
        _placed(0, 3, 1.0),
        _placed(2, 2, 1.0),
    )

    rendering = render_ascii_tab(track)

    assert rendering.text.splitlines() == [
        "Basse — accordage E A D G",
        "",
        "G|---------|",
        "D|-------2-|",
        "A|----2----|",
        "E|-0-----3-|",
    ]
    assert rendering.placed_count == 4
    assert rendering.unplaced_count == 0


def test_highest_string_is_on_top() -> None:
    track = _bass_track(_placed(3, 5, 0.0))
    lines = _string_lines(render_ascii_tab(track).text)
    assert lines[0].startswith("G|")
    assert lines[-1].startswith("E|")


def test_two_digit_frets_keep_columns_aligned() -> None:
    track = _bass_track(_placed(0, 12, 0.0), _placed(1, 5, 0.0), _placed(0, 3, 1.0))
    lines = _string_lines(render_ascii_tab(track).text)
    assert len({len(line) for line in lines}) == 1  # toutes les lignes de même longueur
    assert any("-12-" in line for line in lines)
    assert any("-5--" in line for line in lines)


def test_five_string_tuning_renders_five_lines() -> None:
    track = _bass_track(_placed(0, 0, 0.0), tuning=STANDARD_BASS_5_TUNING)
    lines = _string_lines(render_ascii_tab(track).text)
    assert [line[0] for line in lines] == ["G", "D", "A", "E", "B"]


def test_capo_is_mentioned_in_header() -> None:
    track = _bass_track(_placed(0, 0, 0.0), capo_fret=2)
    assert "capodastre case 2" in render_ascii_tab(track).text.splitlines()[0]


def test_no_capo_mention_without_capo() -> None:
    track = _bass_track(_placed(0, 0, 0.0))
    assert "capodastre" not in render_ascii_tab(track).text


# --- Notes répétées ---------------------------------------------------------


def test_repeated_notes_each_get_their_own_column() -> None:
    track = _bass_track(*[_placed(0, 3, i * 0.5) for i in range(4)])
    e_line = _string_lines(render_ascii_tab(track).text)[-1]
    assert e_line == "E|-3--3--3--3-|"


# --- Silences ---------------------------------------------------------------


def _e_line(track: Track, **kwargs) -> str:
    return _string_lines(render_ascii_tab(track, **kwargs).text)[-1]


def test_silence_of_several_beats_inserts_blank_columns() -> None:
    # fin de la 1re note : 0.5 ; début de la 2e : 2.5 => silence de 2.0 s = 4 temps de 0.5 s
    track = _bass_track(_placed(0, 0, 0.0, 0.5), _placed(0, 0, 2.5, 0.5))
    assert _e_line(track, beat_seconds=0.5) == "E|-0-" + "---" * 4 + "-0-|"


def test_silence_shorter_than_a_beat_adds_nothing() -> None:
    track = _bass_track(_placed(0, 0, 0.0, 0.5), _placed(0, 0, 0.7, 0.5))
    assert _e_line(track, beat_seconds=0.5) == "E|-0--0-|"


def test_long_silence_is_capped() -> None:
    track = _bass_track(_placed(0, 0, 0.0, 0.5), _placed(0, 0, 100.0, 0.5))
    assert _e_line(track, beat_seconds=0.5) == "E|-0-" + "---" * MAX_REST_COLUMNS + "-0-|"


def test_without_beat_duration_silences_are_not_materialized() -> None:
    track = _bass_track(_placed(0, 0, 0.0, 0.5), _placed(0, 0, 100.0, 0.5))
    assert _e_line(track) == "E|-0--0-|"


# --- Mesures ----------------------------------------------------------------


def test_bar_lines_follow_computed_positions() -> None:
    track = _bass_track(
        _placed(0, 0, 0.0, bar=1),
        _placed(0, 0, 0.5, bar=1),
        _placed(0, 0, 2.0, bar=2),
    )
    assert _e_line(track) == "E|-0--0-|-0-|"


def test_no_bar_lines_when_positions_are_not_computed() -> None:
    track = _bass_track(_placed(0, 0, 0.0), _placed(0, 0, 2.0))
    assert "|-0--0-|" in _e_line(track)
    assert _e_line(track).count("|") == 2  # barre d'ouverture et de fin seulement


# --- Retour à la ligne ------------------------------------------------------


def test_long_tab_wraps_within_max_width() -> None:
    track = _bass_track(*[_placed(i % 4, i % 7, i * 0.5) for i in range(30)])

    text = render_ascii_tab(track, max_width=30).text

    assert all(len(line) <= 30 for line in text.splitlines())
    assert text.count("G|") > 1  # plusieurs systèmes


def test_wrapping_never_loses_a_note() -> None:
    notes = [_placed(0, i % 10, i * 0.5) for i in range(25)]
    track = _bass_track(*notes)

    text = render_ascii_tab(track, max_width=24).text
    e_lines = [line for line in text.splitlines() if line.startswith("E|")]
    digits = "".join(ch for line in e_lines for ch in line[2:] if ch.isdigit())

    assert digits == "".join(str(i % 10) for i in range(25))


# --- Notes sans position, cas limites --------------------------------------


def test_notes_without_position_are_counted_not_hidden() -> None:
    unplaced = NoteEvent(midi_pitch=10, start_seconds=1.0, duration_seconds=0.4, velocity=90)
    track = _bass_track(_placed(0, 0, 0.0), unplaced)

    rendering = render_ascii_tab(track)

    assert rendering.placed_count == 1
    assert rendering.unplaced_count == 1
    assert "1 note(s) sans position" in rendering.text


def test_track_without_any_placed_note_still_renders() -> None:
    rendering = render_ascii_tab(_bass_track())
    assert rendering.placed_count == 0
    assert len(_string_lines(rendering.text)) == 4


def test_missing_tuning_is_rejected() -> None:
    track = Track(id="b", instrument=InstrumentKind.BASS, name="Basse", notes=())
    with pytest.raises(ValueError, match="accordage"):
        render_ascii_tab(track)


# --- De bout en bout avec le mapper ----------------------------------------


def test_render_of_a_mapped_bass_line() -> None:
    pitches = [28, 28, 31, 33, 38, 40]
    notes = tuple(
        NoteEvent(midi_pitch=p, start_seconds=i * 0.5, duration_seconds=0.4, velocity=90)
        for i, p in enumerate(pitches)
    )
    track = Track(id="b", instrument=InstrumentKind.BASS, name="Basse", notes=notes)
    mapped = map_track_to_fretboard(
        track,
        FretboardConfig(tuning=STANDARD_BASS_TUNING),
        BASS_PROFILE.weights,
        rest_reset_seconds=BASS_PROFILE.rest_reset_seconds,
    )

    lines = _string_lines(render_ascii_tab(mapped.track).text)

    # 28 28 -> mi à vide (x2) ; 31 -> mi case 3 ; 33 -> la à vide ;
    # 38 -> ré à vide ; 40 -> ré case 2 (rester en première position).
    assert lines == [
        "G|" + "---" * 6 + "|",
        "D|" + "---" * 4 + "-0-" + "-2-" + "|",
        "A|" + "---" * 3 + "-0-" + "---" * 2 + "|",
        "E|" + "-0-" + "-0-" + "-3-" + "---" * 3 + "|",
    ]
