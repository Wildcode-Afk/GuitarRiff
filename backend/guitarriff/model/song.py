"""Song — le morceau musical complet, racine du modèle commun.

Le frontend ne doit jamais dépendre directement du format de sortie d'un
modèle de transcription (basic-pitch ou autre) : un `Song` sérialisé
(`model_dump()` / `model_dump_json()`) est le **seul** contrat exposé par
l'API pour représenter un morceau transcrit — voir docs/ARCHITECTURE.md.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from guitarriff.model.position import compute_position
from guitarriff.model.tempo import TempoChange, TimeSignatureChange
from guitarriff.model.track import Track

_ChangeT = TypeVar("_ChangeT", TempoChange, TimeSignatureChange)


class AudioMetadata(BaseModel):
    """Métadonnées de l'audio source dont ce `Song` a été transcrit — relie
    le modèle musical au fichier stocké (Étapes 4-6 : `acquisition/storage.py`)."""

    model_config = ConfigDict(frozen=True)

    source_file_id: str = Field(min_length=1)
    sample_rate: int = Field(gt=0)
    channels: int = Field(ge=1)
    original_filename: str | None = None
    source: str = "upload"
    source_url: str | None = None


def _default_tempo_changes() -> tuple[TempoChange, ...]:
    return (TempoChange(time_seconds=0.0, bpm=120.0),)


def _default_time_signature_changes() -> tuple[TimeSignatureChange, ...]:
    return (TimeSignatureChange(time_seconds=0.0, numerator=4, denominator=4),)


class Song(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1)
    title: str | None = None
    duration_seconds: float = Field(gt=0)
    audio: AudioMetadata
    tempo_changes: tuple[TempoChange, ...] = Field(default_factory=_default_tempo_changes)
    time_signature_changes: tuple[TimeSignatureChange, ...] = Field(
        default_factory=_default_time_signature_changes
    )
    tracks: tuple[Track, ...] = ()
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @field_validator("tempo_changes")
    @classmethod
    def _validate_tempo_changes(cls, value: tuple[TempoChange, ...]) -> tuple[TempoChange, ...]:
        return _validate_changes_start_at_zero_and_sorted(value, "tempo_changes")

    @field_validator("time_signature_changes")
    @classmethod
    def _validate_time_signature_changes(
        cls, value: tuple[TimeSignatureChange, ...]
    ) -> tuple[TimeSignatureChange, ...]:
        return _validate_changes_start_at_zero_and_sorted(value, "time_signature_changes")

    @model_validator(mode="after")
    def _validate_track_ids_unique(self) -> Song:
        ids = [track.id for track in self.tracks]
        if len(ids) != len(set(ids)):
            raise ValueError(
                "Les identifiants de piste (Track.id) doivent être uniques au sein d'un Song."
            )
        return self

    def with_computed_positions(self) -> Song:
        """Renvoie une copie de ce `Song` où chaque `NoteEvent`/`RhythmEvent`
        de chaque piste a sa `position` calculée à partir de
        `tempo_changes`/`time_signature_changes`.

        Fonction pure : ne modifie jamais `self` (modèle immuable) — utile
        pour une transcription brute (positions à `None`) une fois la carte
        de tempo connue.
        """

        new_tracks = []
        for track in self.tracks:
            new_notes = tuple(
                note.with_position(
                    compute_position(
                        note.start_seconds, self.tempo_changes, self.time_signature_changes
                    )
                )
                for note in track.notes
            )
            new_rhythm_events = tuple(
                event.with_position(
                    compute_position(
                        event.start_seconds, self.tempo_changes, self.time_signature_changes
                    )
                )
                for event in track.rhythm_events
            )
            new_tracks.append(
                track.model_copy(update={"notes": new_notes, "rhythm_events": new_rhythm_events})
            )
        return self.model_copy(update={"tracks": tuple(new_tracks)})


def _validate_changes_start_at_zero_and_sorted(
    changes: tuple[_ChangeT, ...], field_name: str
) -> tuple[_ChangeT, ...]:
    if not changes:
        raise ValueError(
            f"{field_name} ne peut pas être vide (il faut au moins l'entrée à time_seconds=0.0)."
        )
    if changes[0].time_seconds != 0.0:
        raise ValueError(f"{field_name} doit commencer par une entrée à time_seconds == 0.0.")
    for previous, current in zip(changes, changes[1:], strict=False):
        if current.time_seconds <= previous.time_seconds:
            raise ValueError(
                f"{field_name} doit être trié par time_seconds strictement croissant "
                f"(trouvé {previous.time_seconds} suivi de {current.time_seconds})."
            )
    return changes
