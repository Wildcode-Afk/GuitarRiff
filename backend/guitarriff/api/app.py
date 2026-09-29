"""Point d'entrée de l'API FastAPI.

À ce stade (Étape 2 — fondations), l'application n'expose que la vérification
de démarrage (`/health`). Aucune route de transcription/tablature n'existe
encore : elles seront ajoutées derrière l'interface `Transcriber` décrite dans
docs/ARCHITECTURE.md, une fois cette étape validée.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from guitarriff.api.routes.health import router as health_router
from guitarriff.config import Settings, get_settings
from guitarriff.logging_config import configure_logging, get_logger

logger = get_logger(__name__)


def _make_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "GuitarRiff démarré (env=%s, data_dir=%s, job_concurrency=%d)",
            settings.app_env.value,
            settings.data_dir,
            settings.job_concurrency,
        )
        yield

    return lifespan


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="GuitarRiff API",
        version="0.1.0",
        description=(
            "API de GuitarRiff — squelette d'application (Étape 2). "
            "Aucune fonctionnalité de transcription audio à ce stade."
        ),
        lifespan=_make_lifespan(settings),
    )
    app.state.settings = settings

    app.include_router(health_router)

    return app


app = create_app()
