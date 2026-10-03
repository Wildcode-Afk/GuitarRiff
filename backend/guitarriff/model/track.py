"""Track — une piste d'instrument au sein d'un `Song`.

`tuning` n'a de sens que pour un instrument à cordes frettées (guitare,
basse) : séquence de hauteurs MIDI des cordes à vide, de la plus grave à la
plus aiguë (ex. guitare standard : `(40, 45, 50, 55, 59, 64)` pour
E2-A2-D3-G3-B3-E4). `None` pour tout autre instrument, ou tant qu'aucun
mapping manche n'a encore été calculé pour une piste de guitare/basse.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from guitarriff.model.enums import Clef, InstrumentKind
from guitarriff.model.note_event import NoteEvent
from guitarriff.model.rhythm_event import RhythmEvent

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class TrackDisplaySettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    color: str = "#3b82f6"
    clef: Clef = Clef.TREBLE
    visible: bool = True
    display_order: int = 0

    @field_validator("color")
    @classmethod
    def _validate_hex_color(cls, value: str) -> str:
        if not _HEX_COLOR_RE.match(value):
            raise ValueError(
                f"color doit être une couleur hexadécimale du type '#rrggbb', reçu {value!r}."
            )
        return value


class Track(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    instrument: InstrumentKind
    name: str = Field(min_length=1)
    tuning: tuple[int, ...] | None = None
    notes: tuple[NoteEvent, ...] = ()
    rhythm_events: tuple[RhythmEvent, ...] = ()
    display: TrackDisplaySettings = Field(default_factory=TrackDisplaySettings)

    @field_validator("tuning")
    @classmethod
    def _validate_tuning_range(cls, value: tuple[int, ...] | None) -> tuple[int, ...] | None:
        if value is None:
            return None
        if len(value) == 0:
            raise ValueError(
                "tuning ne peut pas être une séquence vide (utiliser None si non applicable)."
            )
        for midi_note in value:
            if not (0 <= midi_note <= 127):
                raise ValueError(
                    f"tuning: hauteur MIDI invalide (0-127 attendu), reçu {midi_note}."
                )
        return value
