"""Routes d'analyse rythmique et de corrections manuelles (Étape 10)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.api.routes.audio_files import get_storage
from guitarriff.config import Settings, get_settings
from guitarriff.model import Song
from guitarriff.model.tempo import VALID_DENOMINATORS
from guitarriff.rhythm import service

router = APIRouter(prefix="/audio-files/{file_id}", tags=["rhythm"])


class AnalyzeRhythmResponse(BaseModel):
    song: Song
    beat_times: list[float]
    confidence: float
    notes: str


class SetTempoRequest(BaseModel):
    bpm: float = Field(gt=0)


class SetTimeSignatureRequest(BaseModel):
    numerator: int = Field(ge=1)
    denominator: int

    @field_validator("denominator")
    @classmethod
    def _check_denominator(cls, value: int) -> int:
        if value not in VALID_DENOMINATORS:
            raise ValueError(
                f"denominator doit être une puissance de 2 parmi {sorted(VALID_DENOMINATORS)}."
            )
        return value


@router.post("/analyze-rhythm", response_model=AnalyzeRhythmResponse)
def analyze_rhythm_route(
    file_id: str,
    settings: Settings = Depends(get_settings),  # noqa: B008
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> AnalyzeRhythmResponse:
    outcome = service.analyze(file_id, settings, storage)
    return AnalyzeRhythmResponse(
        song=outcome.song,
        beat_times=list(outcome.beat_times),
        confidence=outcome.confidence,
        notes=outcome.notes,
    )


@router.post("/tempo", response_model=Song)
def set_tempo_route(
    file_id: str,
    body: SetTempoRequest,
    settings: Settings = Depends(get_settings),  # noqa: B008
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> Song:
    return service.set_manual_tempo(file_id, body.bpm, settings, storage)


@router.post("/time-signature", response_model=Song)
def set_time_signature_route(
    file_id: str,
    body: SetTimeSignatureRequest,
    settings: Settings = Depends(get_settings),  # noqa: B008
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> Song:
    return service.set_manual_time_signature(
        file_id, body.numerator, body.denominator, settings, storage
    )
