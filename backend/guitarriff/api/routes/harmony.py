"""Routes d'analyse harmonique (Étape 13) : accords et piste clavier.

Deux fonctionnalités distinctes :
1. obtenir des accords (`estimate-chords`, `chords-from-notes`, `PUT chords`) ;
2. générer une piste clavier à partir d'accords (`generate-keyboard`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.api.routes.audio_files import get_storage
from guitarriff.config import Settings, get_settings
from guitarriff.harmony import service
from guitarriff.model import (
    ChordEvent,
    ChordQuality,
    EstimationSource,
    InstrumentKind,
    Song,
)
from guitarriff.model.chord import validate_chords_non_overlapping

router = APIRouter(prefix="/audio-files/{file_id}", tags=["harmony"])

_ESTIMATE_NOTES = (
    "Estimation heuristique à partir du chroma audio (base de référence, pas un modèle "
    "entraîné), calibrée et mesurée uniquement sur des signaux synthétiques : sa précision "
    "sur de vrais enregistrements n'est pas connue et sera nettement inférieure. Un accord "
    "marqué ambigu (`ambiguous`) ne doit jamais être présenté comme certain : consultez ses "
    "`alternatives`. Un intervalle sans accord signifie qu'aucun accord défendable n'a été "
    "trouvé (silence, note seule, bruit)."
)
_FROM_NOTES_NOTES = (
    "Accords déduits des notes transcrites : la basse et le renversement sont exacts "
    "(sous réserve des erreurs de la transcription elle-même). Les accords marqués ambigus "
    "restent à vérifier."
)
_MANUAL_NOTES = (
    "Accords fournis par l'utilisateur : certains par définition (aucune confiance associée)."
)
_KEYBOARD_NOTES = (
    "Piste clavier simple, générée à partir des accords : chaque accord est tenu pendant "
    "toute sa durée (aucun rythme interne, vélocité fixe). C'est une représentation jouable "
    "de l'harmonie estimée ou corrigée, pas une transcription de ce qui est joué dans "
    "l'enregistrement. Les notes issues d'un accord incertain portent une confiance basse."
)


class EstimateChordsRequest(BaseModel):
    source: str = Field(
        default="mixture",
        description="'mixture' ou une piste séparée déjà calculée (ex. 'other', 'guitar').",
    )


class ChordsFromNotesRequest(BaseModel):
    instrument: InstrumentKind


class ChordInput(BaseModel):
    root_pitch_class: int = Field(ge=0, le=11, description="0 = do, 1 = do#, ... 11 = si.")
    quality: ChordQuality
    bass_pitch_class: int | None = Field(default=None, ge=0, le=11)
    start_seconds: float = Field(ge=0)
    duration_seconds: float = Field(gt=0)

    def to_event(self) -> ChordEvent:
        return ChordEvent(
            root_pitch_class=self.root_pitch_class,
            quality=self.quality,
            bass_pitch_class=self.bass_pitch_class,
            start_seconds=self.start_seconds,
            duration_seconds=self.duration_seconds,
            source=EstimationSource.MANUAL,
        )


class SetChordsRequest(BaseModel):
    chords: tuple[ChordInput, ...]

    @model_validator(mode="after")
    def _chords_sorted_and_not_overlapping(self) -> SetChordsRequest:
        validate_chords_non_overlapping(self.events())
        return self

    def events(self) -> tuple[ChordEvent, ...]:
        return tuple(c.to_event() for c in self.chords)


class GenerateKeyboardRequest(BaseModel):
    include_ambiguous: bool = Field(
        default=True,
        description="Si faux, les accords ambigus sont ignorés (comptés dans la réponse).",
    )


class ChordsResponse(BaseModel):
    song: Song
    chords: list[ChordEvent]
    ambiguous_count: int
    notes: str


class GenerateKeyboardResponse(BaseModel):
    song: Song
    chord_count: int
    skipped_ambiguous_count: int
    low_confidence_chord_count: int
    right_hand_note_count: int
    left_hand_note_count: int
    notes: str


def _chords_response(outcome: service.ChordsOutcome, notes: str) -> ChordsResponse:
    song = outcome.song.with_computed_positions()  # positions dérivées, jamais persistées
    return ChordsResponse(
        song=song, chords=list(song.chords), ambiguous_count=outcome.ambiguous_count, notes=notes
    )


@router.post("/estimate-chords", response_model=ChordsResponse)
def estimate_chords_route(
    file_id: str,
    body: EstimateChordsRequest,
    settings: Settings = Depends(get_settings),  # noqa: B008
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> ChordsResponse:
    return _chords_response(
        service.estimate_chords(file_id, body.source, settings, storage), _ESTIMATE_NOTES
    )


@router.post("/chords-from-notes", response_model=ChordsResponse)
def chords_from_notes_route(
    file_id: str,
    body: ChordsFromNotesRequest,
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> ChordsResponse:
    return _chords_response(
        service.chords_from_notes(file_id, body.instrument, storage), _FROM_NOTES_NOTES
    )


@router.put("/chords", response_model=ChordsResponse)
def set_chords_route(
    file_id: str,
    body: SetChordsRequest,
    settings: Settings = Depends(get_settings),  # noqa: B008
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> ChordsResponse:
    return _chords_response(
        service.set_manual_chords(file_id, body.events(), settings, storage), _MANUAL_NOTES
    )


@router.post("/generate-keyboard", response_model=GenerateKeyboardResponse)
def generate_keyboard_route(
    file_id: str,
    body: GenerateKeyboardRequest,
    storage: AudioFileStorage = Depends(get_storage),  # noqa: B008
) -> GenerateKeyboardResponse:
    outcome = service.generate_keyboard(file_id, body.include_ambiguous, storage)
    return GenerateKeyboardResponse(
        song=outcome.song.with_computed_positions(),
        chord_count=outcome.chord_count,
        skipped_ambiguous_count=outcome.skipped_ambiguous_count,
        low_confidence_chord_count=outcome.low_confidence_chord_count,
        right_hand_note_count=outcome.right_hand_note_count,
        left_hand_note_count=outcome.left_hand_note_count,
        notes=_KEYBOARD_NOTES,
    )
