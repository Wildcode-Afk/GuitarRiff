"""Tempo et métrique, et leurs changements au cours du morceau.

## Convention temporelle (importante, lire avant de modifier ce fichier)

Tous les changements (tempo, métrique) sont ancrés par `time_seconds` —
**jamais par un numéro de mesure**. Ancrer par numéro de mesure créerait une
dépendance circulaire : savoir à quelle mesure on se trouve à un instant
donné nécessite déjà de connaître l'historique des tempos et métriques
précédents. `time_seconds` est le seul axe de référence absolu du modèle ;
la position en mesure/temps (`MusicalPosition`, voir `position.py`) en est
toujours une donnée **dérivée**, calculée à partir de ces changements.

## Convention BPM (importante)

`TempoChange.bpm` suit la convention MIDI/DAW standard : un battement = une
**noire**, quelle que soit la métrique active (y compris en 6/8, 7/8, etc.).
C'est la convention la plus répandue dans les formats d'échange musicaux
(MIDI, MusicXML) et celle qu'utilisera l'export MIDI d'une étape ultérieure.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_DENOMINATORS = frozenset({1, 2, 4, 8, 16, 32, 64})


class TempoChange(BaseModel):
    """Un changement de tempo prenant effet à `time_seconds`."""

    model_config = ConfigDict(frozen=True)

    time_seconds: float = Field(ge=0)
    bpm: float = Field(gt=0, description="Battements (noires) par minute.")


class TimeSignatureChange(BaseModel):
    """Un changement de métrique prenant effet à `time_seconds`."""

    model_config = ConfigDict(frozen=True)

    time_seconds: float = Field(ge=0)
    numerator: int = Field(ge=1, description="Nombre de temps par mesure.")
    denominator: int = Field(
        description="Valeur de la note correspondant à un temps (doit être une puissance de 2)."
    )

    @property
    def beat_seconds_factor(self) -> float:
        """Facteur par lequel une noire doit être multipliée pour obtenir la
        durée d'un temps de cette métrique (ex. 0.5 en 4/8 : un temps = une
        croche = une demi-noire)."""

        return 4.0 / self.denominator

    @field_validator("denominator")
    @classmethod
    def _check_denominator_is_power_of_two(cls, value: int) -> int:
        if value not in VALID_DENOMINATORS:
            raise ValueError(
                f"denominator doit être une puissance de 2 parmi {sorted(VALID_DENOMINATORS)}, "
                f"reçu {value}."
            )
        return value
