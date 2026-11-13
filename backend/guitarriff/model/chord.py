"""Représentation normalisée des accords (Étape 13).

## Conventions

- `root_pitch_class` / `bass_pitch_class` : classe de hauteur 0-11 (0 = do,
  1 = do#, ... 11 = si). Pas d'octave : un accord estimé n'a pas de hauteur
  absolue, seulement des classes de hauteur.
- Noms de notes : **dièses uniquement** (A# et non Bb). Une orthographe
  dépendant de la tonalité (Bb dans un morceau en fa, A# en si) demanderait une
  estimation de tonalité, hors périmètre ici.
- `start_seconds` / `duration_seconds` : mêmes unités et même axe temporel que
  `NoteEvent` ; `position` (mesure/temps) est une donnée **dérivée**, calculée
  par `Song.with_computed_positions` à partir de la carte de tempo/métrique.
- **Absence d'accord** : un intervalle de temps sans `ChordEvent` (silence, ou
  contenu non harmonique) — pas d'objet « accord vide », comme pour les
  silences de `NoteEvent`.

## Incertitude

Un accord estimé n'est jamais présenté comme certain quand il est ambigu :
`ambiguous` est vrai quand plusieurs accords expliquent presque aussi bien les
données, et `alternatives` liste ces autres lectures plausibles. `confidence`
est une mesure heuristique (voir `harmony/templates.py`), pas une probabilité
calibrée. Une valeur `MANUAL` (fournie ou corrigée par l'utilisateur) n'a ni
confiance, ni ambiguïté, ni alternatives — validé par le modèle lui-même.

## Renversement

`inversion` n'est défini que si la basse (`bass_pitch_class`) est connue **et**
est une note de l'accord : 0 = état fondamental, 1 = premier renversement
(basse = tierce, ou seconde/quarte pour sus2/sus4, ou quinte d'un accord de
quinte), 2 = deuxième renversement, 3 = troisième. Une basse hors de l'accord
(ex. do/ré) donne `None` : c'est une « slash chord » non renversée.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from guitarriff.model.enums import ChordQuality, EstimationSource
from guitarriff.model.position import MusicalPosition

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# Notes de l'accord, en demi-tons au-dessus de la fondamentale, dans l'ordre
# des degrés (l'indice d'une note dans ce tuple est son numéro de renversement).
CHORD_INTERVALS: dict[ChordQuality, tuple[int, ...]] = {
    ChordQuality.MAJOR: (0, 4, 7),
    ChordQuality.MINOR: (0, 3, 7),
    ChordQuality.DIMINISHED: (0, 3, 6),
    ChordQuality.AUGMENTED: (0, 4, 8),
    ChordQuality.SUS2: (0, 2, 7),
    ChordQuality.SUS4: (0, 5, 7),
    ChordQuality.DOMINANT_7: (0, 4, 7, 10),
    ChordQuality.MAJOR_7: (0, 4, 7, 11),
    ChordQuality.MINOR_7: (0, 3, 7, 10),
    ChordQuality.POWER: (0, 7),
}

_SYMBOL_SUFFIX: dict[ChordQuality, str] = {
    ChordQuality.MAJOR: "",
    ChordQuality.MINOR: "m",
    ChordQuality.DIMINISHED: "dim",
    ChordQuality.AUGMENTED: "aug",
    ChordQuality.SUS2: "sus2",
    ChordQuality.SUS4: "sus4",
    ChordQuality.DOMINANT_7: "7",
    ChordQuality.MAJOR_7: "maj7",
    ChordQuality.MINOR_7: "m7",
    ChordQuality.POWER: "5",
}

# Tolérance d'arrondi pour le test de non-chevauchement (des segments adjacents
# calculés en virgule flottante peuvent différer de ~1e-16).
_OVERLAP_TOLERANCE_SECONDS = 1e-6


def chord_pitch_classes(root_pitch_class: int, quality: ChordQuality) -> tuple[int, ...]:
    """Classes de hauteur de l'accord, dans l'ordre des degrés."""

    return tuple((root_pitch_class + interval) % 12 for interval in CHORD_INTERVALS[quality])


def chord_symbol(
    root_pitch_class: int, quality: ChordQuality, bass_pitch_class: int | None = None
) -> str:
    symbol = NOTE_NAMES[root_pitch_class] + _SYMBOL_SUFFIX[quality]
    if bass_pitch_class is not None and bass_pitch_class != root_pitch_class:
        symbol += "/" + NOTE_NAMES[bass_pitch_class]
    return symbol


class ChordCandidate(BaseModel):
    """Une lecture possible d'un accord, avec son score d'adéquation aux données."""

    model_config = ConfigDict(frozen=True)

    root_pitch_class: int = Field(ge=0, le=11)
    quality: ChordQuality
    score: float = Field(ge=0.0, le=1.0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def symbol(self) -> str:
        return chord_symbol(self.root_pitch_class, self.quality)


class ChordEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    root_pitch_class: int = Field(ge=0, le=11)
    quality: ChordQuality
    bass_pitch_class: int | None = Field(default=None, ge=0, le=11)
    start_seconds: float = Field(ge=0)
    duration_seconds: float = Field(gt=0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source: EstimationSource = EstimationSource.DETECTED
    ambiguous: bool = False
    alternatives: tuple[ChordCandidate, ...] = ()
    position: MusicalPosition | None = Field(
        default=None, description="Calculée par Song.with_computed_positions ; None sinon."
    )

    @model_validator(mode="after")
    def _manual_chord_is_certain(self) -> ChordEvent:
        if self.source == EstimationSource.MANUAL and (
            self.confidence is not None or self.ambiguous or self.alternatives
        ):
            raise ValueError(
                "Un accord 'manual' (fourni par l'utilisateur) n'a ni confiance, "
                "ni ambiguïté, ni alternatives."
            )
        return self

    @property
    def end_seconds(self) -> float:
        return self.start_seconds + self.duration_seconds

    # Champs calculés : présents dans le JSON pour les clients, jamais stockés
    # (ils se recalculent depuis la fondamentale, la qualité et la basse).
    @computed_field  # type: ignore[prop-decorator]
    @property
    def pitch_classes(self) -> tuple[int, ...]:
        return chord_pitch_classes(self.root_pitch_class, self.quality)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def symbol(self) -> str:
        return chord_symbol(self.root_pitch_class, self.quality, self.bass_pitch_class)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def inversion(self) -> int | None:
        if self.bass_pitch_class is None:
            return None
        tones = self.pitch_classes
        if self.bass_pitch_class not in tones:
            return None
        return tones.index(self.bass_pitch_class)

    def with_position(self, position: MusicalPosition) -> ChordEvent:
        return self.model_copy(update={"position": position})


def validate_chords_non_overlapping(chords: tuple[ChordEvent, ...]) -> tuple[ChordEvent, ...]:
    """Les accords doivent être triés par début et ne pas se chevaucher (les
    trous sont permis : ils représentent l'absence d'accord)."""

    for previous, current in zip(chords, chords[1:], strict=False):
        if current.start_seconds < previous.start_seconds:
            raise ValueError("chords doit être trié par start_seconds croissant.")
        if current.start_seconds < previous.end_seconds - _OVERLAP_TOLERANCE_SECONDS:
            raise ValueError(
                "Les accords ne doivent pas se chevaucher "
                f"({previous.symbol} finit à {previous.end_seconds:.3f}s, "
                f"{current.symbol} commence à {current.start_seconds:.3f}s)."
            )
    return chords
