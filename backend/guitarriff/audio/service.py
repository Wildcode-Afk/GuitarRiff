"""Orchestration de la normalisation d'un fichier audio déjà stocké.

Relie `acquisition/storage.py` (où vit le fichier) et `audio/ffmpeg.py`
(comment le convertir) : vérifie la durée, convertit vers le format interne
cible, et persiste le résultat dans les métadonnées du fichier.
"""

from __future__ import annotations

from guitarriff.acquisition.storage import AudioFileStorage, StoredAudioFile
from guitarriff.audio.ffmpeg import (
    TARGET_CHANNELS,
    TARGET_SAMPLE_RATE,
    normalize_audio,
    probe_audio,
)
from guitarriff.config import Settings
from guitarriff.errors import AudioTooLongError
from guitarriff.logging_config import get_logger

logger = get_logger(__name__)


def normalize_stored_audio(
    file_id: str, settings: Settings, storage: AudioFileStorage
) -> StoredAudioFile:
    """Normalise le fichier audio identifié par `file_id` et renvoie ses
    métadonnées mises à jour.

    Lève `AudioTooLongError` si la durée réelle du fichier dépasse
    `settings.audio_max_duration_seconds`, `InvalidAudioFileError` si le
    fichier n'est pas un audio exploitable, `FFmpegUnavailableError` si
    FFmpeg/ffprobe sont absents, ou `AudioProcessingTimeoutError` /
    `AudioProcessingError` en cas d'échec de la conversion elle-même.
    """

    source_path = storage.audio_path(file_id)

    probe = probe_audio(source_path, timeout_seconds=settings.ffmpeg_timeout_seconds)
    if probe.duration_seconds > settings.audio_max_duration_seconds:
        raise AudioTooLongError(
            "La durée du fichier audio dépasse la limite autorisée.",
            details={
                "duration_seconds": probe.duration_seconds,
                "max_duration_seconds": settings.audio_max_duration_seconds,
            },
        )

    target_path = storage.normalized_path(file_id)
    normalize_audio(source_path, target_path, timeout_seconds=settings.ffmpeg_timeout_seconds)

    logger.info(
        "Fichier %s normalisé (%.1fs, %dHz source -> %dHz cible, %d canal/canaux source)",
        file_id,
        probe.duration_seconds,
        probe.sample_rate,
        TARGET_SAMPLE_RATE,
        probe.channels,
    )

    return storage.update_metadata(
        file_id,
        duration_seconds=probe.duration_seconds,
        normalized=True,
        normalized_sample_rate=TARGET_SAMPLE_RATE,
        normalized_channels=TARGET_CHANNELS,
    )
