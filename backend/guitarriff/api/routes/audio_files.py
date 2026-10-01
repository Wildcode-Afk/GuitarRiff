"""Routes de gestion des fichiers audio importés localement.

Ne déclenche aucune transcription ni traitement audio : cette route se limite
à valider, stocker et référencer le fichier (Étape 4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel

from guitarriff.acquisition.storage import AudioFileStorage, StoredAudioFile
from guitarriff.config import Settings, get_settings
from guitarriff.errors import FileTooLargeError

router = APIRouter(prefix="/audio-files", tags=["audio-files"])


class AudioFileMetadata(BaseModel):
    file_id: str
    original_filename: str
    format: str
    content_type: str
    size_bytes: int
    uploaded_at: str
    status: str
    source: str = "upload"
    source_url: str | None = None
    title: str | None = None

    @classmethod
    def from_record(cls, record: StoredAudioFile) -> AudioFileMetadata:
        return cls(
            file_id=record.file_id,
            original_filename=record.original_filename,
            format=record.format,
            content_type=record.content_type,
            size_bytes=record.size_bytes,
            uploaded_at=record.uploaded_at,
            status=record.status,
            source=record.source,
            source_url=record.source_url,
            title=record.title,
        )


def get_storage(settings: Settings = Depends(get_settings)) -> AudioFileStorage:  # noqa: B008
    return AudioFileStorage(settings)


@router.post("", status_code=201, response_model=AudioFileMetadata)
async def upload_audio_file(
    file: UploadFile,
    settings: Settings = Depends(get_settings),  # noqa: B008
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> AudioFileMetadata:
    content = await _read_within_limit(file, settings.max_upload_size_bytes)
    record = storage.save(
        filename=file.filename or "",
        declared_content_type=file.content_type or "",
        content=content,
    )
    return AudioFileMetadata.from_record(record)


@router.get("/{file_id}", response_model=AudioFileMetadata)
def get_audio_file(
    file_id: str, storage: AudioFileStorage = Depends(get_storage)  # noqa: B008
) -> AudioFileMetadata:
    record = storage.get(file_id)
    return AudioFileMetadata.from_record(record)


@router.delete("/{file_id}", status_code=204)
def delete_audio_file(file_id: str, storage: AudioFileStorage = Depends(get_storage)) -> None:  # noqa: B008
    storage.delete(file_id)


async def _read_within_limit(file: UploadFile, max_size: int) -> bytes:
    """Lit le contenu envoyé par morceaux, en s'arrêtant dès que la limite de
    taille est dépassée — évite de charger un fichier arbitrairement gros en
    mémoire avant de le rejeter."""

    chunk_size = 1024 * 1024  # 1 Mo
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise FileTooLargeError(
                "Le fichier dépasse la taille maximale autorisée.",
                details={"max_size_bytes": max_size},
            )
        chunks.append(chunk)
    return b"".join(chunks)
