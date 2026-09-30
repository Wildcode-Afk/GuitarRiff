"""Route d'information sur la version de l'API."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter

router = APIRouter(tags=["version"])


def _get_version() -> str:
    try:
        return version("guitarriff")
    except PackageNotFoundError:
        # Package non installé en mode standard (ex. certains contextes de
        # test) — on retombe sur une valeur connue plutôt que de planter.
        return "0.0.0-dev"


@router.get("/version")
def get_version() -> dict:
    return {"name": "guitarriff", "version": _get_version()}
