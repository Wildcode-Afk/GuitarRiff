"""Rendu d'une `Track` mappée sur le manche (Étape 11/12) en tablature ASCII
lisible. Fonction pure, indépendante de l'instrument : la même fonction sert
la guitare et la basse, quel que soit le nombre de cordes.

## Ce que ce rendu montre — et ce qu'il ne montre pas

- Une colonne par note ou par accord, dans l'ordre chronologique.
- **Pas de notation rythmique** : les durées ne sont pas représentées et la
  largeur d'une colonne ne dépend pas de la durée de la note. Seuls les
  silences d'au moins un temps sont signalés, par des colonnes vides (voir
  ci-dessous), pour que les pauses restent visibles.
- Les numéros de case sont **relatifs au capodastre** (voir
  `fretboard.py`) ; le capodastre est rappelé dans l'en-tête quand il est
  utilisé.
- Les notes sans position (`instrument_info` absent : hors de portée de
  l'accordage, accord trop fourni, voir `mapper.py`) ne sont **pas affichées**
  mais sont comptées dans une ligne de bas de page, jamais omises
  silencieusement.

## Silences et mesures

Un silence n'est pas un objet du modèle : c'est l'écart entre la fin d'un
groupe de notes et le début du suivant. S'il vaut au moins `beat_seconds`
(un temps), `floor(écart / beat_seconds)` colonnes vides sont insérées
(plafonné à `MAX_REST_COLUMNS`). Si les notes portent une `position` calculée
(`Song.with_computed_positions`), une barre de mesure `|` est insérée à chaque
changement de mesure.
"""

from __future__ import annotations

from dataclasses import dataclass

from guitarriff.model import Track
from guitarriff.tablature.mapper import group_simultaneous_notes

MAX_REST_COLUMNS = 6
DEFAULT_MAX_WIDTH = 80

_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


@dataclass(frozen=True)
class TabRendering:
    text: str
    placed_count: int
    unplaced_count: int


def string_labels(tuning: tuple[int, ...]) -> tuple[str, ...]:
    """Nom de chaque corde (de la plus grave à la plus aiguë). Un nom déjà
    utilisé par une corde plus grave est écrit en minuscule, selon la
    convention usuelle (guitare : E A D G B e)."""

    seen: set[str] = set()
    labels = []
    for midi_note in tuning:
        name = _NOTE_NAMES[midi_note % 12]
        labels.append(name.lower() if name in seen else name)
        seen.add(name)
    return tuple(labels)


def render_ascii_tab(
    track: Track, *, beat_seconds: float | None = None, max_width: int = DEFAULT_MAX_WIDTH
) -> TabRendering:
    if track.tuning is None:
        raise ValueError(
            "La piste n'a pas d'accordage : le mapping manche doit être fait avant le rendu."
        )

    n_strings = len(track.tuning)
    labels = string_labels(track.tuning)
    label_width = max(len(label) for label in labels)

    placed = tuple(n for n in track.notes if n.instrument_info is not None)
    unplaced_count = len(track.notes) - len(placed)

    columns: list[list[str]] = []  # une colonne = une chaîne par corde (indice = corde)

    previous_end: float | None = None
    previous_bar: int | None = None

    for group in group_simultaneous_notes(placed):
        start = min(n.start_seconds for n in group)

        if previous_end is not None and beat_seconds and beat_seconds > 0:
            silence = start - previous_end
            if silence >= beat_seconds:
                for _ in range(min(MAX_REST_COLUMNS, int(silence / beat_seconds))):
                    columns.append(["---"] * n_strings)

        bar = group[0].position.bar if group[0].position is not None else None
        if previous_bar is not None and bar is not None and bar != previous_bar:
            columns.append(["|"] * n_strings)
        if bar is not None:
            previous_bar = bar

        frets_by_string: dict[int, str] = {}
        for note in group:
            info = note.instrument_info
            assert info is not None and info.string_index is not None and info.fret is not None
            frets_by_string[info.string_index] = str(info.fret)

        width = max(len(text) for text in frets_by_string.values())
        columns.append(
            [
                "-" + frets_by_string[s].ljust(width, "-") + "-"
                if s in frets_by_string
                else "-" * (width + 2)
                for s in range(n_strings)
            ]
        )
        previous_end = max(n.end_seconds for n in group)

    columns.append(["|"] * n_strings)
    if len(columns) == 1:
        columns.insert(0, ["---"] * n_strings)

    prefix_width = label_width + 1
    systems: list[list[list[str]]] = [[]]
    used = prefix_width
    for column in columns:
        column_width = len(column[0])
        if systems[-1] and used + column_width > max_width:
            systems.append([])
            used = prefix_width
        if not systems[-1] and column[0] == "|" and len(systems) > 1:
            continue  # pas de barre de mesure en tête d'une ligne de retour
        systems[-1].append(column)
        used += column_width

    lines = [_header(track, labels)]
    for system in systems:
        lines.append("")
        for string_index in range(n_strings - 1, -1, -1):  # corde aiguë en haut
            prefix = labels[string_index].ljust(label_width) + "|"
            lines.append(prefix + "".join(column[string_index] for column in system))
    if unplaced_count:
        lines.append("")
        lines.append(
            f"({unplaced_count} note(s) sans position : hors de portée de l'accordage ou "
            "accord trop fourni — non affichée(s))"
        )

    return TabRendering(
        text="\n".join(lines), placed_count=len(placed), unplaced_count=unplaced_count
    )


def _header(track: Track, labels: tuple[str, ...]) -> str:
    assert track.tuning is not None
    header = f"{track.name} — accordage {' '.join(labels)}"
    if track.capo_fret > 0:
        header += f", capodastre case {track.capo_fret}"
    return header
