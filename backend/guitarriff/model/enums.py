"""Vocabulaires contrôlés du modèle musical commun.

`InstrumentKind` est délibérément aligné sur les noms de pistes produites par
la séparation (Étape 7, `separation/models.py` : `drums`, `bass`, `other`,
`vocals`, `guitar`, `piano`) — une piste séparée `"bass"` devient
naturellement une `Track` d'instrument `InstrumentKind.BASS`, sans table de
correspondance séparée à maintenir. `OTHER` couvre à la fois la piste
`"other"` de Demucs et le mode `"mixture"` (pas de séparation, Étape 7).
"""

from __future__ import annotations

from enum import StrEnum


class InstrumentKind(StrEnum):
    GUITAR = "guitar"
    BASS = "bass"
    DRUMS = "drums"
    PIANO = "piano"
    VOCALS = "vocals"
    OTHER = "other"


class Clef(StrEnum):
    TREBLE = "treble"
    BASS = "bass"
    PERCUSSION = "percussion"
    TAB = "tab"


class DrumPiece(StrEnum):
    """Vocabulaire contrôlé pour les événements de batterie (`RhythmEvent`).

    Volontairement des noms lisibles plutôt que des numéros bruts de la
    General MIDI Percussion Map — la correspondance vers cette dernière (pour
    un futur export MIDI) est une responsabilité d'une étape ultérieure, pas
    de ce modèle.
    """

    KICK = "kick"
    SNARE = "snare"
    HIHAT_CLOSED = "hihat_closed"
    HIHAT_OPEN = "hihat_open"
    CRASH = "crash"
    RIDE = "ride"
    TOM_LOW = "tom_low"
    TOM_MID = "tom_mid"
    TOM_HIGH = "tom_high"
    CLAP = "clap"
    OTHER_PERCUSSION = "other_percussion"
