"""Route d'import audio depuis YouTube (Étape 5).

Ne fait rien d'autre que valider l'URL, récupérer les métadonnées, vérifier
les limites (durée, taille) et stocker le résultat via le même pipeline de
sécurité que l'import de fichier local. Aucune transcription n'est
déclenchée ici.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.acquisition.youtube import download_audio
from guitarriff.api.routes.audio_files import AudioFileMetadata, get_storage
from guitarriff.config import Settings, get_settings

router = APIRouter(prefix="/youtube-imports", tags=["youtube-imports"])


class YoutubeImportRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)


@router.post("", status_code=201, response_model=AudioFileMetadata)
def import_from_youtube(
    body: YoutubeImportRequest,
    settings: Settings = Depends(get_settings),  # noqa: B008
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> AudioFileMetadata:
    record = download_audio(body.url, settings, storage)
    return AudioFileMetadata.from_record(record)
