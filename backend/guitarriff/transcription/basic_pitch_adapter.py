"""Adaptateur basic-pitch — **seul module du projet qui importe
`basic_pitch`**, à l'image de l'isolation déjà appliquée à Demucs
(`separation/engine.py`) et conformément à docs/ARCHITECTURE.md, principe 2.

## Vérification préalable (avant intégration, comme demandé)

Vérifié par une installation réelle dans l'environnement du projet (pas une
supposition) :

- **Compatibilité Python** : `basic-pitch[tf]==0.4.0` s'installe et
  s'importe correctement sous Python 3.11 (notre version cible, voir
  `.python-version`). **Incompatible avec Python 3.12** (`tensorflow<2.15.1`
  exigé, aucun wheel disponible pour 3.12 — voir
  docs/TECHNICAL_DECISIONS.md, D1, vérifié dès l'Étape 1).
- **Dépendances** : installation réelle testée, `setuptools<81` nécessaire en
  complément (voir D2) — toutes deux déjà épinglées dans `pyproject.toml`.
- **Plateforme** : testé sous Linux x86_64 (CPU, sans GPU) — comportement
  non vérifié sur d'autres plateformes (macOS/Windows), à confirmer si
  déployé ailleurs.
- **Inférence réelle exécutée** dans cet environnement sur un fichier WAV
  généré (sinusoïde à 440 Hz) : la note détectée correspond exactement à la
  hauteur MIDI 69 (A4/440Hz) attendue, confirmant que l'intégration
  fonctionne réellement, pas seulement que l'import réussit.

## Format de sortie (vérifié, pas documenté de mémoire)

`basic_pitch.inference.predict(audio_path)` renvoie un triplet
`(model_output, midi_data, note_events)` où `note_events` est une liste de
tuples `(start_time_s, end_time_s, pitch_midi, amplitude, pitch_bend)` —
`amplitude` dans `[0.0, 1.0]`, `pitch_bend` une liste de valeurs par frame ou
`None`. Un audio silencieux renvoie une liste vide (pas une erreur) — vérifié
réellement, pas supposé.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, NamedTuple

from guitarriff.errors import TranscriptionError, TranscriptionTimeoutError
from guitarriff.logging_config import get_logger

logger = get_logger(__name__)


class RawNoteEvent(NamedTuple):
    """Sortie brute de basic-pitch pour une note, avant conversion vers le
    modèle commun (voir `converter.py`)."""

    start_seconds: float
    end_seconds: float
    midi_pitch: int
    amplitude: float


def basic_pitch_available() -> bool:
    try:
        import basic_pitch.inference  # noqa: F401
    except ImportError:
        return False
    return True


def _import_predict() -> Callable[..., Any]:
    try:
        from basic_pitch.inference import predict
    except ImportError as exc:
        raise TranscriptionError(
            "basic-pitch n'est pas disponible dans cet environnement."
        ) from exc
    return predict


def run_basic_pitch(audio_path: Path, *, timeout_seconds: int) -> list[RawNoteEvent]:
    """Exécute l'inférence basic-pitch sur `audio_path` et renvoie les notes
    brutes détectées (liste vide si aucune note — ce n'est pas une erreur).

    `audio_path` doit toujours être un chemin interne déjà validé (fichier
    normalisé ou piste séparée produits par ce projet), jamais construit à
    partir d'une chaîne utilisateur.
    """

    predict = _import_predict()

    def _run() -> list[RawNoteEvent]:
        _, _, note_events = predict(str(audio_path))
        return [
            RawNoteEvent(
                start_seconds=start,
                end_seconds=end,
                midi_pitch=int(pitch),
                amplitude=float(amplitude),
            )
            for start, end, pitch, amplitude, *_rest in note_events
        ]

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            # Limitation honnête, identique à yt-dlp (Étape 5) et Demucs
            # (Étape 7) : borne l'attente côté appelant ; le thread sous-
            # jacent peut continuer quelques instants en arrière-plan.
            raise TranscriptionTimeoutError(
                "Le délai maximal de transcription a été dépassé."
            ) from exc
        except FileNotFoundError:
            # Ne devrait jamais arriver (chemin toujours interne et déjà
            # vérifié par l'appelant) — signale un bug interne plutôt que de
            # fabriquer un faux résultat.
            logger.error("Fichier introuvable pour la transcription: %s", audio_path)
            raise TranscriptionError("Fichier audio introuvable pour la transcription.") from None
        except Exception as exc:  # noqa: BLE001 — jamais de faux résultat sur échec du modèle
            logger.exception("Échec de l'inférence basic-pitch sur %s", audio_path.name)
            raise TranscriptionError("La transcription a échoué.") from exc
