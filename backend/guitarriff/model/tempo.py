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

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from guitarriff.model.enums import EstimationSource

VALID_DENOMINATORS = frozenset({1, 2, 4, 8, 16, 32, 64})


def _reject_confidence_on_manual(value: float | None, info: ValidationInfo) -> float | None:
    source = info.data.get("source")
    if source == EstimationSource.MANUAL and value is not None:
        raise ValueError(
            "confidence doit être None pour une valeur 'manual' (fournie par l'utilisateur)."
        )
    return value


class TempoChange(BaseModel):
    """Un changement de tempo prenant effet à `time_seconds`.

    `source` distingue une valeur détectée automatiquement (analyse audio,
    Étape 10) d'une valeur fournie ou corrigée par l'utilisateur — voir
    `rhythm/analyzer.py` pour la détection et `rhythm/service.py` pour la
    construction d'une valeur manuelle. `confidence` n'a de sens que pour
    une valeur `DETECTED` ; toujours `None` pour une valeur `MANUAL` (une
    correction de l'utilisateur n'a pas de "confiance", elle est certaine
    par définition — voir le validateur ci-dessous).
    """

    model_config = ConfigDict(frozen=True)

    time_seconds: float = Field(ge=0)
    bpm: float = Field(gt=0, description="Battements (noires) par minute.")
    source: EstimationSource = EstimationSource.DETECTED
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("confidence")
    @classmethod
    def _no_confidence_on_manual_value(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        return _reject_confidence_on_manual(value, info)


class TimeSignatureChange(BaseModel):
    """Un changement de métrique prenant effet à `time_seconds`. Voir
    `TempoChange` pour la convention `source`/`confidence`."""

    model_config = ConfigDict(frozen=True)

    time_seconds: float = Field(ge=0)
    numerator: int = Field(ge=1, description="Nombre de temps par mesure.")
    denominator: int = Field(
        description="Valeur de la note correspondant à un temps (doit être une puissance de 2)."
    )
    source: EstimationSource = EstimationSource.DETECTED
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("confidence")
    @classmethod
    def _no_confidence_on_manual_value(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        return _reject_confidence_on_manual(value, info)

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
