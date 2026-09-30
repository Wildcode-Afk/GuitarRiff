"""Gestion centralisée des erreurs de l'API.

Toutes les erreurs métier passent par `AppError` (et ses sous-classes) pour
obtenir une réponse JSON cohérente. Les erreurs non prévues (bugs, exceptions
non gérées) passent par `generic_exception_handler`, qui journalise le détail
complet côté serveur mais ne renvoie jamais de trace, de chemin système ou de
message d'exception brut au client — voir docs/API.md, section "Erreurs".
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from guitarriff.logging_config import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Erreur métier de base. Toujours renvoyée au client sous la forme
    {"error": {"code": ..., "message": ..., "details": ...}}."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    error_code: str = "app_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"


class ValidationAppError(AppError):
    """Erreur de validation métier (distincte de la validation de schéma
    FastAPI/Pydantic, qui est gérée par `validation_exception_handler`)."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_code = "validation_error"


def _envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.error_code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # On ne garde que loc/msg/type : les objets d'erreur Pydantic peuvent
        # embarquer des références internes qui n'ont rien à faire dans une
        # réponse HTTP.
        safe_errors = [
            {"loc": list(err.get("loc", [])), "msg": err.get("msg"), "type": err.get("type")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_envelope(
                "validation_error", "Les données envoyées sont invalides.", {"errors": safe_errors}
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Couvre notamment les 404 (route inconnue) et 405 (méthode non
        # autorisée) levées par le routeur avant d'atteindre nos vues.
        detail = exc.detail if isinstance(exc.detail, str) else "Erreur HTTP."
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(f"http_{exc.status_code}", detail),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Détail complet côté serveur uniquement — jamais dans la réponse.
        logger.exception("Erreur interne non gérée sur %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("internal_error", "Une erreur interne est survenue."),
        )
