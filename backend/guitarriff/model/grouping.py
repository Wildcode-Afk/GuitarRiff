"""Regroupement des notes simultanées (accords) d'une piste.

Partagé par le mapping manche (`tablature/mapper.py`, Étape 11-12), le rendu
de tablature et la déduction d'accords à partir de notes (`harmony/`,
Étape 13) : un seul endroit définit ce que « simultané » veut dire.

Les notes dont les débuts sont à moins de `CHORD_TOLERANCE_SECONDS` du début
du groupe sont regroupées — une transcription audio réelle ne produit presque
jamais des `start_seconds` rigoureusement identiques pour les notes d'un même
accord (micro-gigue d'onset).
"""

from __future__ import annotations

from guitarriff.model.note_event import NoteEvent

CHORD_TOLERANCE_SECONDS = 0.05


def group_note_indices(notes: tuple[NoteEvent, ...]) -> tuple[tuple[int, ...], ...]:
    """Regroupe les **indices** des notes. Travailler sur des indices (et non
    sur l'identité des objets) reste correct même si le même objet
    `NoteEvent` apparaît plusieurs fois dans la piste."""

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
    """Version renvoyant des notes plutôt que des indices."""

    return tuple(tuple(notes[i] for i in group) for group in group_note_indices(notes))
