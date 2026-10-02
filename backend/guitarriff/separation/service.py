"""Orchestration de la séparation d'instruments.

Relie le stockage (cache sur disque, métadonnées), la détection de capacités
(mémoire disponible), le suivi de progression et le moteur Demucs
(`engine.py`). C'est ici, pas dans `engine.py`, que vivent : le cache
("éviter de relancer inutilement"), la vérification mémoire, la limite de
durée et le calcul du statut exposé par l'API.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from time import time

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.audio.ffmpeg import probe_audio
from guitarriff.config import Settings
from guitarriff.errors import (
    AudioTooLongError,
    InsufficientMemoryError,
    SeparationInProgressError,
)
from guitarriff.logging_config import get_logger
from guitarriff.separation import capabilities
from guitarriff.separation.engine import run_separation
from guitarriff.separation.models import SeparationModelInfo, get_mode
from guitarriff.separation.progress import Stage, progress_store

logger = get_logger(__name__)

_CACHE_META_FILENAME = "meta.json"


@dataclass(frozen=True)
class SeparationStatus:
    file_id: str
    mode: str
    stage: str
    progress_percent: int
    stems: list[str] | None
    error: str | None
    notes: str
    experimental: bool


def _cache_meta_path(storage: AudioFileStorage, file_id: str, mode: str) -> Path:
    return storage.separated_dir(file_id, mode) / _CACHE_META_FILENAME


def _read_cache(storage: AudioFileStorage, file_id: str, mode: str) -> list[str] | None:
    meta_path = _cache_meta_path(storage, file_id, mode)
    if not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        stems = data.get("stems")
        return list(stems) if isinstance(stems, list) else None
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(storage: AudioFileStorage, file_id: str, mode: str, stems: list[str]) -> None:
    meta_path = _cache_meta_path(storage, file_id, mode)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps({"stems": stems}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_status(
    file_id: str, mode: str, settings: Settings, storage: AudioFileStorage
) -> SeparationStatus:
    model_info = get_mode(mode)

    cached_stems = _read_cache(storage, file_id, mode)
    if cached_stems is not None:
        return _status_from(model_info, Stage.DONE, 100, cached_stems, None)

    entry = progress_store.get(file_id, mode)
    if entry is None:
        return _status_from(model_info, Stage.QUEUED, 0, None, None, stage_label="not_started")

    if entry.stage not in (Stage.DONE, Stage.ERROR) and (
        time() - entry.started_at > settings.separation_timeout_seconds
    ):
        # Limitation honnête (voir engine.py) : le thread sous-jacent peut
        # continuer en arrière-plan ; ceci borne uniquement l'état visible
        # côté client.
        return _status_from(
            model_info,
            Stage.ERROR,
            100,
            None,
            "Le délai maximal de séparation a été dépassé.",
        )

    return _status_from(
        model_info, entry.stage, entry.progress_percent, entry.stems, entry.error_message
    )


def _status_from(
    model_info: SeparationModelInfo,
    stage: Stage,
    progress_percent: int,
    stems: list[str] | None,
    error: str | None,
    *,
    stage_label: str | None = None,
) -> SeparationStatus:
    return SeparationStatus(
        file_id="",  # renseigné par l'appelant si besoin ; non utilisé en interne
        mode=model_info.key,
        stage=stage_label or stage.value,
        progress_percent=progress_percent,
        stems=stems,
        error=error,
        notes=model_info.notes,
        experimental=model_info.experimental,
    )


def start_separation(
    file_id: str, mode: str, settings: Settings, storage: AudioFileStorage
) -> SeparationStatus:
    """Démarre une séparation (ou renvoie l'état déjà en cache/en cours).

    Ne lève jamais pour "déjà en cache" : c'est un succès (rien à refaire).
    Lève `SeparationInProgressError` si une séparation est déjà en cours
    pour ce couple (fichier, mode) — évite les exécutions concurrentes
    inutiles sur la même ressource.
    """

    model_info = get_mode(mode)

    # Valide l'existence du fichier avant toute chose.
    storage.get(file_id)

    cached_stems = _read_cache(storage, file_id, mode)
    if cached_stems is not None:
        logger.info("Séparation '%s' déjà en cache pour %s — pas de relance.", mode, file_id)
        return _status_from(model_info, Stage.DONE, 100, cached_stems, None)

    if progress_store.is_running(file_id, mode):
        raise SeparationInProgressError(
            "Une séparation est déjà en cours pour ce fichier et ce mode.",
            details={"file_id": file_id, "mode": mode},
        )

    if model_info.key == "none":
        _write_cache(storage, file_id, mode, list(model_info.stems))
        _persist_separated_mode(storage, file_id, mode)
        return _status_from(model_info, Stage.DONE, 100, list(model_info.stems), None)

    _check_memory(settings)
    _check_duration(file_id, settings, storage)

    progress_store.start(file_id, mode)
    thread = threading.Thread(
        target=_run_in_background,
        args=(file_id, mode, model_info, settings, storage),
        daemon=True,
    )
    thread.start()

    return _status_from(model_info, Stage.QUEUED, 0, None, None)


def _check_memory(settings: Settings) -> None:
    _, available_mb = capabilities.get_memory_info_mb()
    if available_mb is not None and available_mb < settings.separation_min_available_memory_mb:
        raise InsufficientMemoryError(
            "Mémoire disponible insuffisante pour lancer une séparation.",
            details={
                "available_memory_mb": round(available_mb),
                "required_memory_mb": settings.separation_min_available_memory_mb,
            },
        )


def _check_duration(file_id: str, settings: Settings, storage: AudioFileStorage) -> None:
    source_path = storage.audio_path(file_id)
    probe = probe_audio(source_path, timeout_seconds=settings.ffmpeg_timeout_seconds)
    if probe.duration_seconds > settings.audio_max_duration_seconds:
        raise AudioTooLongError(
            "La durée du fichier dépasse la limite autorisée pour la séparation.",
            details={
                "duration_seconds": probe.duration_seconds,
                "max_duration_seconds": settings.audio_max_duration_seconds,
            },
        )


def _persist_separated_mode(storage: AudioFileStorage, file_id: str, mode: str) -> None:
    record = storage.get(file_id)
    if mode not in record.separated_modes:
        storage.update_metadata(file_id, separated_modes=[*record.separated_modes, mode])


def _run_in_background(
    file_id: str,
    mode: str,
    model_info: SeparationModelInfo,
    settings: Settings,
    storage: AudioFileStorage,
) -> None:
    def on_stage(stage: Stage) -> None:
        progress_store.set_stage(file_id, mode, stage)

    try:
        source_path = storage.audio_path(file_id)
        output_dir = storage.separated_dir(file_id, mode)
        stems = run_separation(
            source_path,
            output_dir,
            model_info,
            allow_model_download=settings.separation_allow_model_download,
            on_stage=on_stage,
        )
        _write_cache(storage, file_id, mode, stems)
        _persist_separated_mode(storage, file_id, mode)
        progress_store.set_done(file_id, mode, stems)
    except Exception as exc:  # noqa: BLE001 — isole le thread, jamais de crash silencieux
        logger.exception("Échec de la séparation en arrière-plan pour %s (%s)", file_id, mode)
        progress_store.set_error(file_id, mode, str(_safe_error_message(exc)))


def _safe_error_message(exc: Exception) -> str:
    # Les `AppError` ont un message déjà sûr à afficher ; toute autre
    # exception reste générique pour ne rien exposer d'interne.
    from guitarriff.errors import AppError

    if isinstance(exc, AppError):
        return exc.message
    return "La séparation a échoué pour une raison inattendue."
