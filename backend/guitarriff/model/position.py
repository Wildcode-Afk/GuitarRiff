"""Position musicale (mesure + temps) et son calcul.

`MusicalPosition` est une donnée **dérivée** : un `NoteEvent` brut, tel que
produit par une transcription audio, n'a qu'un `start_seconds` — sa position
en mesure/temps n'est calculable qu'une fois la carte de tempo/métrique du
`Song` connue. Voir `compute_position` ci-dessous (fonction pure) et
`Song.with_computed_positions` (`song.py`) pour le remplissage en lot.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from guitarriff.model.tempo import TempoChange, TimeSignatureChange


class MusicalPosition(BaseModel):
    """Position d'un événement dans la partition : mesure et temps, tous
    deux numérotés à partir de 1 (convention de notation musicale standard,
    pas 0-indexée)."""

    model_config = ConfigDict(frozen=True)

    bar: int = Field(ge=1)
    beat: float = Field(
        ge=1.0, description="Position dans la mesure, dans l'unité de la métrique active."
    )


def _active_tempo_bpm(time_seconds: float, tempo_changes: tuple[TempoChange, ...]) -> float:
    active = tempo_changes[0]
    for change in tempo_changes:
        if change.time_seconds <= time_seconds:
            active = change
        else:
            break
    return active.bpm


def _active_time_signature(
    time_seconds: float, time_signature_changes: tuple[TimeSignatureChange, ...]
) -> TimeSignatureChange:
    active = time_signature_changes[0]
    for change in time_signature_changes:
        if change.time_seconds <= time_seconds:
            active = change
        else:
            break
    return active


def compute_position(
    time_seconds: float,
    tempo_changes: tuple[TempoChange, ...],
    time_signature_changes: tuple[TimeSignatureChange, ...],
) -> MusicalPosition:
    """Calcule la position (mesure, temps) d'un instant donné.

    `tempo_changes` et `time_signature_changes` doivent chacun contenir au
    moins un élément à `time_seconds == 0.0` (invariant garanti par
    `Song`, voir `song.py`) — sans quoi la position avant le premier
    changement serait indéfinie.

    Algorithme : parcourt la timeline par segments délimités par chaque
    changement de tempo ou de métrique jusqu'à `time_seconds`, en convertissant
    la durée de chaque segment en temps (battements) selon le tempo et la
    métrique actifs sur ce segment, puis en comptant les mesures complètes.
    """

    if time_seconds < 0:
        raise ValueError("time_seconds doit être positif ou nul.")
    if not tempo_changes or tempo_changes[0].time_seconds != 0.0:
        raise ValueError("tempo_changes doit contenir une entrée à time_seconds == 0.0.")
    if not time_signature_changes or time_signature_changes[0].time_seconds != 0.0:
        raise ValueError("time_signature_changes doit contenir une entrée à time_seconds == 0.0.")

    breakpoints = sorted(
        {
            0.0,
            *(tc.time_seconds for tc in tempo_changes if tc.time_seconds <= time_seconds),
            *(ts.time_seconds for ts in time_signature_changes if ts.time_seconds <= time_seconds),
        }
    )

    bar = 1
    beat_in_bar = 1.0

    for index, segment_start in enumerate(breakpoints):
        segment_end = breakpoints[index + 1] if index + 1 < len(breakpoints) else time_seconds
        segment_duration = segment_end - segment_start
        if segment_duration <= 0:
            continue

        bpm = _active_tempo_bpm(segment_start, tempo_changes)
        signature = _active_time_signature(segment_start, time_signature_changes)
        seconds_per_beat = (60.0 / bpm) * signature.beat_seconds_factor
        beats_elapsed = segment_duration / seconds_per_beat

        beat_in_bar += beats_elapsed
        while beat_in_bar >= signature.numerator + 1:
            beat_in_bar -= signature.numerator
            bar += 1

    return MusicalPosition(bar=bar, beat=round(beat_in_bar, 6))
