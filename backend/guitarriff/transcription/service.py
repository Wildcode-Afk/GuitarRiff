"""Orchestration de la transcription : résout la source audio (mélange
normalisé ou piste séparée déjà calculée), lance basic-pitch, convertit le
résultat et met à jour le `Song` persisté pour ce fichier.

Préfère les pistes séparées au mélange complet quand c'est pertinent : voir
`_build_disclaimer` ci-dessous, toujours renvoyé à l'appelant plutôt que
laissé à la seule documentation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.audio.ffmpeg import probe_audio
from guitarriff.config import Settings
from guitarriff.errors import (
    AudioNotNormalizedError,
    InvalidInstrumentForTranscriptionError,
    SeparatedStemNotFoundError,
)
from guitarriff.model import AudioMetadata, Clef, InstrumentKind, Song, Track, TrackDisplaySettings
from guitarriff.transcription.basic_pitch_adapter import run_basic_pitch
from guitarriff.transcription.converter import raw_notes_to_note_events

# Décision Q3 (docs/TECHNICAL_DECISIONS.md) : MVP limité à guitare/basse.
_SUPPORTED_INSTRUMENTS = (InstrumentKind.GUITAR, InstrumentKind.BASS)

_TRACK_NAMES = {InstrumentKind.GUITAR: "Guitare", InstrumentKind.BASS: "Basse"}

# Ordre de recherche des modes de séparation en cache pour une piste donnée
# (voir separation/models.py) — htdemucs_6s d'abord, seul mode à isoler une
# piste "guitar" dédiée.
_SEPARATION_MODES_SEARCH_ORDER = ("htdemucs_6s", "htdemucs")


@dataclass(frozen=True)
class TranscriptionResult:
    song: Song
    track_id: str
    notes: str


def transcribe(
    file_id: str,
    instrument: InstrumentKind,
    source: str,
    settings: Settings,
    storage: AudioFileStorage,
) -> TranscriptionResult:
    if instrument not in _SUPPORTED_INSTRUMENTS:
        raise InvalidInstrumentForTranscriptionError(
            "La transcription est limitée à guitare et basse pour le MVP (décision Q3).",
            details={
                "instrument": instrument.value,
                "supported": [i.value for i in _SUPPORTED_INSTRUMENTS],
            },
        )

    record = storage.get(file_id)
    source_path = _resolve_source_path(file_id, source, storage)

    probe = probe_audio(source_path, timeout_seconds=settings.ffmpeg_timeout_seconds)

    raw_notes = run_basic_pitch(source_path, timeout_seconds=settings.transcription_timeout_seconds)
    notes = raw_notes_to_note_events(raw_notes)

    track = Track(
        id=instrument.value,
        instrument=instrument,
        name=_TRACK_NAMES[instrument],
        notes=notes,
        display=TrackDisplaySettings(clef=Clef.TAB),
    )

    song = storage.read_song(file_id)
    if song is None:
        song = Song(
            duration_seconds=probe.duration_seconds,
            audio=AudioMetadata(
                source_file_id=file_id,
                sample_rate=probe.sample_rate,
                channels=probe.channels,
                original_filename=record.original_filename,
                source=record.source,
                source_url=record.source_url,
            ),
            tracks=(track,),
        )
    else:
        remaining_tracks = tuple(t for t in song.tracks if t.id != track.id)
        song = song.model_copy(update={"tracks": (*remaining_tracks, track)})

    storage.write_song(file_id, song)

    return TranscriptionResult(
        song=song, track_id=track.id, notes=_build_disclaimer(instrument, source)
    )


def _resolve_source_path(file_id: str, source: str, storage: AudioFileStorage) -> Path:
    if source == "mixture":
        record = storage.get(file_id)
        normalized_path = storage.normalized_path(file_id)
        if not record.normalized or not normalized_path.is_file():
            raise AudioNotNormalizedError(
                "Ce fichier doit d'abord être normalisé (POST .../normalize) "
                "avant une transcription sur le mélange complet.",
                details={"file_id": file_id},
            )
        return normalized_path

    for mode in _SEPARATION_MODES_SEARCH_ORDER:
        candidate = storage.separated_dir(file_id, mode) / f"{source}.wav"
        if candidate.is_file():
            return candidate

    raise SeparatedStemNotFoundError(
        "Cette piste séparée n'a pas encore été calculée (POST .../separate d'abord).",
        details={"file_id": file_id, "requested_stem": source},
    )


def _build_disclaimer(instrument: InstrumentKind, source: str) -> str:
    base = (
        "basic-pitch est un modèle de détection de hauteur polyvalent : il ne reconnaît jamais "
        "parfaitement un instrument, et les résultats peuvent inclure des notes manquées, des "
        "notes fantômes ou des hauteurs erronées — en particulier sur de l'audio polyphonique "
        "ou saturé."
    )
    if source == "mixture":
        return (
            base
            + " Transcription effectuée sur le mélange complet : la précision est généralement "
            "nettement meilleure sur une piste déjà séparée (POST .../separate) quand plusieurs "
            "instruments sont présents."
        )
    if source == "other":
        return (
            base
            + " Transcription effectuée sur la piste 'other' de la séparation : elle contient la "
            "guitare mélangée avec d'autres instruments non isolés (claviers, synthés) — ce n'est "
            "pas une guitare isolée (voir docs/MODELS.md)."
        )
    return base
