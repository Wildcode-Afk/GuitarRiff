"""Profils d'instrument pour le mapping manche.

Un profil regroupe ce qui diffère d'un instrument à l'autre sans justifier
une copie du mapper : accordage par défaut, poids de la fonction de coût,
durée de silence au-delà de laquelle la position de la main est oubliée.

## Pourquoi un profil basse distinct

- La basse est quasi monophonique : la cohérence note à note (rester dans la
  même position, rejouer une note répétée au même endroit) prime sur le
  confort d'accord, d'où des poids plus forts pour le déplacement, le
  changement de corde.
- Les cases d'une basse sont plus larges que celles d'une guitare : un même
  écart en cases est un étirement plus difficile, d'où un poids d'écartement
  des doigts plus élevé.
- Un silence suffisamment long laisse au bassiste le temps de se
  repositionner : le coût de déplacement ne s'applique plus après lui.

**Ces valeurs sont un jugement heuristique de jouabilité**, comme celles du
profil guitare : elles n'ont été validées contre aucun corpus de lignes de
basse réelles. Elles sont ajustables (`CostWeights`) et ne prétendent pas
reconstituer le jeu d'un bassiste donné.
"""

from __future__ import annotations

from dataclasses import dataclass

from guitarriff.model import InstrumentKind
from guitarriff.tablature.cost import DEFAULT_WEIGHTS, CostWeights
from guitarriff.tablature.fretboard import STANDARD_BASS_TUNING, STANDARD_GUITAR_TUNING


@dataclass(frozen=True)
class MappingProfile:
    name: str
    default_tuning: tuple[int, ...]
    weights: CostWeights
    rest_reset_seconds: float | None


GUITAR_PROFILE = MappingProfile(
    name="guitar",
    default_tuning=STANDARD_GUITAR_TUNING,
    weights=DEFAULT_WEIGHTS,
    rest_reset_seconds=None,  # comportement de l'Étape 11 inchangé
)

BASS_PROFILE = MappingProfile(
    name="bass",
    default_tuning=STANDARD_BASS_TUNING,
    weights=CostWeights(
        movement_weight=1.5,
        span_weight=3.0,
        absolute_fret_weight=0.2,
        open_string_bonus=-0.5,
        string_change_weight=0.8,
    ),
    rest_reset_seconds=1.0,
)

_PROFILES = {
    InstrumentKind.GUITAR: GUITAR_PROFILE,
    InstrumentKind.BASS: BASS_PROFILE,
}


def profile_for(instrument: InstrumentKind) -> MappingProfile | None:
    """Profil de l'instrument, ou `None` s'il n'est pas à cordes frettées
    prises en charge (décision Q3 : guitare/basse uniquement)."""

    return _PROFILES.get(instrument)
