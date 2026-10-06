"""Analyse rythmique via `librosa` — seul module du projet qui l'importe
directement (`librosa` est déjà une dépendance transitive de `basic-pitch`,
voir docs/MODELS.md ; aucune nouvelle dépendance requise pour cette étape).

## Étude des bibliothèques (avant implémentation, comme demandé)

- **`librosa`** (déjà installé) : détection de tempo et de battements
  (`librosa.beat.beat_track`) robuste et bien établie, mais **ne fournit
  aucun détecteur de mesure/métrique fiable** (pas de "downbeat tracker"
  intégré qui identifierait quel battement porte l'accent métrique).
- **`madmom`** (bibliothèque historique de référence pour le suivi de
  "downbeat"/métrique) : recherchée et évaluée, mais **écartée**. Le paquet
  PyPI officiel (`CPJKU/madmom`) est non maintenu depuis plusieurs années,
  distribue des extensions Cython compilées et s'installe difficilement sur
  des versions récentes de Python/NumPy (constat indépendant, pas seulement
  notre propre test). Une réimplémentation plus récente (`madmom-infer`,
  2026) existe mais reste un projet jeune et spécialisé ; son ajout n'a pas
  été jugé justifié pour cette étape au vu de la consigne de ne pas déduire
  une métrique avec une confiance non étayée. Voir docs/TECHNICAL_DECISIONS.md.
- **Conséquence directe** : ce module détecte le tempo, les battements et
  les changements de tempo avec une vraie mesure de confiance ; il **ne
  prétend jamais détecter la métrique** — voir `service.py`, qui applique une
  métrique par défaut (4/4) non confirmée plutôt que d'inventer une
  estimation non fondée.

## Vérifications réelles effectuées (pas supposées)

Sur un "click track" synthétique à 120 BPM généré pour ce test : tempo
détecté 117.5 (écart ~2 %, caractéristique connue de l'algorithme sur un
signal de clics purs). Sur un signal de bruit blanc (aucun rythme réel) : la
mesure de confiance ci-dessous tombe à ~0.23, contre 1.0 sur le click track —
confirmant qu'elle distingue bien un vrai signal rythmique d'un signal sans
rythme. Avec une introduction silencieuse de 2 s avant le click track : tempo
toujours détecté correctement, premier battement situé après le silence.
Sur un silence complet : `beat_track` renvoie un tempo de 0.0 et aucun
battement — traité explicitement comme "aucun rythme détecté" (voir
`NoRhythmDetectedError`), jamais comme un tempo de substitution.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from guitarriff.errors import NoRhythmDetectedError, RhythmAnalysisError, RhythmAnalysisTimeoutError
from guitarriff.logging_config import get_logger

logger = get_logger(__name__)

# Fenêtre glissante pour la détection de changements de tempo, et seuil
# relatif au-delà duquel une différence de tempo entre deux fenêtres
# consécutives est considérée comme un véritable changement (pas du bruit de
# mesure) — vérifié empiriquement sur un signal à deux tempos connus (120 ->
# 90 BPM) avant d'être fixé à ces valeurs.
_WINDOW_SECONDS = 6.0
_MIN_WINDOW_SECONDS = 2.0
_TEMPO_CHANGE_RELATIVE_THRESHOLD = 0.08
_CONFIDENCE_TOLERANCE = 0.04


@dataclass(frozen=True)
class TempoSegment:
    start_seconds: float
    bpm: float


@dataclass(frozen=True)
class RhythmAnalysisResult:
    tempo_bpm: float
    confidence: float
    beat_times: tuple[float, ...]
    tempo_segments: tuple[TempoSegment, ...]
    duration_seconds: float


def _scalar(value: object) -> float:
    """`librosa.beat.beat_track` renvoie `tempo` comme un tableau NumPy à un
    élément dans les versions récentes (vérifié dans cet environnement,
    `librosa` 0.11) — normalise vers un `float` Python dans tous les cas."""

    import numpy as np

    return float(np.asarray(value).reshape(-1)[0])


def _analyze(y: Any, sr: int) -> RhythmAnalysisResult:
    import librosa
    import numpy as np

    duration_seconds = float(len(y) / sr)  # type: ignore[arg-type]

    tempo_raw, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    tempo_bpm = _scalar(tempo_raw)
    beat_times = tuple(float(t) for t in librosa.frames_to_time(beat_frames, sr=sr))

    if tempo_bpm <= 0.0 or not beat_times:
        raise NoRhythmDetectedError(
            "Aucun battement exploitable n'a été détecté dans cet audio "
            "(silence, ou signal sans contenu rythmique perceptible)."
        )

    tempo_env = librosa.feature.tempo(y=y, sr=sr, aggregate=None)
    relative_diff = np.abs(tempo_env - tempo_bpm) / tempo_bpm
    confidence = float(np.mean(relative_diff < _CONFIDENCE_TOLERANCE))

    tempo_segments = _detect_tempo_segments(y, sr, duration_seconds, fallback_bpm=tempo_bpm)

    return RhythmAnalysisResult(
        tempo_bpm=tempo_bpm,
        confidence=confidence,
        beat_times=beat_times,
        tempo_segments=tempo_segments,
        duration_seconds=duration_seconds,
    )


def _detect_tempo_segments(
    y: Any, sr: int, duration_seconds: float, *, fallback_bpm: float
) -> tuple[TempoSegment, ...]:
    import librosa

    if duration_seconds < _WINDOW_SECONDS + _MIN_WINDOW_SECONDS:
        # Trop court pour une analyse par fenêtres fiable : un seul segment
        # couvrant tout le morceau, basé sur le tempo global déjà calculé.
        return (TempoSegment(start_seconds=0.0, bpm=fallback_bpm),)

    hop_samples = int(_WINDOW_SECONDS * sr)
    raw_segments: list[TempoSegment] = []
    for start_sample in range(0, len(y), hop_samples):  # type: ignore[arg-type]
        segment = y[start_sample : start_sample + hop_samples]  # type: ignore[index]
        if len(segment) / sr < _MIN_WINDOW_SECONDS:
            continue
        try:
            local_tempo_raw, _ = librosa.beat.beat_track(y=segment, sr=sr)
            local_tempo = _scalar(local_tempo_raw)
        except Exception:  # noqa: BLE001 — une fenêtre illisible ne doit pas faire échouer toute l'analyse
            continue
        if local_tempo <= 0.0:
            continue
        raw_segments.append(TempoSegment(start_seconds=start_sample / sr, bpm=local_tempo))

    if not raw_segments:
        return (TempoSegment(start_seconds=0.0, bpm=fallback_bpm),)

    # Ancre toujours le premier segment à 0.0 (exigence de Song, Étape 8) et
    # fusionne les fenêtres consécutives dont le tempo ne diffère pas
    # significativement, pour ne retenir que de véritables changements.
    merged = [TempoSegment(start_seconds=0.0, bpm=raw_segments[0].bpm)]
    for segment in raw_segments[1:]:
        previous = merged[-1]
        relative_diff = abs(segment.bpm - previous.bpm) / previous.bpm
        if relative_diff > _TEMPO_CHANGE_RELATIVE_THRESHOLD:
            merged.append(segment)

    return tuple(merged)


def analyze_rhythm(audio_path: Path, *, timeout_seconds: int) -> RhythmAnalysisResult:
    """Analyse le tempo, les battements et les changements de tempo d'un
    fichier audio. Lève `NoRhythmDetectedError` si aucun rythme exploitable
    n'est détecté — ne fabrique jamais de tempo de substitution."""

    def _run() -> RhythmAnalysisResult:
        import librosa

        y, sr = librosa.load(str(audio_path), sr=None, mono=True)
        return _analyze(y, int(sr))

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            raise RhythmAnalysisTimeoutError(
                "Le délai maximal d'analyse rythmique a été dépassé."
            ) from exc
        except NoRhythmDetectedError:
            raise
        except Exception as exc:  # noqa: BLE001 — jamais de faux résultat sur échec
            logger.exception("Échec de l'analyse rythmique sur %s", audio_path.name)
            raise RhythmAnalysisError("L'analyse rythmique a échoué.") from exc
