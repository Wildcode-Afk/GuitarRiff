"""Point d'entrée de l'API FastAPI.

À ce stade (Étape 6), l'application expose : la vérification de démarrage
(`/health`, avec vérification de la disponibilité de FFmpeg en mode
`verbose`), la version (`/version`), l'import/consultation/suppression/
normalisation de fichiers audio locaux (`/audio-files`), l'import audio
depuis YouTube (`/youtube-imports`), une gestion d'erreurs cohérente et la
configuration CORS pour le frontend. Aucune transcription n'existe encore :
elle sera ajoutée derrière l'interface `Transcriber` décrite dans
docs/ARCHITECTURE.md, une fois cette étape validée.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from guitarriff.api.routes.audio_files import router as audio_files_router
from guitarriff.api.routes.health import router as health_router
from guitarriff.api.routes.version import router as version_router
from guitarriff.api.routes.youtube_imports import router as youtube_imports_router
from guitarriff.config import Settings, get_settings
from guitarriff.errors import register_error_handlers
from guitarriff.logging_config import configure_logging, get_logger

logger = get_logger(__name__)

API_DESCRIPTION = """
API de GuitarRiff — socle serveur (Étape 6).

Aucune fonctionnalité de transcription audio n'est encore exposée à ce
stade. Voir `docs/API.md` pour le détail des routes disponibles et le
format des erreurs.
""".strip()


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
        description=API_DESCRIPTION,
        lifespan=_make_lifespan(settings),
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    app.include_router(health_router)
    app.include_router(version_router)
    app.include_router(audio_files_router)
    app.include_router(youtube_imports_router)

    return app


app = create_app()
