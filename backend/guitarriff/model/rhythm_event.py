"""RhythmEvent — événements rythmiques, en particulier de batterie.

Distinct de `NoteEvent` : un coup de batterie n'a pas de hauteur musicale au
sens harmonique (même si la General MIDI Percussion Map leur assigne des
numéros de note par convention). `RhythmEvent` utilise un vocabulaire
contrôlé lisible (`DrumPiece`) plutôt qu'un entier MIDI brut.

`duration_seconds` peut valoir 0 (contrairement à `NoteEvent`) : un coup de
batterie est un déclenchement instantané dont la résonance naturelle de
l'instrument n'a pas besoin d'être modélisée explicitement.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from guitarriff.model.enums import DrumPiece
from guitarriff.model.position import MusicalPosition


class RhythmEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    drum_piece: DrumPiece
    start_seconds: float = Field(ge=0)
    duration_seconds: float = Field(ge=0)
    velocity: int = Field(ge=0, le=127)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    position: MusicalPosition | None = None

    @property
    def end_seconds(self) -> float:
        return self.start_seconds + self.duration_seconds

    def with_position(self, position: MusicalPosition) -> RhythmEvent:
        return self.model_copy(update={"position": position})
