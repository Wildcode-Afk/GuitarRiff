"""Estimation d'accords à partir de l'audio — **base de référence** : chroma
`librosa` obtenu par décomposition en notes, puis comparaison à des modèles
d'accords. Pas un modèle entraîné.

## Pourquoi aucune bibliothèque de reconnaissance d'accords n'est ajoutée

Une reconnaissance réellement fiable sur des enregistrements demande
normalement un modèle entraîné. Les options existantes ont été étudiées
(métadonnées PyPI et dépendances vérifiées) et aucune n'est acceptable ici :

- `crema` : licence ISC, mais dernière release en avril 2022 ; exige
  `tensorflow` et `keras`.
- `autochord` : licence MIT, mais dernière release en octobre 2021 ; exige
  `tensorflow` et `vamp`.
- `chord-extractor` : **GPLv2** (incompatible avec la distribution permissive
  du projet), Python `<3.12`, enveloppe un greffon Vamp compilé (Chordino).
- `essentia` : **AGPL-3.0**, bibliothèque lourde.
- `madmom` : abandonné (2018) ; licence « BSD, CC BY-NC-SA » : modèles à
  usage **non commercial**.
- `madmom-infer` : BSD-2, maintenu — mais l'extraction d'accords y est
  explicitement « hors périmètre pour l'instant ».

Voir docs/TECHNICAL_DECISIONS.md, D9. Cette base n'ajoute donc **aucune
dépendance** de modèle ; elle reste modeste et dit ce qu'elle ne sait pas.

## Méthode

1. **CQT** (`librosa.cqt`, 7 octaves à partir de do1, hop 2048, accordage
   estimé) à **3 cases par demi-ton**. Mesuré : à 1 case par demi-ton, une note
   déborde d'environ 45 % sur les demi-tons voisins et pollue le chroma ; à 3
   cases le profil d'une sinusoïde pure est `[0.01, 0.5, 1, 0.5, 0.01]`,
   identique à toutes les octaves.
2. **Compensation de la réponse en fréquence** : le module du CQT d'une
   sinusoïde d'amplitude constante décroît comme f^(-1/2) (mesuré : x2.0 à do2,
   x1.0 à do4, x0.5 à do6). Sans gain `sqrt(f / f_ref)`, une note de basse
   écrase le reste du chroma.
3. **Décomposition en notes** (moindres carrés non négatifs, principe du chroma
   NNLS de Chordino) avec un profil d'harmoniques : les harmoniques d'une note
   ne sont plus confondues avec d'autres notes. Mesuré sur 108 accords
   synthétiques à 4 harmoniques : 52 exacts avec un simple repliement du
   spectre, 72/72 des accords sans équivalent avec la décomposition en notes.
4. Étiquette d'accord par trame (similarité cosinus), lissée par vote
   majoritaire, puis fusion des segments trop courts : cela ne sert qu'à
   **segmenter**. L'accord final est reclassé sur le chroma **moyen** du segment.
5. Basse : plus basse note significative des activations du registre do1-si3,
   **seulement si** ce registre porte au moins la moitié de l'énergie maximale
   (sinon aucun renversement n'est affirmé : la décomposition produit des
   activations parasites une octave sous les notes réelles). Elle définit le
   renversement seulement si c'est une note de l'accord (une basse hors accord
   n'est jamais affirmée comme « slash » depuis l'audio).

## Garde-fous (jamais d'accord inventé)

- Silence, ou trame sous 5 % de l'énergie maximale : pas d'accord.
- Il faut **au moins 3 classes de hauteur significatives** (≥ 15 % du maximum)
  pour proposer un accord de trois sons ou plus. Mesuré : après décomposition,
  une note seule ne laisse que ≤ 5 % d'énergie parasite, alors que les vraies
  notes d'accord descendent jusqu'à ≈ 23 % (quinte d'un accord à fondamentale
  doublée) ; un seuil à 35 %, essayé d'abord, ratait ces accords.
- Exactement 2 classes séparées d'une quinte : « quinte » (power chord), mais
  **toujours ambiguë** et à confiance plafonnée.
- Meilleure similarité inférieure à 0.7 (ex. bruit) : pas d'accord.

## Limites assumées

Tous les chiffres ci-dessus viennent de signaux **synthétiques** que j'ai
générés (notes à harmoniques en 1/k, durées de 2 s) : ils décrivent le meilleur
cas, pas la performance réelle. La précision sur de vrais enregistrements
(timbres riches, percussions, voix, réverbération, accords complexes) n'a
**pas** été mesurée et est certainement très inférieure. Le vocabulaire (10
qualités) exclut les accords étendus ; l'orthographe n'est pas fonction de la
tonalité ; aucune analyse de tonalité ni de contexte harmonique n'intervient ;
une sixte majeure est lue comme la septième mineure du relatif (mêmes notes).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import nnls

from guitarriff.errors import ChordAnalysisError, ChordAnalysisTimeoutError
from guitarriff.harmony.templates import (
    AUDIO_QUALITIES,
    POWER_CONFIDENCE,
    assess,
    rank_chords,
    template_bank,
)
from guitarriff.logging_config import get_logger
from guitarriff.model import ChordCandidate, ChordEvent, ChordQuality, EstimationSource
from guitarriff.model.chord import chord_pitch_classes

logger = get_logger(__name__)

HOP_LENGTH = 2048
BINS_PER_SEMITONE = 3  # à 1 case par demi-ton, une note déborde de ~45 % sur ses voisines
N_NOTES = 84  # 7 octaves à partir de do1 (MIDI 24)
N_BINS = N_NOTES * BINS_PER_SEMITONE
BINS_PER_OCTAVE = 12 * BINS_PER_SEMITONE
LOW_NOTES = 36  # do1 à si3 : registre de la basse
# Le module du CQT d'une sinusoïde d'amplitude constante décroît comme f^(-1/2)
# (mesuré) ; gain appliqué : sqrt(f / f_ref).
REFERENCE_HZ = 261.63

SMOOTH_FRAMES = 5
MIN_SEGMENT_FRAMES = 4
SILENCE_RATIO = 0.05

SIGNIFICANT_RATIO = 0.15
MIN_SIGNIFICANT_PITCH_CLASSES = 3
MIN_MATCH_SCORE = 0.7

# Profil d'une note dans le CQT, pour la décomposition en notes. Noyau
# d'étalement **mesuré** sur une sinusoïde pure (36 cases par octave) :
# [0.01, 0.5, 1, 0.5, 0.01] sur +-2 cases, soit un triangle de demi-largeur 2.
# Harmoniques 1 à 8, amplitude décroissant géométriquement (hypothèse de timbre,
# volontairement différente du 1/k des signaux de test pour ne pas ajuster le
# dictionnaire à eux).
SPREAD_HALF_WIDTH_BINS = 2.0
HARMONIC_NUMBERS = (1, 2, 3, 4, 5, 6, 7, 8)
HARMONIC_DECAY = 0.7

# Énergie minimale du registre grave (do1-si3) par rapport au pic des activations
# pour affirmer une basse. Mesuré : la décomposition en notes produit de faibles
# activations parasites une octave sous les notes réelles (rapport 0.10-0.28,
# médiane 0.18, sur des accords joués uniquement en registre moyen), alors que de
# vraies notes de basse d'amplitude égale donnent 0.87-1.00. Un seuil à 0.10,
# essayé d'abord, faisait affirmer une basse — donc un renversement — sans note
# grave : 46 inversions fausses sur 120. On préfère ne pas affirmer le
# renversement que d'en affirmer un faux ; en contrepartie, une basse nettement
# plus discrète que le reste du mélange ne sera pas retenue.
BASS_MIN_RATIO = 0.5
BASS_BIN_RATIO = 0.4

_NO_CHORD = -1


@dataclass(frozen=True)
class ChordAnalysisResult:
    chords: tuple[ChordEvent, ...]
    duration_seconds: float


def _majority_filter(labels: np.ndarray, window: int) -> np.ndarray:
    half = window // 2
    out = labels.copy()
    for i in range(len(labels)):
        chunk = labels[max(0, i - half) : i + half + 1]
        values, counts = np.unique(chunk, return_counts=True)
        out[i] = values[np.argmax(counts)]
    return out


def _runs(labels: np.ndarray) -> list[list[int]]:
    runs: list[list[int]] = []
    start = 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            runs.append([int(labels[start]), start, i])
            start = i
    return runs


def _fuse(runs: list[list[int]]) -> list[list[int]]:
    fused: list[list[int]] = []
    for run in runs:
        if fused and fused[-1][0] == run[0]:
            fused[-1][2] = run[2]
        else:
            fused.append(list(run))
    return fused


def _merge_short_runs(runs: list[list[int]], min_length: int) -> list[list[int]]:
    runs = _fuse(runs)
    while len(runs) > 1:
        short = [i for i, r in enumerate(runs) if r[2] - r[1] < min_length]
        if not short:
            break
        i = min(short, key=lambda k: runs[k][2] - runs[k][1])
        neighbours = [j for j in (i - 1, i + 1) if 0 <= j < len(runs)]
        j = max(neighbours, key=lambda k: runs[k][2] - runs[k][1])
        runs[i][0] = runs[j][0]
        runs = _fuse(runs)
    return runs


@lru_cache(maxsize=1)
def _note_dictionary() -> np.ndarray:
    """Matrice (cases CQT × notes) : spectre attendu de chaque note avec ses
    harmoniques. La note d'indice i est la hauteur MIDI 24 + i (do1 = note 0),
    dont la case centrale est `3 * i`."""

    bins = np.arange(N_BINS)
    dictionary = np.zeros((N_BINS, N_NOTES))
    for note in range(N_NOTES):
        for k in HARMONIC_NUMBERS:
            position = BINS_PER_SEMITONE * note + BINS_PER_OCTAVE * np.log2(k)
            dictionary[:, note] += (HARMONIC_DECAY ** (k - 1)) * np.maximum(
                0.0, 1.0 - np.abs(bins - position) / SPREAD_HALF_WIDTH_BINS
            )
    return dictionary


def _note_activations(cqt_magnitude: np.ndarray) -> np.ndarray:
    """Décompose chaque trame du CQT en activations de **notes** (moindres
    carrés non négatifs avec le profil ci-dessus), de sorte que les harmoniques
    d'une note ne soient pas confondues avec d'autres notes — c'est ce qui
    évite qu'une triade majeure soit lue comme un accord de septième majeure à
    cause de la troisième harmonique de sa tierce."""

    dictionary = _note_dictionary()
    activations = np.zeros((N_NOTES, cqt_magnitude.shape[1]))
    for frame in range(cqt_magnitude.shape[1]):
        activations[:, frame], _ = nnls(dictionary, cqt_magnitude[:, frame])
    return activations


def _fold_to_chroma(activations: np.ndarray) -> np.ndarray:
    chroma = np.zeros((12, activations.shape[1]))
    for note in range(activations.shape[0]):
        chroma[note % 12] += activations[note]
    return chroma


def _estimate_bass(activations: np.ndarray, start: int, end: int) -> int | None:
    """Plus basse classe de hauteur significative (activations de notes du
    registre do1-si3), ou `None` si ce registre est trop pauvre pour affirmer
    quoi que ce soit."""

    segment = activations[:, start:end]
    low = segment[:LOW_NOTES].mean(axis=1)
    overall_peak = float(segment.mean(axis=1).max())
    if overall_peak <= 0.0 or float(low.max()) < BASS_MIN_RATIO * overall_peak:
        return None
    lowest_significant = int(np.argmax(low >= BASS_BIN_RATIO * float(low.max())))
    return lowest_significant % 12


@dataclass(frozen=True)
class _SegmentChord:
    root: int
    quality: ChordQuality
    bass: int | None
    ambiguous: bool
    confidence: float
    alternatives: tuple[ChordCandidate, ...]


def _chord_for_segment(
    chroma_sum: np.ndarray, bass_pitch_class: int | None
) -> _SegmentChord | None:
    """Renvoie l'accord défendable d'un segment, ou `None` s'il n'y en a pas."""

    peak = float(chroma_sum.max())
    if peak <= 0.0:
        return None
    significant = np.flatnonzero(chroma_sum / peak >= SIGNIFICANT_RATIO)

    if len(significant) == 2:
        a, b = (int(x) for x in significant)
        if (b - a) % 12 == 7:
            root = a
        elif (a - b) % 12 == 7:
            root = b
        else:
            return None
        bass = bass_pitch_class if bass_pitch_class in (root, (root + 7) % 12) else None
        return _SegmentChord(root, ChordQuality.POWER, bass, True, POWER_CONFIDENCE, ())

    if len(significant) < MIN_SIGNIFICANT_PITCH_CLASSES:
        return None

    assessment = assess(
        rank_chords(chroma_sum, qualities=AUDIO_QUALITIES, bass_pitch_class=bass_pitch_class)
    )
    if assessment is None or assessment.best.score < MIN_MATCH_SCORE:
        return None

    best = assessment.best
    tones = chord_pitch_classes(best.root_pitch_class, best.quality)
    bass = bass_pitch_class if bass_pitch_class in tones else None
    return _SegmentChord(
        best.root_pitch_class,
        best.quality,
        bass,
        assessment.ambiguous,
        assessment.confidence,
        assessment.alternatives,
    )


def _merge_adjacent(chords: list[ChordEvent]) -> list[ChordEvent]:
    merged: list[ChordEvent] = []
    for chord in chords:
        if merged:
            previous = merged[-1]
            same = (
                previous.root_pitch_class == chord.root_pitch_class
                and previous.quality == chord.quality
                and previous.bass_pitch_class == chord.bass_pitch_class
                and abs(chord.start_seconds - previous.end_seconds) < 1e-6
            )
            if same:
                confidences = [c for c in (previous.confidence, chord.confidence) if c is not None]
                merged[-1] = previous.model_copy(
                    update={
                        "duration_seconds": chord.end_seconds - previous.start_seconds,
                        "confidence": min(confidences) if confidences else None,
                        "ambiguous": previous.ambiguous or chord.ambiguous,
                    }
                )
                continue
        merged.append(chord)
    return merged


def _analyze(y: Any, sr: int) -> ChordAnalysisResult:
    import librosa

    duration = float(len(y) / sr)
    if duration <= 0.0 or float(np.max(np.abs(y), initial=0.0)) == 0.0:
        return ChordAnalysisResult(chords=(), duration_seconds=max(duration, 0.0))

    tuning = float(librosa.estimate_tuning(y=y, sr=sr))
    c1_hz = float(librosa.note_to_hz("C1"))
    cqt = np.abs(
        librosa.cqt(
            y,
            sr=sr,
            hop_length=HOP_LENGTH,
            fmin=c1_hz,
            n_bins=N_BINS,
            bins_per_octave=BINS_PER_OCTAVE,
            tuning=tuning,
        )
    )
    frequencies = librosa.cqt_frequencies(
        N_BINS, fmin=c1_hz, bins_per_octave=BINS_PER_OCTAVE, tuning=tuning
    )
    cqt = cqt * np.sqrt(frequencies / REFERENCE_HZ)[:, None]
    activations = _note_activations(cqt)
    chroma = _fold_to_chroma(activations)

    energy = chroma.sum(axis=0)
    active = energy >= SILENCE_RATIO * float(energy.max())

    norms = np.linalg.norm(chroma, axis=0)
    normalized = chroma / np.where(norms > 0, norms, 1.0)
    _, bank = template_bank(AUDIO_QUALITIES)
    frame_labels = np.where(active, np.argmax(bank @ normalized, axis=0), _NO_CHORD)

    smoothed = _majority_filter(frame_labels, SMOOTH_FRAMES)
    runs = _merge_short_runs(_runs(smoothed), MIN_SEGMENT_FRAMES)

    frame_seconds = HOP_LENGTH / sr
    chords: list[ChordEvent] = []
    for label, start, end in runs:
        if label == _NO_CHORD:
            continue
        found = _chord_for_segment(
            chroma[:, start:end].sum(axis=1), _estimate_bass(activations, start, end)
        )
        if found is None:
            continue
        start_seconds = max(0.0, (start - 0.5) * frame_seconds)
        end_seconds = min(duration, (end - 0.5) * frame_seconds)
        if end_seconds - start_seconds <= 0.0:
            continue
        chords.append(
            ChordEvent(
                root_pitch_class=found.root,
                quality=found.quality,
                bass_pitch_class=found.bass,
                start_seconds=start_seconds,
                duration_seconds=end_seconds - start_seconds,
                confidence=found.confidence,
                source=EstimationSource.DETECTED,
                ambiguous=found.ambiguous,
                alternatives=found.alternatives,
            )
        )

    return ChordAnalysisResult(chords=tuple(_merge_adjacent(chords)), duration_seconds=duration)


def estimate_chords(audio_path: Path, *, timeout_seconds: int) -> ChordAnalysisResult:
    """Estime les accords d'un fichier audio. Un résultat vide est légitime
    (silence, contenu non harmonique) : aucun accord n'est jamais inventé."""

    def _run() -> ChordAnalysisResult:
        import librosa

        y, sr = librosa.load(str(audio_path), sr=None, mono=True)
        return _analyze(y, int(sr))

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            raise ChordAnalysisTimeoutError(
                "Le délai maximal d'estimation des accords a été dépassé."
            ) from exc
        except Exception as exc:  # noqa: BLE001 — jamais de faux résultat sur échec
            logger.exception("Échec de l'estimation d'accords sur %s", audio_path.name)
            raise ChordAnalysisError("L'estimation des accords a échoué.") from exc
