"""Modèle musical commun — le contrat unique entre toute méthode de
transcription et le reste du pipeline (voir docs/ARCHITECTURE.md, principe 4).

Le frontend ne doit jamais dépendre directement du format de sortie d'un
modèle de transcription : `Song` (sérialisé via `model_dump`/`model_dump_json`)
est le seul contrat exposé.

- `enums.py` : vocabulaires contrôlés (`InstrumentKind`, `Clef`, `DrumPiece`).
- `tempo.py` : `TempoChange`, `TimeSignatureChange` — conventions temporelles.
- `position.py` : `MusicalPosition` + `compute_position` (fonction pure).
- `note_event.py` : `NoteEvent`, `InstrumentSpecificInfo`.
- `rhythm_event.py` : `RhythmEvent` (batterie et événements non-harmoniques).
- `track.py` : `Track`, `TrackDisplaySettings`.
- `song.py` : `Song`, `AudioMetadata` — racine du modèle.
"""

from __future__ import annotations

from guitarriff.model.enums import Clef, DrumPiece, InstrumentKind
from guitarriff.model.note_event import InstrumentSpecificInfo, NoteEvent
from guitarriff.model.position import MusicalPosition, compute_position
from guitarriff.model.rhythm_event import RhythmEvent
from guitarriff.model.song import AudioMetadata, Song
from guitarriff.model.tempo import TempoChange, TimeSignatureChange
from guitarriff.model.track import Track, TrackDisplaySettings

__all__ = [
    "AudioMetadata",
    "Clef",
    "DrumPiece",
    "InstrumentKind",
    "InstrumentSpecificInfo",
    "MusicalPosition",
    "NoteEvent",
    "RhythmEvent",
    "Song",
    "TempoChange",
    "TimeSignatureChange",
    "Track",
    "TrackDisplaySettings",
    "compute_position",
]
