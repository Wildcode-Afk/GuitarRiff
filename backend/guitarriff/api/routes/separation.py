"""Routes de séparation d'instruments (Étape 7).

Rappel systématique dans les réponses : la séparation n'est jamais parfaite
— voir `notes` dans chaque réponse, et `docs/API.md`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.api.routes.audio_files import get_storage
from guitarriff.config import Settings, get_settings
from guitarriff.errors import NotFoundError, ValidationAppError
from guitarriff.separation import service
from guitarriff.separation.models import get_mode

router = APIRouter(prefix="/audio-files/{file_id}/separate", tags=["separation"])


class SeparationRequest(BaseModel):
    mode: str = Field(default="htdemucs")


class SeparationStatusResponse(BaseModel):
    file_id: str
    mode: str
    stage: str
    progress_percent: int
    stems: list[str] | None = None
    error: str | None = None
    notes: str
    experimental: bool


def _to_response(file_id: str, status: service.SeparationStatus) -> SeparationStatusResponse:
    return SeparationStatusResponse(
        file_id=file_id,
        mode=status.mode,
        stage=status.stage,
        progress_percent=status.progress_percent,
        stems=status.stems,
        error=status.error,
        notes=status.notes,
        experimental=status.experimental,
    )


@router.post("", status_code=202, response_model=SeparationStatusResponse)
def start_separation(
    file_id: str,
    body: SeparationRequest,
    settings: Settings = Depends(get_settings),  # noqa: B008
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> SeparationStatusResponse:
    status = service.start_separation(file_id, body.mode, settings, storage)
    return _to_response(file_id, status)


@router.get("/{mode}", response_model=SeparationStatusResponse)
def get_separation_status(
    file_id: str,
    mode: str,
    settings: Settings = Depends(get_settings),  # noqa: B008
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> SeparationStatusResponse:
    # Valide que le fichier existe (lève NotFoundError sinon).
    storage.get(file_id)
    status = service.get_status(file_id, mode, settings, storage)
    return _to_response(file_id, status)


@router.get("/{mode}/stems/{stem_name}")
def download_stem(
    file_id: str,
    mode: str,
    stem_name: str,
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> FileResponse:
    storage.get(file_id)
    model_info = get_mode(mode)
    if stem_name not in model_info.stems:
        raise ValidationAppError(
            "Piste inconnue pour ce mode de séparation.",
            details={
                "mode": mode,
                "requested_stem": stem_name,
                "available_stems": list(model_info.stems),
            },
        )

    stem_path = storage.separated_dir(file_id, mode) / f"{stem_name}.wav"
    if not stem_path.is_file():
        raise NotFoundError(
            "Cette piste n'a pas encore été calculée (lancez la séparation d'abord).",
            details={"file_id": file_id, "mode": mode, "stem": stem_name},
        )
    return FileResponse(stem_path, media_type="audio/wav", filename=f"{stem_name}.wav")
