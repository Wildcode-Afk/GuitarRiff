"""Conversion des `NoteEvent` d'une `Track` en positions (corde, case).

**Ne reconstitue pas le doigté original du musicien** — impossible à déduire
du seul audio. Produit une position jouable parmi plusieurs valides, choisie
par une fonction de coût (voir `cost.py`), pas nécessairement celle qu'un
musicien donné aurait réellement utilisée.

Ce mapper est partagé par la guitare (Étape 11) et la basse (Étape 12) : ce
qui change d'un instrument à l'autre (accordage par défaut, poids de la
fonction de coût, réinitialisation après un silence) est porté par un profil
(`profiles.py`), pas par une copie du code.

## Notes simultanées (accords)

Les notes dont les débuts sont suffisamment proches (`CHORD_TOLERANCE_SECONDS`,
pour absorber la micro-gigue d'onset d'une transcription audio réelle — les
notes d'un même accord ne partagent presque jamais un `start_seconds`
rigoureusement identique) sont regroupées et résolues ensemble : deux notes
d'un même groupe ne peuvent jamais partager la même corde.

## Notes répétées et silences

- Le contexte de la note précédente (case de référence de la main, corde
  moyenne) est conservé d'un groupe au suivant : c'est ce qui permet de limiter
  les déplacements inutiles et de rejouer une note répétée exactement au même
  endroit (vérifié sur des milliers de séquences aléatoires, voir les tests).
- Un silence n'est pas un objet du modèle (voir `model/note_event.py`) : c'est
  l'écart entre la fin du groupe précédent et le début du suivant. Si le profil
  définit `rest_reset_seconds` et que cet écart l'atteint, le contexte est
  oublié — la main a eu le temps de se repositionner librement.

## Notes impossibles à placer

Deux cas distincts, tous deux signalés explicitement (jamais une note
silencieusement ignorée) :

- la hauteur est hors de portée de l'accordage/capodastre/limite de cases ;
- le groupe contient plus de notes simultanées jouables que de cordes
  disponibles (aucune assignation complète n'existe) — dans ce cas, **tout**
  le groupe est signalé comme impossible plutôt que de choisir arbitrairement
  quelles notes garder.
"""

from __future__ import annotations

from dataclasses import dataclass

from guitarriff.model import InstrumentSpecificInfo, NoteEvent, Track
from guitarriff.tablature.cost import (
    DEFAULT_WEIGHTS,
    CostWeights,
    group_cost,
    reference_fret_after,
    string_center_after,
)
from guitarriff.tablature.fretboard import FretboardConfig, Position, candidate_positions

CHORD_TOLERANCE_SECONDS = 0.05


@dataclass(frozen=True)
class UnplacedNote:
    note: NoteEvent
    reason: str


@dataclass(frozen=True)
class MappingResult:
    track: Track
    placed_count: int
    unplaced: tuple[UnplacedNote, ...]


@dataclass(frozen=True)
class _Context:
    """Ce que l'on sait de la main après le dernier groupe effectivement joué."""

    reference_fret: float | None = None
    string_center: float | None = None


def _group_indices(notes: tuple[NoteEvent, ...]) -> tuple[tuple[int, ...], ...]:
    """Regroupe les indices de notes dont les débuts sont à moins de
    `CHORD_TOLERANCE_SECONDS` du début du groupe. Travailler sur des indices
    (et non sur l'identité des objets) reste correct même si le même objet
    `NoteEvent` apparaît plusieurs fois dans la piste (notes répétées)."""

    if not notes:
        return ()

    ordered = sorted(range(len(notes)), key=lambda i: notes[i].start_seconds)
    groups: list[list[int]] = [[ordered[0]]]
    group_start = notes[ordered[0]].start_seconds

    for index in ordered[1:]:
        if notes[index].start_seconds - group_start <= CHORD_TOLERANCE_SECONDS:
            groups[-1].append(index)
        else:
            groups.append([index])
            group_start = notes[index].start_seconds

    return tuple(tuple(g) for g in groups)


def group_simultaneous_notes(notes: tuple[NoteEvent, ...]) -> tuple[tuple[NoteEvent, ...], ...]:
    """Version publique du regroupement (utilisée aussi par le rendu de la
    tablature, `render.py`), renvoyant des notes plutôt que des indices."""

    return tuple(tuple(notes[i] for i in group) for group in _group_indices(notes))


