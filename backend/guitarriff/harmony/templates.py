"""Modèles d'accords et classement par similarité (fonctions pures, NumPy).

Chaque accord est un vecteur binaire de 12 classes de hauteur (1 pour chaque
note de l'accord). Un vecteur observé (chroma d'un segment audio, ou ensemble
de classes de hauteur de notes transcrites) est comparé à tous les modèles par
similarité cosinus ; le meilleur candidat et ses concurrents proches sont
renvoyés. Les seuils de `assess` (marge d'ambiguïté, marge de pleine
confiance) sont des choix heuristiques, calibrés sur des signaux synthétiques
— voir `analyzer.py` et docs/ARCHITECTURE.md § 10.

## Ambiguïtés inévitables du vocabulaire

Certains accords ont exactement les mêmes classes de hauteur : `Csus2` =
`Gsus4`, et `Caug` = `Eaug` = `G#aug`. Aucune analyse de l'audio ne peut les
distinguer sans information de basse ou de contexte : ils obtiennent des
scores identiques et sont donc signalés comme ambigus, avec leur équivalent en
alternative. De même, un accord de septième et sa triade s'emboîtent
(`Cdim` ⊂ `G#7`, `C` ⊂ `Cmaj7`) : quand la septième est discrète, les deux
lectures sont proches.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

import numpy as np

from guitarriff.model import ChordCandidate, ChordQuality
from guitarriff.model.chord import CHORD_INTERVALS

ALL_QUALITIES: tuple[ChordQuality, ...] = tuple(ChordQuality)
# L'estimation audio n'inclut pas la quinte seule (POWER) dans le classement
# libre : sur un signal harmonique, une seule note avec ses harmoniques
# ressemble à une quinte — voir `analyzer.py` pour son traitement dédié.
AUDIO_QUALITIES: tuple[ChordQuality, ...] = tuple(
    q for q in ChordQuality if q != ChordQuality.POWER
)

# Bonus appliqué à un candidat dont la fondamentale est la basse observée,
# **uniquement pour ordonner** les candidats (départager Csus2 / Gsus4, dont les
# notes sont identiques). Les scores renvoyés et la marge d'ambiguïté restent
# ceux de la similarité brute : la basse aide à choisir une lecture sans jamais
# faire croire que l'autre est exclue.
BASS_ROOT_BONUS = 0.03

AMBIGUITY_MARGIN = 0.08

# Une quinte seule (« power chord ») n'a pas de tierce : majeur ou mineur sont
# indécidables, et — sur l'audio — une note seule avec ses harmoniques lui
# ressemble. Toujours ambiguë, confiance plafonnée.
POWER_CONFIDENCE = 0.4

# Marge minimale d'une correspondance exacte : une triade parfaitement observée
# n'est battue que par l'accord de septième correspondant (similarité cosinus
# √(3/4) = 0.866, soit 1 - 0.866 = 0.134 d'écart). Une marge de 0.13 suffit donc
# à atteindre la pleine confiance pour un accord net.
FULL_CONFIDENCE_MARGIN = 0.13
ALTERNATIVE_WINDOW = 0.15
MAX_ALTERNATIVES = 3


@cache
def template_bank(
    qualities: tuple[ChordQuality, ...],
) -> tuple[tuple[tuple[int, ChordQuality], ...], np.ndarray]:
    entries: list[tuple[int, ChordQuality]] = []
    rows: list[np.ndarray] = []
    for quality in qualities:
        for root in range(12):
            vector = np.zeros(12)
            for interval in CHORD_INTERVALS[quality]:
                vector[(root + interval) % 12] = 1.0
            entries.append((root, quality))
            rows.append(vector / np.linalg.norm(vector))
    return tuple(entries), np.vstack(rows)


def rank_chords(
    vector: np.ndarray,
    *,
    qualities: tuple[ChordQuality, ...] = AUDIO_QUALITIES,
    bass_pitch_class: int | None = None,
    limit: int = 8,
) -> list[ChordCandidate]:
    """Classe les accords par similarité cosinus avec `vector` (12 valeurs
    positives). Liste vide si le vecteur est nul. L'ordre peut être départagé
    par la basse (`BASS_ROOT_BONUS`) ; les scores renvoyés sont toujours bruts."""

    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        return []
    entries, bank = template_bank(qualities)
    scores = bank @ (np.asarray(vector, dtype=float) / norm)
    ordering_scores = scores.copy()
    if bass_pitch_class is not None:
        for index, (root, _) in enumerate(entries):
            if root == bass_pitch_class:
                ordering_scores[index] += BASS_ROOT_BONUS
    order = np.argsort(-ordering_scores, kind="stable")[:limit]
    return [
        ChordCandidate(
            root_pitch_class=entries[i][0],
            quality=entries[i][1],
            score=float(min(1.0, max(0.0, scores[i]))),
        )
        for i in order
    ]


@dataclass(frozen=True)
class Assessment:
    best: ChordCandidate
    alternatives: tuple[ChordCandidate, ...]
    ambiguous: bool
    confidence: float
    margin: float


def assess(candidates: list[ChordCandidate]) -> Assessment | None:
    """Interprète un classement : ambiguïté (marge faible entre les deux
    premiers), alternatives plausibles et confiance.

    `confidence = score du meilleur × min(1, marge / FULL_CONFIDENCE_MARGIN)` :
    elle est élevée seulement si l'accord correspond bien aux données **et**
    se distingue nettement de ses concurrents. C'est un indicateur heuristique,
    pas une probabilité calibrée.
    """

    if not candidates:
        return None
    best = candidates[0]
    second_score = candidates[1].score if len(candidates) > 1 else 0.0
    # Le classement peut avoir été départagé par la basse : si le meilleur a un
    # score brut inférieur au deuxième, les deux lectures sont à égalité.
    margin = max(0.0, best.score - second_score)
    alternatives = tuple(c for c in candidates[1:] if c.score >= best.score - ALTERNATIVE_WINDOW)[
        :MAX_ALTERNATIVES
    ]
    return Assessment(
        best=best,
        alternatives=alternatives,
        ambiguous=margin < AMBIGUITY_MARGIN,
        confidence=best.score * min(1.0, margin / FULL_CONFIDENCE_MARGIN),
        margin=margin,
    )
