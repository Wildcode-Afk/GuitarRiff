"""Routes de transcription (Étape 9).

Toujours un rappel explicite dans la réponse : basic-pitch n'est jamais
parfait — voir `notes` dans `POST .../transcribe`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.api.routes.audio_files import get_storage
from guitarriff.config import Settings, get_settings
from guitarriff.errors import NotFoundError
from guitarriff.model import InstrumentKind, Song
from guitarriff.transcription import service

router = APIRouter(prefix="/audio-files/{file_id}", tags=["transcription"])


class TranscribeRequest(BaseModel):
    instrument: InstrumentKind
    source: str = Field(
        default="mixture",
        description="'mixture' ou le nom d'une piste séparée déjà calculée (ex. 'bass', 'guitar').",
    )


class TranscribeResponse(BaseModel):
    song: Song
    track_id: str
    notes: str


@router.post("/transcribe", response_model=TranscribeResponse)
def transcribe_audio(
    file_id: str,
    body: TranscribeRequest,
    settings: Settings = Depends(get_settings),  # noqa: B008
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> TranscribeResponse:
    result = service.transcribe(file_id, body.instrument, body.source, settings, storage)
    return TranscribeResponse(song=result.song, track_id=result.track_id, notes=result.notes)


@router.get("/song", response_model=Song)
def get_song(file_id: str, storage: AudioFileStorage = Depends(get_storage)) -> Song:  # noqa: B008
    storage.get(file_id)  # valide l'existence du fichier (404 sinon)
    song = storage.read_song(file_id)
    if song is None:
        raise NotFoundError(
            "Aucune transcription n'a encore été calculée pour ce fichier.",
            details={"file_id": file_id},
        )
    return song
