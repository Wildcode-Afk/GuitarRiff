"""Route de mapping manche (Étape 11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.api.routes.audio_files import get_storage
from guitarriff.model import InstrumentKind, Song
from guitarriff.tablature import service
from guitarriff.tablature.fretboard import DEFAULT_MAX_FRET
from guitarriff.tablature.render import DEFAULT_MAX_WIDTH

router = APIRouter(prefix="/audio-files/{file_id}", tags=["tablature"])


class MapFretboardRequest(BaseModel):
    instrument: InstrumentKind
    tuning: tuple[int, ...] | None = Field(
        default=None,
        description="Accordage personnalisé (hauteurs MIDI, grave vers aigu). Défaut si omis.",
    )
    capo_fret: int = Field(default=0, ge=0)
    max_fret: int = Field(default=DEFAULT_MAX_FRET, ge=0)

    @field_validator("tuning")
    @classmethod
    def _validate_tuning(cls, value: tuple[int, ...] | None) -> tuple[int, ...] | None:
        if value is None:
            return None
        if len(value) == 0:
            raise ValueError("tuning ne peut pas être une séquence vide.")
        for midi_note in value:
            if not (0 <= midi_note <= 127):
                raise ValueError(
                    f"tuning: hauteur MIDI invalide (0-127 attendu), reçu {midi_note}."
                )
        return value

    @model_validator(mode="after")
    def _validate_capo_within_max_fret(self) -> MapFretboardRequest:
        if self.capo_fret > self.max_fret:
            raise ValueError("capo_fret doit être inférieur ou égal à max_fret.")
        return self


class MapFretboardResponse(BaseModel):
    song: Song
    placed_count: int
    unplaced_count: int
    unplaced_reasons: list[str]
    notes: str


class TablatureResponse(BaseModel):
    instrument: InstrumentKind
    text: str
    placed_count: int
    unplaced_count: int
    notes: str


def _mapping_disclaimer(instrument: InstrumentKind) -> str:
    musician = "bassiste" if instrument == InstrumentKind.BASS else "guitariste"
    return (
        "Positions choisies par une fonction de coût (déplacement, écart entre doigts, "
        "jouabilité) parmi plusieurs valides — ne reconstitue pas le doigté original "
        f"du {musician}, qui ne peut pas être déduit de l'audio seul."
    )


@router.post("/map-fretboard", response_model=MapFretboardResponse)
def map_fretboard_route(
    file_id: str,
    body: MapFretboardRequest,
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> MapFretboardResponse:
    outcome = service.map_fretboard(
        file_id,
        body.instrument,
        storage,
        tuning=body.tuning,
        capo_fret=body.capo_fret,
        max_fret=body.max_fret,
    )
    return MapFretboardResponse(
        song=outcome.song,
        placed_count=outcome.placed_count,
        unplaced_count=outcome.unplaced_count,
        unplaced_reasons=list(outcome.unplaced_reasons),
        notes=_mapping_disclaimer(body.instrument),
    )


@router.get("/tablature", response_model=TablatureResponse)
def get_tablature_route(
    file_id: str,
    instrument: InstrumentKind,
    max_width: int = Query(default=DEFAULT_MAX_WIDTH, ge=20, le=240),
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> TablatureResponse:
    rendering = service.render_tablature(file_id, instrument, storage, max_width=max_width)
    return TablatureResponse(
        instrument=instrument,
        text=rendering.text,
        placed_count=rendering.placed_count,
        unplaced_count=rendering.unplaced_count,
        notes=_mapping_disclaimer(instrument)
        + " Le rendu ne représente pas les durées (voir docs/API.md).",
    )
