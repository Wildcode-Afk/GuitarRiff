"""Fonction de coût pour la sélection de position sur le manche.

**Ce ne sont pas des constantes dérivées objectivement** — contrairement par
exemple à la fréquence d'échantillonnage cible de la normalisation (Étape 6,
justifiée par une contrainte vérifiable de `basic-pitch`), les poids
ci-dessous sont un jugement heuristique de jouabilité, documenté comme tel,
ajustable. Le but n'est **pas** de reconstituer le doigté réel qu'aurait
utilisé le guitariste original (impossible à déduire du seul audio) mais de
produire *une* position jouable et cohérente avec ce qui précède, parmi
plusieurs valides.

## Composantes du coût

- **Déplacement** (`movement_weight`) : distance en cases entre une position
  pressée et la position de référence de la main issue de la note/l'accord
  précédent. Une corde à vide (case 0) ne coûte rien ici : elle ne requiert
  aucun doigt, donc aucun déplacement de main.
- **Écart entre les doigts** (`span_weight`), pour un accord (plusieurs notes
  simultanées) : différence entre la case la plus haute et la plus basse
  parmi les cordes *pressées* (les cordes à vide sont ignorées — une corde à
  vide n'écarte pas les doigts). Un grand écart est pénalisé plus fortement
  que le déplacement simple, car un étirement important est généralement
  plus difficile qu'un déplacement de la main dans son ensemble.
- **Jouabilité générale** (`absolute_fret_weight`) : léger biais vers les
  cases basses, qui sont en général plus accessibles/moins fatigantes.
- **Bonus corde à vide** (`open_string_bonus`) : les cordes à vide sont
  toujours plus faciles à jouer qu'une case pressée, quelle que soit la
  position de la main.
"""

from __future__ import annotations

from dataclasses import dataclass

from guitarriff.tablature.fretboard import Position


@dataclass(frozen=True)
class CostWeights:
    """Poids de la fonction de coût.

    `string_change_weight` vaut 0 par défaut : il n'intervient pas dans le
    profil guitare (Étape 11, comportement inchangé) et est activé par le
    profil basse (Étape 12, voir `profiles.py`). C'est un coût par corde
    d'écart avec la (ou les) corde(s) de la note/l'accord précédent : sur une
    basse, les cordes sont très espacées et un changement de corde est un geste
    plus coûteux qu'à la guitare.

    Un bonus de répétition explicite (rejouer une note identique à la même
    position) a été prototypé puis retiré : mesuré sur 4000 séquences
    aléatoires avec répétitions immédiates, il ne changeait aucun résultat —
    le déplacement et le changement de corde suffisent déjà à garder une note
    répétée exactement au même endroit.
    """

    movement_weight: float = 1.0
    span_weight: float = 2.0
    absolute_fret_weight: float = 0.3
    open_string_bonus: float = -0.5
    string_change_weight: float = 0.0


DEFAULT_WEIGHTS = CostWeights()


def position_cost(
    position: Position,
    previous_reference_fret: float | None,
    weights: CostWeights = DEFAULT_WEIGHTS,
) -> float:
    """Coût d'une position isolée (note seule, pas un accord) par rapport à
    la position de référence de la main avant cette note."""

    if position.fret == 0:
        return weights.open_string_bonus

    cost = weights.absolute_fret_weight * position.fret
    if previous_reference_fret is not None:
        cost += weights.movement_weight * abs(position.fret - previous_reference_fret)
    return cost


def group_cost(
    positions: tuple[Position, ...],
    previous_reference_fret: float | None,
    weights: CostWeights = DEFAULT_WEIGHTS,
    *,
    previous_string_center: float | None = None,
) -> float:
    """Coût total d'un ensemble de positions jouées simultanément (accord) :
    somme des coûts individuels, plus une pénalité d'écartement des doigts et,
    si `string_change_weight > 0`, une pénalité de changement de corde par
    rapport à la position moyenne (en cordes) du groupe précédent."""

    total = sum(position_cost(p, previous_reference_fret, weights) for p in positions)

    if previous_string_center is not None and weights.string_change_weight:
        total += weights.string_change_weight * sum(
            abs(p.string_index - previous_string_center) for p in positions
        )

    pressed_frets = [p.fret for p in positions if p.fret > 0]
    if len(pressed_frets) >= 2:
        span = max(pressed_frets) - min(pressed_frets)
        total += weights.span_weight * span

    return total


def reference_fret_after(
    positions: tuple[Position, ...], previous_reference_fret: float | None
) -> float | None:
    """Nouvelle position de référence de la main après avoir joué
    `positions`. Les cordes à vide ne déplacent pas la main : si aucune corde
    n'a été pressée, la référence précédente est conservée telle quelle."""

    pressed_frets = [p.fret for p in positions if p.fret > 0]
    if not pressed_frets:
        return previous_reference_fret
    return sum(pressed_frets) / len(pressed_frets)


def string_center_after(
    positions: tuple[Position, ...],
) -> float:
    """Position moyenne, en indices de cordes, d'un groupe de positions."""

    return sum(p.string_index for p in positions) / len(positions)
