"""Acquisition audio depuis YouTube (décision Q1 — voir
docs/TECHNICAL_DECISIONS.md).

Utilise `yt-dlp` **via son API Python** (jamais en ligne de commande/`shell`),
ce qui élimine par construction tout risque de construction d'une commande
système à partir d'une entrée utilisateur : il n'y a aucune commande shell
nulle part dans ce module.

Usage prévu : strictement personnel, sous la responsabilité de l'utilisateur
final. Ce module ne contourne aucune restriction d'accès — pas
d'authentification, pas de cookies, pas de contournement géographique. Une
vidéo privée, limitée par l'âge ou autrement restreinte échoue normalement et
renvoie une erreur claire plutôt que d'être contournée.
"""

from __future__ import annotations

import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any

import yt_dlp

from guitarriff.acquisition.storage import AudioFileStorage, StoredAudioFile
from guitarriff.acquisition.youtube_url import normalize_youtube_url
from guitarriff.config import Settings
from guitarriff.errors import (
    YoutubeTimeoutError,
    YoutubeUnavailableError,
    YoutubeVideoTooLongError,
)
from guitarriff.logging_config import get_logger

logger = get_logger(__name__)

# Options yt-dlp volontairement minimales et sans contournement de
# restriction : pas de `cookiefile`, pas de `geo_bypass`, pas
# d'authentification. Une vidéo que yt-dlp ne peut pas extraire normalement
# est traitée comme indisponible, point final.
_COMMON_YDL_OPTS: dict[str, Any] = {
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "socket_timeout": 30,
}


@dataclass(frozen=True)
class YoutubeMetadata:
    video_id: str
    title: str
    duration_seconds: int | None
    uploader: str | None
    webpage_url: str
    is_live: bool


def _run_with_timeout(func: Any, *, timeout_seconds: int) -> Any:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            # Remarque honnête (voir docs/PROJECT_STATUS.md) : ceci borne le
            # temps d'attente côté appelant, qui reçoit une erreur propre.
            # Le thread yt-dlp sous-jacent peut continuer en arrière-plan
            # jusqu'à son propre `socket_timeout` ; il n'y a pas de
            # kill-switch dur sans passer par un sous-processus.
            raise YoutubeTimeoutError(
                "Le délai maximal pour l'opération YouTube a été dépassé."
            ) from exc


def fetch_metadata(url: str, settings: Settings) -> YoutubeMetadata:
    """Récupère les métadonnées d'une vidéo YouTube, sans rien télécharger."""

    canonical_url = normalize_youtube_url(url)

    def _extract() -> dict[str, Any]:
        with yt_dlp.YoutubeDL({**_COMMON_YDL_OPTS, "skip_download": True}) as ydl:
            info = ydl.extract_info(canonical_url, download=False)
            if info is None:
                raise YoutubeUnavailableError(
                    "Impossible de récupérer les informations de la vidéo."
                )
            return info

    try:
        info = _run_with_timeout(
            _extract, timeout_seconds=settings.youtube_download_timeout_seconds
        )
    except YoutubeTimeoutError:
        raise
    except yt_dlp.utils.DownloadError as exc:
        logger.warning("Échec d'extraction des métadonnées YouTube: %s", exc)
        raise YoutubeUnavailableError("Vidéo YouTube indisponible ou inaccessible.") from exc

    return YoutubeMetadata(
        video_id=info.get("id", ""),
        title=info.get("title") or "Vidéo YouTube",
        duration_seconds=info.get("duration"),
        uploader=info.get("uploader"),
        webpage_url=info.get("webpage_url", canonical_url),
        is_live=bool(info.get("is_live")),
    )


def _check_duration(metadata: YoutubeMetadata, settings: Settings) -> None:
    if metadata.is_live:
        raise YoutubeVideoTooLongError(
            "Les flux en direct ne sont pas supportés (durée non déterminée)."
        )
    if metadata.duration_seconds is None:
        raise YoutubeVideoTooLongError("Durée de la vidéo inconnue — import refusé par précaution.")
    if metadata.duration_seconds > settings.youtube_max_duration_seconds:
        raise YoutubeVideoTooLongError(
            "La vidéo dépasse la durée maximale autorisée.",
            details={
                "duration_seconds": metadata.duration_seconds,
                "max_duration_seconds": settings.youtube_max_duration_seconds,
            },
        )


def download_audio(url: str, settings: Settings, storage: AudioFileStorage) -> StoredAudioFile:
    """Télécharge l'audio d'une vidéo YouTube et le stocke via `AudioFileStorage`.

    Réutilise exactement le même pipeline de sécurité que l'import de fichier
    local (Étape 4) : détection de format par contenu réel, identifiant
    interne généré côté serveur. Aucun champ fourni par l'utilisateur (titre
    de la vidéo, etc.) ne participe à la construction d'un chemin sur le
    disque.
    """

    canonical_url = normalize_youtube_url(url)
    metadata = fetch_metadata(canonical_url, settings)
    _check_duration(metadata, settings)

    settings.youtube_tmp_dir.mkdir(parents=True, exist_ok=True)
    job_dir = settings.youtube_tmp_dir / str(uuid.uuid4())
    job_dir.mkdir(parents=True, exist_ok=False)

    try:
        ydl_opts: dict[str, Any] = {
            **_COMMON_YDL_OPTS,
            "format": "bestaudio/best",
            "outtmpl": str(job_dir / "audio.%(ext)s"),
            "max_filesize": settings.max_upload_size_bytes,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                }
            ],
        }

        def _download() -> None:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([canonical_url])

        try:
            _run_with_timeout(_download, timeout_seconds=settings.youtube_download_timeout_seconds)
        except YoutubeTimeoutError:
            raise
        except yt_dlp.utils.DownloadError as exc:
            logger.warning("Échec de téléchargement YouTube: %s", exc)
            raise YoutubeUnavailableError(
                "Le téléchargement de la vidéo YouTube a échoué."
            ) from exc

        downloaded_files = list(job_dir.glob("audio.*"))
        if not downloaded_files:
            raise YoutubeUnavailableError(
                "Le téléchargement n'a produit aucun fichier audio exploitable."
            )

        audio_path = downloaded_files[0]
        content = audio_path.read_bytes()

        return storage.save(
            filename=f"{metadata.video_id}{audio_path.suffix}",
            declared_content_type="audio/wav",
            content=content,
            source="youtube",
            source_url=metadata.webpage_url,
            title=metadata.title,
        )
    finally:
        # Nettoyage du répertoire temporaire de travail, succès ou échec.
        shutil.rmtree(job_dir, ignore_errors=True)


def _cleanup_stale_tmp_dirs(settings: Settings) -> int:
    """Utilitaire de nettoyage pour d'éventuels répertoires temporaires
    laissés par un arrêt brutal du processus. Non appelé automatiquement à
    ce stade — prévu pour un futur usage manuel ou planifié."""

    root = settings.youtube_tmp_dir
    count = 0
    if root.is_dir():
        for entry in root.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
                count += 1
    return count
