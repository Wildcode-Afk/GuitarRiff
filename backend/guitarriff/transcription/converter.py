"""Conversion des notes brutes de basic-pitch vers `NoteEvent` (modèle commun).

Fonction pure, testable avec des sorties simulées — aucune dépendance à
basic-pitch ni à un vrai modèle ici (voir `basic_pitch_adapter.py` pour
l'isolation de la bibliothèque elle-même).

## Correspondance des champs

- `amplitude` (basic-pitch, `[0.0, 1.0]`) devient à la fois :
  - `velocity` MIDI (`round(amplitude * 127)`, convention MIDI 0-127) ;
  - `confidence` (`amplitude` directement, déjà dans `[0.0, 1.0]`).
  C'est une simplification documentée : `amplitude` n'est pas conçue par
  basic-pitch comme une mesure de confiance au sens strict, mais c'est la
  seule grandeur fournie par le modèle corrélée à la certitude de détection,
  et c'est l'approche retenue dès le test de compatibilité de l'Étape 8.
"""

from __future__ import annotations

from guitarriff.logging_config import get_logger
from guitarriff.model import NoteEvent
from guitarriff.transcription.basic_pitch_adapter import RawNoteEvent

logger = get_logger(__name__)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def raw_notes_to_note_events(raw_notes: list[RawNoteEvent]) -> tuple[NoteEvent, ...]:
    """Convertit une liste de `RawNoteEvent` en `NoteEvent` du modèle commun.

    Filtre silencieusement (avec un avertissement journalisé) toute note à
    durée nulle ou négative : cela ne devrait jamais arriver avec les
    paramètres par défaut de basic-pitch (`minimum_note_length`), mais
    `NoteEvent` exige une durée strictement positive — défense en profondeur
    plutôt qu'un plantage sur une donnée de modèle inattendue.
    """

    notes = []
    dropped = 0
    for raw in raw_notes:
        duration = raw.end_seconds - raw.start_seconds
        if duration <= 0:
            dropped += 1
            continue
        amplitude = _clamp01(raw.amplitude)
        notes.append(
            NoteEvent(
                midi_pitch=raw.midi_pitch,
                start_seconds=raw.start_seconds,
                duration_seconds=duration,
                velocity=round(amplitude * 127),
                confidence=amplitude,
            )
        )

    if dropped:
        logger.warning("%d note(s) basic-pitch ignorée(s) (durée nulle ou négative).", dropped)

    return tuple(notes)
