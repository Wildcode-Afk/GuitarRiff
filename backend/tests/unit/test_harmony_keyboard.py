"""Tests de `harmony/keyboard.py` : piste clavier à partir d'accords."""

from __future__ import annotations

import random

import pytest

from guitarriff.harmony import keyboard as kb
from guitarriff.harmony.keyboard import generate_keyboard
from guitarriff.model import (
    AudioMetadata,
    ChordEvent,
    ChordQuality,
    Clef,
    EstimationSource,
    InstrumentKind,
    Song,
)

QUALITIES = [q for q in ChordQuality if q != ChordQuality.POWER]


def _c(
    root, quality=ChordQuality.MAJOR, start=0.0, bass=None, duration=2.0, **kwargs
) -> ChordEvent:
    return ChordEvent(
        root_pitch_class=root,
        quality=quality,
        bass_pitch_class=bass,
        start_seconds=start,
        duration_seconds=duration,
        **kwargs,
    )


def _progression() -> tuple[ChordEvent, ...]:
    return (
        _c(0, start=0.0),  # C
        _c(5, start=2.0),  # F
        _c(7, ChordQuality.DOMINANT_7, start=4.0),  # G7
        _c(9, ChordQuality.MINOR, start=6.0),  # Am
        _c(0, start=8.0, bass=4),  # C/E
    )


def _notes_at(track, start: float) -> list[int]:
    return sorted(n.midi_pitch for n in track.notes if abs(n.start_seconds - start) < 1e-9)


# --- Résultat attendu sur une progression connue ----------------------------


def test_known_progression_gives_expected_voicings() -> None:
    """Sortie observée et relue à la main avant d'être figée : conduite des voix
    (do5 commun entre C et F), basse en renversement pour C/E."""

    result = generate_keyboard(_progression())

    assert [_notes_at(result.right_hand, s) for s in (0.0, 2.0, 4.0, 6.0, 8.0)] == [
        [64, 67, 72],  # E4 G4 C5
        [65, 69, 72],  # F4 A4 C5
        [65, 67, 71, 74],  # F4 G4 B4 D5
        [64, 69, 72],  # E4 A4 C5
        [64, 67, 72],  # E4 G4 C5
    ]
    assert [_notes_at(result.left_hand, s) for s in (0.0, 2.0, 4.0, 6.0, 8.0)] == [
        [48],  # C3
        [53],  # F3
        [55],  # G3
        [45],  # A2
        [40],  # E2 : basse du renversement C/E
    ]
    assert result.chord_count == 5


def test_tracks_are_two_piano_tracks_with_the_right_clefs() -> None:
    result = generate_keyboard(_progression())
    assert (result.right_hand.id, result.left_hand.id) == ("piano-rh", "piano-lh")
    assert result.right_hand.instrument == result.left_hand.instrument == InstrumentKind.PIANO
    assert result.right_hand.display.clef == Clef.TREBLE
    assert result.left_hand.display.clef == Clef.BASS


def test_generated_tracks_are_accepted_by_song() -> None:
    result = generate_keyboard(_progression())
    Song(
        duration_seconds=12.0,
        audio=AudioMetadata(source_file_id="f", sample_rate=22050, channels=1),
        tracks=(result.right_hand, result.left_hand),
        chords=_progression(),
    )


# --- Jouabilité (invariants) ------------------------------------------------


def _random_progression(rng: random.Random, n: int) -> tuple[ChordEvent, ...]:
    return tuple(
        _c(
            rng.randrange(12),
            rng.choice(QUALITIES),
            start=i * 2.0,
            bass=rng.choice([None, rng.randrange(12)]),
        )
        for i in range(n)
    )


def test_every_voicing_is_playable_by_one_hand_and_complete() -> None:
    rng = random.Random(1)
    for _ in range(200):
        chords = _random_progression(rng, 6)
        result = generate_keyboard(chords)
        for chord in chords:
            right = _notes_at(result.right_hand, chord.start_seconds)
            assert 3 <= len(right) <= 4
            assert right[-1] - right[0] <= kb.MAX_HAND_SPAN
            assert kb.RH_LOW <= right[0] and right[-1] <= kb.RH_HIGH
            # Toutes les notes de l'accord, chacune une fois, aucune note étrangère.
            assert sorted(p % 12 for p in right) == sorted(chord.pitch_classes)
            assert len({p for p in right}) == len(right)


