"""Orchestration du mapping manche et du rendu de tablature, sur le `Song`
persisté pour un fichier (Étape 9) — guitare (Étape 11) et basse (Étape 12).

Le profil de l'instrument (`profiles.py`) fournit l'accordage par défaut, les
poids de la fonction de coût et la règle de réinitialisation après silence :
le mapper lui-même (`mapper.py`) est le même pour les deux instruments.
"""

from __future__ import annotations

from dataclasses import dataclass

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.errors import (
    FretboardNotMappedError,
    InvalidInstrumentForFretboardMappingError,
    NotFoundError,
)
from guitarriff.model import InstrumentKind, Song, Track
from guitarriff.tablature.fretboard import DEFAULT_MAX_FRET, FretboardConfig
from guitarriff.tablature.mapper import MappingResult, map_track_to_fretboard
from guitarriff.tablature.profiles import MappingProfile, profile_for
from guitarriff.tablature.render import DEFAULT_MAX_WIDTH, TabRendering, render_ascii_tab

_SUPPORTED = (InstrumentKind.GUITAR, InstrumentKind.BASS)

# Durée d'un temps utilisée pour matérialiser les silences dans le rendu
# lorsque le Song ne fournit aucun tempo exploitable (ne devrait pas arriver :
# `Song` a toujours au moins un `TempoChange`).
_FALLBACK_BPM = 120.0


@dataclass(frozen=True)
class FretboardMappingOutcome:
    song: Song
    placed_count: int
    unplaced_count: int
    unplaced_reasons: tuple[str, ...]


def _require_profile(instrument: InstrumentKind) -> MappingProfile:
    profile = profile_for(instrument)
    if profile is None:
        raise InvalidInstrumentForFretboardMappingError(
            "Le mapping manche est limité à guitare et basse pour le MVP (décision Q3).",
            details={"instrument": instrument.value, "supported": [i.value for i in _SUPPORTED]},
        )
    return profile


def _load_song_and_track(
    file_id: str, instrument: InstrumentKind, storage: AudioFileStorage
) -> tuple[Song, Track]:
    song = storage.read_song(file_id)
    if song is None:
        raise NotFoundError(
            "Aucune transcription n'existe encore pour ce fichier.",
            details={"file_id": file_id},
        )
    track = next((t for t in song.tracks if t.instrument == instrument), None)
    if track is None:
        raise NotFoundError(
            "Aucune piste de cet instrument n'a encore été transcrite pour ce fichier.",
            details={"file_id": file_id, "instrument": instrument.value},
        )
    return song, track


def map_fretboard(
    file_id: str,
    instrument: InstrumentKind,
    storage: AudioFileStorage,
    *,
    tuning: tuple[int, ...] | None = None,
    capo_fret: int = 0,
    max_fret: int = DEFAULT_MAX_FRET,
) -> FretboardMappingOutcome:
    profile = _require_profile(instrument)
    song, track = _load_song_and_track(file_id, instrument, storage)

    config = FretboardConfig(
        tuning=tuning or profile.default_tuning, capo_fret=capo_fret, max_fret=max_fret
    )
    result: MappingResult = map_track_to_fretboard(
        track, config, profile.weights, rest_reset_seconds=profile.rest_reset_seconds
    )

    remaining_tracks = tuple(t for t in song.tracks if t.id != track.id)
    updated_song = song.model_copy(update={"tracks": (*remaining_tracks, result.track)})
    storage.write_song(file_id, updated_song)

    return FretboardMappingOutcome(
        song=updated_song,
        placed_count=result.placed_count,
        unplaced_count=len(result.unplaced),
        unplaced_reasons=tuple(u.reason for u in result.unplaced),
    )


def render_tablature(
    file_id: str,
    instrument: InstrumentKind,
    storage: AudioFileStorage,
    *,
    max_width: int = DEFAULT_MAX_WIDTH,
) -> TabRendering:
    """Rend en ASCII la piste déjà mappée de `instrument`. Lecture seule : le
    `Song` persisté n'est pas modifié (les positions musicales servant aux
    barres de mesure sont calculées à la volée)."""

    _require_profile(instrument)
    song, track = _load_song_and_track(file_id, instrument, storage)

    if track.tuning is None:
        raise FretboardNotMappedError(
            "Cette piste n'a pas encore été mappée sur le manche (POST .../map-fretboard d'abord).",
            details={"file_id": file_id, "instrument": instrument.value},
        )

    with_positions = song.with_computed_positions()
    track_with_positions = next(t for t in with_positions.tracks if t.id == track.id)

    bpm = song.tempo_changes[0].bpm if song.tempo_changes else _FALLBACK_BPM
    return render_ascii_tab(track_with_positions, beat_seconds=60.0 / bpm, max_width=max_width)
