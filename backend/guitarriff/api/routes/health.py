"""Route de santé — vérifie que l'application démarre et que la configuration
est chargée, sans dépendre d'aucune fonctionnalité audio."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from guitarriff.config import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:  # noqa: B008
    return {
        "status": "ok",
        "app_env": settings.app_env.value,
        "job_concurrency": settings.job_concurrency,
        "ytdlp_enabled": settings.ytdlp_enabled,
    }
