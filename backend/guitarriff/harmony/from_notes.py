"""Déduction d'accords à partir de **notes transcrites** (`NoteEvent`).

Distinct de l'estimation à partir de l'audio (`analyzer.py`) : ici les hauteurs
sont connues (sous réserve des erreurs de la transcription), donc la **basse
exacte** — la plus basse note du groupe — est connue et le renversement est
déterminable avec certitude, y compris une basse hors de l'accord (do/ré).

## Règles

- Notes simultanées regroupées comme pour le mapping manche
  (`model/grouping.py`).
- Au moins 3 classes de hauteur distinctes : classement par similarité avec les
  modèles d'accords (`templates.py`), même gestion de l'ambiguïté que pour
  l'audio ; en dessous d'une similarité de 0.7, pas d'accord.
- Exactement 2 classes séparées d'une quinte : « quinte » (`POWER`), toujours
  signalée ambiguë (la tierce est absente, ou a été manquée par la
  transcription) avec majeur/mineur en alternatives.
- Moins de 2 classes, ou 2 classes sans intervalle de quinte : pas d'accord.
- `confidence` = confiance de l'accord × moyenne des confiances des notes
  quand elles existent (une transcription incertaine rend l'accord incertain)
  × **couverture** (part des classes de hauteur jouées qui appartiennent à
  l'accord retenu). Une couverture incomplète (note étrangère à l'accord, amas
  chromatique) rend aussi l'accord **ambigu** : l'étiquette n'explique pas tout.
- Un accord ne chevauche jamais le suivant : sa durée est écourtée au début du
  suivant si des notes tenues dépassent.
"""

from __future__ import annotations

import numpy as np

from guitarriff.harmony.analyzer import MIN_MATCH_SCORE
from guitarriff.harmony.templates import (
    ALL_QUALITIES,
    AUDIO_QUALITIES,
    POWER_CONFIDENCE,
    assess,
    rank_chords,
)
from guitarriff.model import ChordEvent, ChordQuality, EstimationSource, NoteEvent
from guitarriff.model.chord import chord_pitch_classes
from guitarriff.model.grouping import group_simultaneous_notes


def _mean_note_confidence(group: tuple[NoteEvent, ...]) -> float | None:
    values = [n.confidence for n in group if n.confidence is not None]
    return float(np.mean(values)) if values else None


def chords_from_notes(notes: tuple[NoteEvent, ...]) -> tuple[ChordEvent, ...]:
    drafts: list[tuple[float, float, ChordEvent]] = []  # (début, fin brute, accord)

    for group in group_simultaneous_notes(notes):
        start = min(n.start_seconds for n in group)
        end = max(n.end_seconds for n in group)
        bass_pitch_class = min(group, key=lambda n: n.midi_pitch).midi_pitch % 12

        vector = np.zeros(12)
        for note in group:
            vector[note.midi_pitch % 12] = 1.0
        distinct = np.flatnonzero(vector)
        note_confidence = _mean_note_confidence(group)
        weight = note_confidence if note_confidence is not None else 1.0

        if len(distinct) == 2:
            a, b = (int(x) for x in distinct)
            if (b - a) % 12 == 7:
                root = a
            elif (a - b) % 12 == 7:
                root = b
            else:
                continue
            ranked = rank_chords(vector, qualities=ALL_QUALITIES)
            alternatives = tuple(c for c in ranked if c.quality != ChordQuality.POWER)[:3]
            chord = ChordEvent(
                root_pitch_class=root,
                quality=ChordQuality.POWER,
                bass_pitch_class=bass_pitch_class,
                start_seconds=start,
                duration_seconds=end - start,
                confidence=POWER_CONFIDENCE * weight,
                source=EstimationSource.DETECTED,
                ambiguous=True,
                alternatives=alternatives,
            )
        elif len(distinct) >= 3:
            assessment = assess(
                rank_chords(vector, qualities=AUDIO_QUALITIES, bass_pitch_class=bass_pitch_class)
            )
            if assessment is None or assessment.best.score < MIN_MATCH_SCORE:
                continue
            tones = set(
                chord_pitch_classes(assessment.best.root_pitch_class, assessment.best.quality)
            )
            coverage = len(tones & {int(x) for x in distinct}) / len(distinct)
            chord = ChordEvent(
                root_pitch_class=assessment.best.root_pitch_class,
                quality=assessment.best.quality,
                bass_pitch_class=bass_pitch_class,
                start_seconds=start,
                duration_seconds=end - start,
                confidence=assessment.confidence * weight * coverage,
                source=EstimationSource.DETECTED,
                ambiguous=assessment.ambiguous or coverage < 1.0,
                alternatives=assessment.alternatives,
            )
        else:
            continue

        drafts.append((start, end, chord))

    drafts.sort(key=lambda d: d[0])
    chords: list[ChordEvent] = []
    for index, (start, end, chord) in enumerate(drafts):
        if index + 1 < len(drafts):
            end = min(end, drafts[index + 1][0])
        if end - start <= 0.0:
            continue
        chords.append(chord.model_copy(update={"duration_seconds": end - start}))
    return tuple(chords)
