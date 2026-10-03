"""NoteEvent — le contrat unique entre une méthode de transcription et le
reste du pipeline (voir docs/ARCHITECTURE.md, principe 4).

## Unités et conventions

- `midi_pitch` : hauteur au format MIDI standard (0-127, 60 = do central / C4).
- `start_seconds` / `duration_seconds` : secondes depuis le début de l'audio
  — **pas** une position en mesure/temps (voir `position.py` pour la donnée
  dérivée correspondante).
- `velocity` : convention MIDI standard (0-127), pas une amplitude 0-1.
- `confidence` : optionnel, `[0.0, 1.0]`. Certaines méthodes de transcription
  (ex. import MIDI direct) ne fournissent aucune confiance — `None` est une
  valeur légitime, pas une erreur.

## Notes simultanées (accords)

Un accord n'est pas un objet séparé dans ce modèle : c'est simplement
plusieurs `NoteEvent` dont les intervalles `[start_seconds, start_seconds +
duration_seconds)` se chevauchent, sur la même piste. Le regroupement visuel
en accord est une responsabilité d'une étape de génération de tablature en
aval, pas de ce modèle.

## Silences

Un silence n'est pas non plus un objet explicite : c'est l'absence de
`NoteEvent` sur un intervalle de temps donné. Ce choix suit la convention
MIDI/`basic-pitch` (qui ne représentent que des événements note-on/note-off)
et évite une donnée redondante qui se désynchroniserait facilement des notes
réelles.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guitarriff.model.position import MusicalPosition


class InstrumentSpecificInfo(BaseModel):
    """Informations spécifiques à l'instrument, quand disponibles.

    Toujours optionnel dans `NoteEvent` : une transcription audio brute ne
    fournit jamais ces informations directement (une note transcrite n'a pas
    de corde ni de case tant qu'une étape de mapping manche ultérieure ne les
    lui a pas assignées — voir docs/ARCHITECTURE.md, pipeline étape 7a).
    """

    model_config = ConfigDict(frozen=True)

    string_index: int | None = Field(
        default=None,
        ge=0,
        description="Index de corde (0 = corde la plus grave du tuning de la Track).",
    )
    fret: int | None = Field(default=None, ge=0, le=36)

    @model_validator(mode="after")
    def _string_and_fret_together(self) -> InstrumentSpecificInfo:
        if (self.string_index is None) != (self.fret is None):
            raise ValueError(
                "string_index et fret doivent être renseignés ensemble ou absents ensemble."
            )
        return self


class NoteEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    midi_pitch: int = Field(ge=0, le=127)
    start_seconds: float = Field(ge=0)
    duration_seconds: float = Field(gt=0)
    velocity: int = Field(ge=0, le=127)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    position: MusicalPosition | None = Field(
        default=None,
        description="Calculée — voir position.compute_position. None tant que non calculée.",
    )
    instrument_info: InstrumentSpecificInfo | None = None

    @property
    def end_seconds(self) -> float:
        return self.start_seconds + self.duration_seconds

    def overlaps(self, other: NoteEvent) -> bool:
        """Vrai si les intervalles temporels de deux notes se chevauchent
        (utilisé pour détecter des notes simultanées — voir docstring du
        module)."""

        return self.start_seconds < other.end_seconds and other.start_seconds < self.end_seconds

    def with_position(self, position: MusicalPosition) -> NoteEvent:
        """Renvoie une copie avec `position` renseignée — fonction pure,
        l'instance d'origine n'est jamais modifiée (modèle immuable)."""

        return self.model_copy(update={"position": position})
