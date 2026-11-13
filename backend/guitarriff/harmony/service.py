"""Orchestration de l'analyse harmonique (Étape 13), sur le `Song` persisté.

Deux fonctionnalités distinctes, à ne pas confondre :

1. **Obtenir des accords** — estimés à partir de l'audio (`estimate_chords`),
   déduits de notes déjà transcrites (`chords_from_notes`), ou fournis /
   corrigés par l'utilisateur (`set_manual_chords`). Le résultat est toujours
   `Song.chords`, avec `source` (détecté / manuel), confiance et ambiguïté.
2. **Générer une piste clavier** (`generate_keyboard`) à partir de ces accords,
   quelle qu'en soit l'origine.

Les positions rythmiques (mesure/temps) ne sont **pas persistées** : elles sont
dérivées de la carte de tempo/métrique et deviendraient fausses si celle-ci
changeait ; elles sont calculées à la volée pour les réponses.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.audio.ffmpeg import probe_audio
from guitarriff.audio.sources import resolve_source_path
from guitarriff.config import Settings
from guitarriff.errors import (
    InvalidChordsError,
    InvalidChordSourceError,
    NoChordsError,
    NotFoundError,
)
from guitarriff.harmony import analyzer, from_notes, keyboard
from guitarriff.model import AudioMetadata, ChordEvent, EstimationSource, InstrumentKind, Song
from guitarriff.model.chord import validate_chords_non_overlapping

KEYBOARD_TRACK_IDS = (keyboard.RIGHT_HAND_TRACK_ID, keyboard.LEFT_HAND_TRACK_ID)
LOW_CONFIDENCE_THRESHOLD = 0.5


@dataclass(frozen=True)
class ChordsOutcome:
    song: Song
    ambiguous_count: int


@dataclass(frozen=True)
class KeyboardOutcome:
    song: Song
    chord_count: int
    skipped_ambiguous_count: int
    right_hand_note_count: int
    left_hand_note_count: int
    low_confidence_chord_count: int


def _ensure_song(
    file_id: str, settings: Settings, storage: AudioFileStorage, source_path: Path
) -> Song:
    existing = storage.read_song(file_id)
    if existing is not None:
        return existing

    record = storage.get(file_id)
    probe = probe_audio(source_path, timeout_seconds=settings.ffmpeg_timeout_seconds)
    return Song(
        duration_seconds=probe.duration_seconds,
        audio=AudioMetadata(
            source_file_id=file_id,
            sample_rate=probe.sample_rate,
            channels=probe.channels,
            original_filename=record.original_filename,
            source=record.source,
            source_url=record.source_url,
        ),
    )


def _store_chords(
    song: Song, chords: tuple[ChordEvent, ...], file_id: str, storage: AudioFileStorage
) -> ChordsOutcome:
    try:
        validate_chords_non_overlapping(chords)
    except ValueError as exc:
        raise InvalidChordsError(str(exc)) from exc
    updated = song.model_copy(update={"chords": chords})
    storage.write_song(file_id, updated)
    return ChordsOutcome(song=updated, ambiguous_count=sum(1 for c in chords if c.ambiguous))


def estimate_chords(
    file_id: str, source: str, settings: Settings, storage: AudioFileStorage
) -> ChordsOutcome:
    source_path = resolve_source_path(file_id, source, storage)
    result = analyzer.estimate_chords(
        source_path, timeout_seconds=settings.chord_analysis_timeout_seconds
    )
    song = _ensure_song(file_id, settings, storage, source_path)
    return _store_chords(song, result.chords, file_id, storage)


def chords_from_notes(
    file_id: str, instrument: InstrumentKind, storage: AudioFileStorage
) -> ChordsOutcome:
    if instrument == InstrumentKind.DRUMS:
        raise InvalidChordSourceError(
            "La batterie n'a pas de hauteurs : aucun accord ne peut en être déduit.",
            details={"instrument": instrument.value},
        )
    song = storage.read_song(file_id)
    if song is None:
        raise NotFoundError(
            "Aucune transcription n'existe encore pour ce fichier.", details={"file_id": file_id}
        )
    track = next((t for t in song.tracks if t.instrument == instrument), None)
    if track is None:
        raise NotFoundError(
            "Aucune piste de cet instrument n'a été transcrite pour ce fichier.",
            details={"file_id": file_id, "instrument": instrument.value},
        )
    return _store_chords(song, from_notes.chords_from_notes(track.notes), file_id, storage)


def set_manual_chords(
    file_id: str, chords: tuple[ChordEvent, ...], settings: Settings, storage: AudioFileStorage
) -> ChordsOutcome:
    """Remplace **tous** les accords par ceux de l'utilisateur. Chaque accord
    doit être `MANUAL` : un accord confirmé ou corrigé par l'utilisateur est
    certain par définition (ni confiance, ni ambiguïté)."""

    if any(c.source != EstimationSource.MANUAL for c in chords):
        raise InvalidChordsError(
            "Les accords fournis par l'utilisateur doivent être de source 'manual'."
        )

    song = storage.read_song(file_id)
    if song is None:
        normalized = storage.normalized_path(file_id)
        source_path = normalized if normalized.is_file() else storage.audio_path(file_id)
        song = _ensure_song(file_id, settings, storage, source_path)
    return _store_chords(song, chords, file_id, storage)


def generate_keyboard(
    file_id: str, include_ambiguous: bool, storage: AudioFileStorage
) -> KeyboardOutcome:
    song = storage.read_song(file_id)
    if song is None or not song.chords:
        raise NoChordsError(
            "Aucun accord n'est disponible pour ce fichier : estimez-les "
            "(POST .../estimate-chords), déduisez-les de notes (POST .../chords-from-notes) "
            "ou définissez-les (PUT .../chords) d'abord.",
            details={"file_id": file_id},
        )

    result = keyboard.generate_keyboard(song.chords, include_ambiguous=include_ambiguous)
    kept_tracks = tuple(t for t in song.tracks if t.id not in KEYBOARD_TRACK_IDS)
    updated = song.model_copy(
        update={"tracks": (*kept_tracks, result.right_hand, result.left_hand)}
    )
    storage.write_song(file_id, updated)

    low_confidence = sum(
        1
        for c in song.chords
        if (include_ambiguous or not c.ambiguous)
        and c.confidence is not None
        and c.confidence < LOW_CONFIDENCE_THRESHOLD
    )
    return KeyboardOutcome(
        song=updated,
        chord_count=result.chord_count,
        skipped_ambiguous_count=result.skipped_ambiguous_count,
        right_hand_note_count=len(result.right_hand.notes),
        left_hand_note_count=len(result.left_hand.notes),
        low_confidence_chord_count=low_confidence,
    )
