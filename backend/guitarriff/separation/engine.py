"""Exécution de la séparation via Demucs — **seul module du projet qui
importe `torch`/`demucs`**, à l'image de l'isolation déjà appliquée à
`basic-pitch` dans l'architecture (voir docs/ARCHITECTURE.md, principe 2).

`demucs` est une dépendance **optionnelle** (extra `separation` du
`pyproject.toml`) : son absence doit être une situation normale et bien
gérée, pas une erreur de configuration. Voir `DemucsNotInstalledError`.

## Avertissement honnête sur cette implémentation

L'appel à l'API Python de Demucs ci-dessous suit le schéma documenté par le
projet Demucs lui-même (`AudioFile` → `apply_model` → `save_audio`). Il n'a
**pas pu être exécuté contre une installation réelle de `torch`+`demucs`
dans cet environnement** : l'installation par défaut de `torch` depuis PyPI
entraîne toute la pile CUDA (plusieurs Go, vérifié par une résolution de
dépendances réelle — voir docs/MODELS.md) et dépasse largement l'espace
disque disponible dans ce bac à sable, sans index PyPI dédié au CPU
accessible depuis ce réseau restreint. **À valider sur un environnement réel
avant mise en production** — voir docs/PROJECT_STATUS.md.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from guitarriff.errors import (
    DemucsNotInstalledError,
    SeparationError,
    SeparationModelUnavailableError,
)
from guitarriff.logging_config import get_logger
from guitarriff.separation.models import SeparationModelInfo
from guitarriff.separation.progress import Stage

logger = get_logger(__name__)


def _import_demucs() -> tuple[Any, Any, Any, Any, Any]:
    try:
        import torch
        from demucs.apply import apply_model
        from demucs.audio import AudioFile, save_audio
        from demucs.pretrained import get_model
    except ImportError as exc:
        raise DemucsNotInstalledError(
            "Demucs n'est pas installé. Installez l'extra optionnel "
            "'separation' (voir docs/MODELS.md) pour activer cette "
            "fonctionnalité."
        ) from exc
    return torch, apply_model, AudioFile, save_audio, get_model  # type: ignore[return-value]


def run_separation(
    source_path: Path,
    output_dir: Path,
    model_info: SeparationModelInfo,
    *,
    allow_model_download: bool,
    on_stage: Callable[[Stage], None] | None = None,
) -> list[str]:
    """Exécute la séparation et écrit un fichier WAV par piste dans
    `output_dir`. Renvoie la liste des noms de pistes produites.

    Toujours exécuté sur CPU (`device="cpu"`) — aucune détection/usage de GPU
    à ce stade, conformément au mode CPU demandé pour cette étape.
    """

    torch, apply_model, AudioFile, save_audio, get_model = _import_demucs()

    def _report(stage: Stage) -> None:
        if on_stage:
            on_stage(stage)

    _report(Stage.LOADING_MODEL)

    if not allow_model_download:
        # Limitation assumée (voir docstring du module et docs/MODELS.md) :
        # nous n'avons pas pu vérifier de façon fiable, dans cet
        # environnement, l'emplacement exact du cache des modèles
        # pré-entraînés de Demucs. Ce réglage refuse donc tout chargement
        # plutôt que de tenter une détection de cache non fiable.
        raise SeparationModelUnavailableError(
            "Le téléchargement automatique des modèles de séparation est "
            "désactivé (SEPARATION_ALLOW_MODEL_DOWNLOAD=false).",
            details={"model": model_info.key},
        )

    try:
        model = get_model(model_info.key)
        model.eval()
    except Exception as exc:
        logger.warning("Échec de chargement du modèle Demucs '%s': %s", model_info.key, exc)
        raise SeparationModelUnavailableError(
            "Impossible de charger le modèle de séparation (réseau "
            "indisponible ou modèle introuvable).",
            details={"model": model_info.key},
        ) from exc

    _report(Stage.SEPARATING)

    try:
        wav = AudioFile(str(source_path)).read(
            streams=0, samplerate=model.samplerate, channels=model.audio_channels
        )
        reference = wav.mean(0)
        normalized = (wav - reference.mean()) / reference.std()
        with torch.no_grad():
            estimated_sources = apply_model(model, normalized[None], device="cpu", progress=False)[
                0
            ]
        estimated_sources = estimated_sources * reference.std() + reference.mean()
    except Exception as exc:
        logger.error("Échec de séparation Demucs sur %s: %s", source_path.name, exc)
        raise SeparationError("La séparation audio a échoué.") from exc

    _report(Stage.WRITING_STEMS)

    output_dir.mkdir(parents=True, exist_ok=True)
    produced: list[str] = []
    for waveform, stem_name in zip(estimated_sources, model.sources, strict=True):
        stem_path = output_dir / f"{stem_name}.wav"
        save_audio(waveform, str(stem_path), model.samplerate)
        produced.append(stem_name)

    return produced