def _best_assignment(
    notes: tuple[NoteEvent, ...],
    candidates_by_note: tuple[tuple[Position, ...], ...],
    context: _Context,
    weights: CostWeights,
) -> tuple[Position, ...] | None:
    """Recherche exhaustive de la meilleure affectation (une position par
    note, cordes toutes distinctes). Les accords réels comportent peu de
    notes (au plus le nombre de cordes de l'instrument) et chaque note a au
    plus `n_strings` candidats : la recherche exhaustive reste largement
    praticable (quelques milliers de combinaisons au pire) sans nécessiter
    d'heuristique d'élagage plus complexe."""

    best_cost: float | None = None
    best_positions: tuple[Position, ...] | None = None

    def backtrack(index: int, used_strings: set[int], chosen: list[Position]) -> None:
        nonlocal best_cost, best_positions
        if index == len(notes):
            positions = tuple(chosen)
            cost = group_cost(
                positions,
                context.reference_fret,
                weights,
                previous_string_center=context.string_center,
            )
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best_positions = positions
            return
        for candidate in candidates_by_note[index]:
            if candidate.string_index in used_strings:
                continue
            used_strings.add(candidate.string_index)
            chosen.append(candidate)
            backtrack(index + 1, used_strings, chosen)
            chosen.pop()
            used_strings.remove(candidate.string_index)

    backtrack(0, set(), [])
    return best_positions


def map_track_to_fretboard(
    track: Track,
    config: FretboardConfig,
    weights: CostWeights = DEFAULT_WEIGHTS,
    *,
    rest_reset_seconds: float | None = None,
) -> MappingResult:
    """Calcule une position (corde, case) pour chaque note de `track`
    exploitable sur `config`, en tenant compte des notes précédentes, des
    notes simultanées et, si `rest_reset_seconds` est fourni, des silences.
    Renvoie une nouvelle `Track` (accordage et capodastre mis à jour, notes
    enrichies de `instrument_info` quand c'est possible) ainsi que le détail
    des notes non placées."""

    notes = track.notes
    groups = _group_indices(notes)

    placed: dict[int, NoteEvent] = {}  # indice d'origine -> note enrichie
    unplaced: list[UnplacedNote] = []
    context = _Context()
    last_played_end: float | None = None

    for group in groups:
        group_notes = tuple(notes[i] for i in group)
        group_start = min(n.start_seconds for n in group_notes)

        if (
            rest_reset_seconds is not None
            and last_played_end is not None
            and group_start - last_played_end >= rest_reset_seconds
        ):
            context = _Context()  # silence suffisamment long : la main est libre

        candidates_by_note = tuple(candidate_positions(n.midi_pitch, config) for n in group_notes)

        reachable = [
            (i, n, c) for i, n, c in zip(group, group_notes, candidates_by_note, strict=True) if c
        ]
        unreachable = [n for n, c in zip(group_notes, candidates_by_note, strict=True) if not c]
        for note in unreachable:
            unplaced.append(
                UnplacedNote(
                    note=note,
                    reason=(
                        f"Hauteur MIDI {note.midi_pitch} hors de portée de cet accordage "
                        f"(capodastre case {config.capo_fret}, limite case {config.max_fret})."
                    ),
                )
            )

        if not reachable:
            continue

        if len(reachable) > config.n_strings:
            for _, note, _ in reachable:
                unplaced.append(
                    UnplacedNote(
                        note=note,
                        reason=(
                            f"{len(reachable)} notes simultanées pour seulement "
                            f"{config.n_strings} corde(s) : impossible de toutes les jouer."
                        ),
                    )
                )
            continue  # rien n'a été joué : le contexte de la main ne change pas

        reachable_indices = tuple(i for i, _, _ in reachable)
        reachable_notes = tuple(n for _, n, _ in reachable)
        reachable_candidates = tuple(c for _, _, c in reachable)

        assignment = _best_assignment(reachable_notes, reachable_candidates, context, weights)
        if assignment is None:
            # Ne devrait pas arriver (chaque note a au moins un candidat et
            # le nombre de notes ne dépasse pas le nombre de cordes), mais
            # une recherche qui échoue malgré tout est signalée, pas ignorée.
            for note in reachable_notes:
                unplaced.append(
                    UnplacedNote(note=note, reason="Aucune affectation de cordes valide trouvée.")
                )
            continue

        for index, note, position in zip(
            reachable_indices, reachable_notes, assignment, strict=True
        ):
            placed[index] = note.with_instrument_info(
                InstrumentSpecificInfo(string_index=position.string_index, fret=position.fret)
            )

        context = _Context(
            reference_fret=reference_fret_after(assignment, context.reference_fret),
            string_center=string_center_after(assignment),
        )
        last_played_end = max(n.end_seconds for n in reachable_notes)

    new_notes = tuple(placed.get(i, note) for i, note in enumerate(notes))
    new_track = track.model_copy(
        update={"tuning": config.tuning, "capo_fret": config.capo_fret, "notes": new_notes}
    )

    return MappingResult(track=new_track, placed_count=len(placed), unplaced=tuple(unplaced))
