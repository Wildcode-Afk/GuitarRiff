"""Route de santé — vérifie que l'application démarre et que la configuration
est chargée, sans dépendre d'aucune fonctionnalité audio.

Ne jamais exposer de chemin absolu du système de fichiers dans la réponse
(voir docs/API.md, section "Sécurité") : le mode `verbose` renvoie des
indicateurs booléens, jamais les chemins eux-mêmes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from guitarriff.audio.ffmpeg import ffmpeg_available
from guitarriff.config import Settings, get_settings

router = APIRouter(tags=["health"])


def _is_data_dir_writable(settings: Settings) -> bool:
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.data_dir / ".write_check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


@router.get("/health")
def health(verbose: bool = False, settings: Settings = Depends(get_settings)) -> dict:  # noqa: B008
    payload: dict[str, Any] = {
        "status": "ok",
        "app_env": settings.app_env.value,
        "job_concurrency": settings.job_concurrency,
        "ytdlp_enabled": settings.ytdlp_enabled,
    }
    if verbose:
        payload["checks"] = {
            "data_dir_writable": _is_data_dir_writable(settings),
            "ffmpeg_available": ffmpeg_available(),
        }
    return payload
