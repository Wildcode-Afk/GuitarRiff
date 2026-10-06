"""Orchestration de l'analyse rythmique et des corrections manuelles.

Met à jour le `Song` persisté pour un fichier (créé si nécessaire, comme pour
la transcription — Étape 9). Trois opérations distinctes, pour que la
provenance (détectée vs manuelle) ne soit jamais ambiguë :

- `analyze` : détection automatique (tempo, battements, changements de
  tempo) — remplace entièrement `tempo_changes` par le résultat, `source`
  toujours `DETECTED`. La métrique n'est **jamais** déduite par cette
  fonction : une métrique par défaut (4/4, `confidence=None`) est appliquée
  si aucune métrique manuelle n'a déjà été définie, conformément à la
  consigne de ne pas déduire une métrique certaine d'une estimation
  incertaine.
- `set_manual_tempo` / `set_manual_time_signature` : remplacent la carte
  correspondante par une unique valeur `MANUAL`, fournie par l'utilisateur.
"""

from __future__ import annotations

from dataclasses import dataclass

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.config import Settings
from guitarriff.errors import AudioNotNormalizedError
from guitarriff.model import AudioMetadata, EstimationSource, Song, TempoChange, TimeSignatureChange
from guitarriff.rhythm.analyzer import RhythmAnalysisResult, analyze_rhythm

DEFAULT_TIME_SIGNATURE_NUMERATOR = 4
DEFAULT_TIME_SIGNATURE_DENOMINATOR = 4


@dataclass(frozen=True)
class RhythmAnalysisOutcome:
    song: Song
    beat_times: tuple[float, ...]
    confidence: float
    notes: str


def analyze(file_id: str, settings: Settings, storage: AudioFileStorage) -> RhythmAnalysisOutcome:
    record = storage.get(file_id)
    normalized_path = storage.normalized_path(file_id)
    if not record.normalized or not normalized_path.is_file():
        raise AudioNotNormalizedError(
            "Ce fichier doit d'abord être normalisé (POST .../normalize) avant l'analyse.",
            details={"file_id": file_id},
        )

    result: RhythmAnalysisResult = analyze_rhythm(
        normalized_path, timeout_seconds=settings.rhythm_analysis_timeout_seconds
    )

    tempo_changes = tuple(
        TempoChange(
            time_seconds=segment.start_seconds,
            bpm=segment.bpm,
            source=EstimationSource.DETECTED,
            confidence=result.confidence,
        )
        for segment in result.tempo_segments
    )

    song = storage.read_song(file_id)
    if song is None:
        song = Song(
            duration_seconds=result.duration_seconds,
            audio=AudioMetadata(
                source_file_id=file_id,
                sample_rate=record.normalized_sample_rate or 22050,
                channels=record.normalized_channels or 1,
                original_filename=record.original_filename,
                source=record.source,
                source_url=record.source_url,
            ),
            tempo_changes=tempo_changes,
            time_signature_changes=_default_time_signature(),
        )
    else:
        # Conserve une métrique déjà définie manuellement (voir
        # `set_manual_time_signature`) ; sinon applique le défaut non
        # confirmé — jamais une métrique "détectée" par cette fonction.
        existing_signature = song.time_signature_changes
        keep_existing_signature = existing_signature[0].source == EstimationSource.MANUAL
        song = song.model_copy(
            update={
                "tempo_changes": tempo_changes,
                "time_signature_changes": existing_signature
                if keep_existing_signature
                else _default_time_signature(),
            }
        )

    storage.write_song(file_id, song)

    return RhythmAnalysisOutcome(
        song=song,
        beat_times=result.beat_times,
        confidence=result.confidence,
        notes=_build_notes(len(tempo_changes)),
    )


def set_manual_tempo(
    file_id: str, bpm: float, settings: Settings, storage: AudioFileStorage
) -> Song:
    song = _require_song_or_bootstrap(file_id, settings, storage)
    new_tempo = (
        TempoChange(time_seconds=0.0, bpm=bpm, source=EstimationSource.MANUAL, confidence=None),
    )
    song = song.model_copy(update={"tempo_changes": new_tempo})
    storage.write_song(file_id, song)
    return song


def set_manual_time_signature(
    file_id: str, numerator: int, denominator: int, settings: Settings, storage: AudioFileStorage
) -> Song:
    song = _require_song_or_bootstrap(file_id, settings, storage)
    new_signature = (
        TimeSignatureChange(
            time_seconds=0.0,
            numerator=numerator,
            denominator=denominator,
            source=EstimationSource.MANUAL,
            confidence=None,
        ),
    )
    song = song.model_copy(update={"time_signature_changes": new_signature})
    storage.write_song(file_id, song)
    return song


def _require_song_or_bootstrap(file_id: str, settings: Settings, storage: AudioFileStorage) -> Song:
    """Pour une correction manuelle sur un fichier sans transcription ni
    analyse préalable, crée un `Song` minimal plutôt que d'échouer —
    l'utilisateur doit pouvoir fixer un tempo avant même toute détection."""

    song = storage.read_song(file_id)
    if song is not None:
        return song

    record = storage.get(file_id)
    normalized_path = storage.normalized_path(file_id)
    if not record.normalized or not normalized_path.is_file():
        raise AudioNotNormalizedError(
            "Ce fichier doit d'abord être normalisé (POST .../normalize) avant ce réglage.",
            details={"file_id": file_id},
        )
    duration = record.duration_seconds or 0.0
    if duration <= 0.0:
        from guitarriff.audio.ffmpeg import probe_audio

        duration = probe_audio(
            normalized_path, timeout_seconds=settings.ffmpeg_timeout_seconds
        ).duration_seconds

    return Song(
        duration_seconds=duration,
        audio=AudioMetadata(
            source_file_id=file_id,
            sample_rate=record.normalized_sample_rate or 22050,
            channels=record.normalized_channels or 1,
            original_filename=record.original_filename,
            source=record.source,
            source_url=record.source_url,
        ),
    )


def _default_time_signature() -> tuple[TimeSignatureChange, ...]:
    return (
        TimeSignatureChange(
            time_seconds=0.0,
            numerator=DEFAULT_TIME_SIGNATURE_NUMERATOR,
            denominator=DEFAULT_TIME_SIGNATURE_DENOMINATOR,
            source=EstimationSource.DETECTED,
            confidence=None,
        ),
    )


def _build_notes(tempo_change_count: int) -> str:
    base = (
        "Tempo et battements détectés automatiquement à partir de l'audio. "
        "La métrique n'est pas déduite de l'analyse audio (aucun détecteur "
        "fiable disponible) : une métrique par défaut (4/4) est appliquée "
        "jusqu'à correction manuelle (POST .../time-signature)."
    )
    if tempo_change_count > 1:
        base += f" {tempo_change_count} segments de tempo distincts détectés."
    return base