def test_left_hand_plays_one_bass_note_in_range() -> None:
    rng = random.Random(2)
    for _ in range(200):
        chords = _random_progression(rng, 6)
        result = generate_keyboard(chords)
        for chord in chords:
            left = _notes_at(result.left_hand, chord.start_seconds)
            assert len(left) == 1
            assert kb.LH_LOW <= left[0] <= kb.LH_HIGH
            expected = (
                chord.bass_pitch_class
                if chord.bass_pitch_class is not None
                else chord.root_pitch_class
            )
            assert left[0] % 12 == expected


def test_power_chord_is_playable_with_two_notes() -> None:
    result = generate_keyboard((_c(0, ChordQuality.POWER),))
    assert len(_notes_at(result.right_hand, 0.0)) == 2


def test_notes_never_overlap_between_successive_chords() -> None:
    result = generate_keyboard(_progression())
    for track in (result.right_hand, result.left_hand):
        by_start: dict[float, float] = {}
        for note in track.notes:
            by_start[note.start_seconds] = note.end_seconds
        starts = sorted(by_start)
        assert all(by_start[a] <= b + 1e-9 for a, b in zip(starts, starts[1:], strict=False))


def test_voice_leading_moves_the_hand_less_than_a_fixed_voicing() -> None:
    """Sur 300 progressions aléatoires, la conduite des voix déplace moins la main
    qu'un voicing fixe en état fondamental (mesuré avec cette graine : 13859 contre
    32161 demi-tons cumulés, soit un ratio de 0.43, et jamais pire sur une
    progression donnée)."""

    rng = random.Random(5)
    total_leading = total_fixed = 0
    for _ in range(300):
        chords = _random_progression(rng, 8)
        result = generate_keyboard(chords)
        led = [tuple(_notes_at(result.right_hand, c.start_seconds)) for c in chords]
        fixed = [
            min(
                (
                    v
                    for v in kb._right_hand_candidates(c.pitch_classes)
                    if v[0] % 12 == c.pitch_classes[0]
                ),
                key=lambda p: (abs(sum(p) / len(p) - kb.RH_CENTER), p),
            )
            for c in chords
        ]
        move_led = sum(kb._voice_leading_distance(b, a) for a, b in zip(led, led[1:], strict=False))
        move_fixed = sum(
            kb._voice_leading_distance(b, a) for a, b in zip(fixed, fixed[1:], strict=False)
        )
        assert move_led <= move_fixed
        total_leading += move_led
        total_fixed += move_fixed
    assert total_leading < 0.6 * total_fixed


def test_common_tone_is_kept_between_c_and_f() -> None:
    result = generate_keyboard(_progression())
    assert 72 in _notes_at(result.right_hand, 0.0) and 72 in _notes_at(result.right_hand, 2.0)


# --- Confiance, ambiguïté, timing -------------------------------------------


def test_notes_carry_the_chord_confidence_and_time() -> None:
    chords = (_c(0, confidence=0.35, ambiguous=True, start=1.5, duration=3.0),)
    result = generate_keyboard(chords)
    for note in (*result.right_hand.notes, *result.left_hand.notes):
        assert note.confidence == pytest.approx(0.35)
        assert note.start_seconds == 1.5 and note.duration_seconds == 3.0
        assert note.velocity == kb.NOTE_VELOCITY


def test_manual_chords_give_notes_without_confidence() -> None:
    result = generate_keyboard((_c(0, source=EstimationSource.MANUAL),))
    assert all(n.confidence is None for n in result.right_hand.notes)


def test_ambiguous_chords_are_included_by_default_and_skippable() -> None:
    chords = (_c(0, start=0.0), _c(5, start=2.0, ambiguous=True, confidence=0.1), _c(7, start=4.0))

    included = generate_keyboard(chords)
    skipped = generate_keyboard(chords, include_ambiguous=False)

    assert included.chord_count == 3 and included.skipped_ambiguous_count == 0
    assert skipped.chord_count == 2 and skipped.skipped_ambiguous_count == 1
    assert _notes_at(skipped.right_hand, 2.0) == []
    assert _notes_at(skipped.left_hand, 2.0) == []


def test_no_chords_gives_empty_tracks() -> None:
    result = generate_keyboard(())
    assert result.right_hand.notes == () and result.left_hand.notes == ()
    assert result.chord_count == 0


def test_generation_is_deterministic() -> None:
    assert generate_keyboard(_progression()) == generate_keyboard(_progression())
