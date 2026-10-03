"""Tests de `model/song.py` : validation des cartes de tempo/métrique,
unicité des identifiants de piste, calcul de position en lot, sérialisation
complète d'un morceau réaliste."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from guitarriff.model import (
    AudioMetadata,
    DrumPiece,
    InstrumentKind,
    NoteEvent,
    RhythmEvent,
    Song,
    TempoChange,
    TimeSignatureChange,
    Track,
)


def _audio_metadata(**overrides: object) -> AudioMetadata:
    defaults: dict[str, object] = dict(source_file_id="file-123", sample_rate=22050, channels=1)
    defaults.update(overrides)
    return AudioMetadata(**defaults)  # type: ignore[arg-type]


def test_minimal_song_gets_sensible_defaults() -> None:
    song = Song(duration_seconds=10.0, audio=_audio_metadata())
    assert song.tempo_changes[0].bpm == 120.0
    assert song.time_signature_changes[0].numerator == 4
    assert song.tracks == ()
    assert len(song.id) > 0


def test_duration_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Song(duration_seconds=0.0, audio=_audio_metadata())


def test_tempo_changes_must_start_at_zero() -> None:
    with pytest.raises(ValidationError, match="time_seconds == 0.0"):
        Song(
            duration_seconds=10.0,
            audio=_audio_metadata(),
            tempo_changes=(TempoChange(time_seconds=1.0, bpm=120.0),),
        )


def test_tempo_changes_must_be_strictly_increasing() -> None:
    with pytest.raises(ValidationError, match="croissant"):
        Song(
            duration_seconds=10.0,
            audio=_audio_metadata(),
            tempo_changes=(
                TempoChange(time_seconds=0.0, bpm=120.0),
                TempoChange(time_seconds=2.0, bpm=100.0),
                TempoChange(time_seconds=2.0, bpm=90.0),
            ),
        )


def test_time_signature_changes_must_start_at_zero() -> None:
    with pytest.raises(ValidationError, match="time_seconds == 0.0"):
        Song(
            duration_seconds=10.0,
            audio=_audio_metadata(),
            time_signature_changes=(
                TimeSignatureChange(time_seconds=1.0, numerator=4, denominator=4),
            ),
        )


def test_duplicate_track_ids_rejected() -> None:
    track_a = Track(id="dup", instrument=InstrumentKind.GUITAR, name="Guitare")
    track_b = Track(id="dup", instrument=InstrumentKind.BASS, name="Basse")
    with pytest.raises(ValidationError, match="uniques"):
        Song(duration_seconds=10.0, audio=_audio_metadata(), tracks=(track_a, track_b))


def test_song_is_frozen() -> None:
    song = Song(duration_seconds=10.0, audio=_audio_metadata())
    with pytest.raises(ValidationError):
        song.title = "Nouveau titre"


def test_with_computed_positions_fills_every_note_and_rhythm_event() -> None:
    notes = (NoteEvent(midi_pitch=60, start_seconds=0.5, duration_seconds=0.5, velocity=90),)
    rhythm_events = (
        RhythmEvent(
            drum_piece=DrumPiece.KICK, start_seconds=0.0, duration_seconds=0.0, velocity=100
        ),
    )
    track = Track(
        id="t1",
        instrument=InstrumentKind.GUITAR,
        name="Guitare",
        notes=notes,
        rhythm_events=rhythm_events,
    )
    song = Song(duration_seconds=10.0, audio=_audio_metadata(), tracks=(track,))

    assert song.tracks[0].notes[0].position is None  # pas encore calculée

    enriched = song.with_computed_positions()

    assert enriched.tracks[0].notes[0].position is not None
    assert enriched.tracks[0].notes[0].position.bar == 1
    assert enriched.tracks[0].rhythm_events[0].position is not None

    # Fonction pure : l'original n'est jamais modifié.
    assert song.tracks[0].notes[0].position is None


def test_with_computed_positions_returns_new_song_object() -> None:
    song = Song(duration_seconds=5.0, audio=_audio_metadata())
    enriched = song.with_computed_positions()
    assert enriched is not song
    assert enriched == song  # contenu identique (aucune piste à enrichir)


def test_full_realistic_song_serialization_round_trip() -> None:
    guitar_notes = (
        NoteEvent(
            midi_pitch=64, start_seconds=0.0, duration_seconds=0.5, velocity=90, confidence=0.95
        ),
        NoteEvent(
            midi_pitch=67, start_seconds=0.0, duration_seconds=0.5, velocity=85, confidence=0.88
        ),  # accord
        NoteEvent(midi_pitch=69, start_seconds=0.5, duration_seconds=0.5, velocity=92),
    )
    bass_notes = (NoteEvent(midi_pitch=40, start_seconds=0.0, duration_seconds=1.0, velocity=100),)
    drum_events = (
        RhythmEvent(
            drum_piece=DrumPiece.KICK, start_seconds=0.0, duration_seconds=0.0, velocity=110
        ),
        RhythmEvent(
            drum_piece=DrumPiece.HIHAT_CLOSED, start_seconds=0.25, duration_seconds=0.0, velocity=70
        ),
    )

    guitar = Track(
        id="guitar-1",
        instrument=InstrumentKind.GUITAR,
        name="Guitare rythmique",
        tuning=(40, 45, 50, 55, 59, 64),
        notes=guitar_notes,
    )
    bass = Track(
        id="bass-1",
        instrument=InstrumentKind.BASS,
        name="Basse",
        tuning=(28, 33, 38, 43),
        notes=bass_notes,
    )
    drums = Track(
        id="drums-1", instrument=InstrumentKind.DRUMS, name="Batterie", rhythm_events=drum_events
    )

    song = Song(
        title="Morceau de test",
        duration_seconds=60.0,
        audio=AudioMetadata(
            source_file_id="abc-123",
            sample_rate=22050,
            channels=1,
            original_filename="demo.wav",
            source="upload",
        ),
        tempo_changes=(
            TempoChange(time_seconds=0.0, bpm=96.0),
            TempoChange(time_seconds=30.0, bpm=120.0),
        ),
        time_signature_changes=(TimeSignatureChange(time_seconds=0.0, numerator=4, denominator=4),),
        tracks=(guitar, bass, drums),
    ).with_computed_positions()

    payload = song.model_dump_json()
    restored = Song.model_validate_json(payload)

    assert restored == song
    assert len(restored.tracks) == 3
    assert restored.tracks[0].notes[0].position is not None
    assert restored.tracks[2].rhythm_events[0].drum_piece == DrumPiece.KICK


def test_simultaneous_notes_are_representable_without_special_object() -> None:
    """Un accord n'est qu'un ensemble de NoteEvent qui se chevauchent — pas
    besoin d'un objet Chord dédié (voir docstring de note_event.py)."""

    chord = (
        NoteEvent(midi_pitch=60, start_seconds=1.0, duration_seconds=1.0, velocity=80),
        NoteEvent(midi_pitch=64, start_seconds=1.0, duration_seconds=1.0, velocity=80),
        NoteEvent(midi_pitch=67, start_seconds=1.0, duration_seconds=1.0, velocity=80),
    )
    track = Track(id="t1", instrument=InstrumentKind.PIANO, name="Piano", notes=chord)
    song = Song(duration_seconds=5.0, audio=_audio_metadata(), tracks=(track,))

    assert len(song.tracks[0].notes) == 3
    assert all(n.overlaps(chord[0]) for n in chord)


def test_silence_is_simply_absence_of_notes_in_a_time_range() -> None:
    """Un silence n'est pas un objet : un intervalle sans NoteEvent est déjà
    un silence valide, sans aucune construction spéciale requise."""

    notes = (
        NoteEvent(midi_pitch=60, start_seconds=0.0, duration_seconds=1.0, velocity=80),
        # Silence implicite de 1.0 à 3.0s.
        NoteEvent(midi_pitch=62, start_seconds=3.0, duration_seconds=1.0, velocity=80),
    )
    track = Track(id="t1", instrument=InstrumentKind.GUITAR, name="Guitare", notes=notes)

    gap_start, gap_end = notes[0].end_seconds, notes[1].start_seconds
    assert gap_end - gap_start == 2.0
    assert all(
        not (gap_start < n.start_seconds < gap_end) for n in track.notes if n is not notes[1]
    )
