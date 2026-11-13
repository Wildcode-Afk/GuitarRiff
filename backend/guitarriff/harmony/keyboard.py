"""Génération d'une piste clavier **simple** à partir d'accords (détectés ou
corrigés par l'utilisateur).

## Ce que c'est — et ce que ce n'est pas

C'est une représentation **jouable de l'harmonie**, pas une transcription de ce
que le claviériste (ou le guitariste) joue réellement dans l'enregistrement :
chaque accord est tenu pendant toute sa durée, sans rythme interne, sans
arpège ni ornement. Les notes héritent de la **confiance** de leur accord
(`NoteEvent.confidence`) : un accord ambigu produit des notes à confiance basse.
La vélocité est fixe (`NOTE_VELOCITY`) — elle ne vient pas de l'audio.

## Deux mains, deux pistes

- **Main gauche** (`piano-lh`, clé de fa) : une seule note, la basse — la basse
  connue de l'accord (renversement) si elle existe, sinon la fondamentale —,
  choisie dans `[LH_LOW, LH_HIGH]` au plus près de la note précédente.
- **Main droite** (`piano-rh`, clé de sol) : les notes de l'accord en position
  rapprochée, dans `[RH_LOW, RH_HIGH]`, parmi tous les renversements et octaves
  possibles ; on retient celui qui **déplace le moins** la main par rapport à
  l'accord précédent (conduite des voix), avec un léger biais vers le centre
  du clavier.

## Jouabilité (invariants garantis par construction, testés)

- Main droite : au plus 4 notes (le vocabulaire d'accords n'en a pas plus) et
  un écart maximal de `MAX_HAND_SPAN` demi-tons (une octave).
- Main gauche : une note à la fois.
- Aucun chevauchement : les accords ne se chevauchent pas (validé par `Song`),
  donc les notes de deux accords successifs non plus.

Le biais vers le centre est un jugement heuristique, comme les poids du mapping
manche ; il n'a pas été validé auprès de claviéristes.
"""

from __future__ import annotations

from dataclasses import dataclass

from guitarriff.model import (
    ChordEvent,
    Clef,
    InstrumentKind,
    NoteEvent,
    Track,
    TrackDisplaySettings,
)

RIGHT_HAND_TRACK_ID = "piano-rh"
LEFT_HAND_TRACK_ID = "piano-lh"

RH_LOW, RH_HIGH = 55, 84  # sol3 à do6
LH_LOW, LH_HIGH = 36, 55  # do2 à sol3
RH_CENTER = 67  # sol4
LH_CENTER = 45  # la2
MAX_HAND_SPAN = 12
NOTE_VELOCITY = 80
_CENTER_WEIGHT = 0.1


@dataclass(frozen=True)
class KeyboardResult:
    right_hand: Track
    left_hand: Track
    chord_count: int
    skipped_ambiguous_count: int


def _right_hand_candidates(tones: tuple[int, ...]) -> list[tuple[int, ...]]:
    """Toutes les voicings rapprochées (renversements × octaves) jouables par
    une main dans [RH_LOW, RH_HIGH]."""

    candidates: list[tuple[int, ...]] = []
    for rotation in range(len(tones)):
        order = tones[rotation:] + tones[:rotation]
        for start in range(RH_LOW, RH_HIGH + 1):
            if start % 12 != order[0]:
                continue
            pitches = [start]
            for pitch_class in order[1:]:
                pitch = pitches[-1] + 1
                while pitch % 12 != pitch_class:
                    pitch += 1
                pitches.append(pitch)
            if pitches[-1] <= RH_HIGH and pitches[-1] - pitches[0] <= MAX_HAND_SPAN:
                candidates.append(tuple(pitches))
    return candidates


def _voice_leading_distance(new: tuple[int, ...], previous: tuple[int, ...]) -> float:
    """Distance symétrique : chaque note de l'une à la plus proche de l'autre."""

    forward = sum(min(abs(n - p) for p in previous) for n in new)
    backward = sum(min(abs(p - n) for n in new) for p in previous)
    return float(forward + backward)


def _choose_right_hand(tones: tuple[int, ...], previous: tuple[int, ...] | None) -> tuple[int, ...]:
    def cost(pitches: tuple[int, ...]) -> tuple[float, tuple[int, ...]]:
        center_penalty = _CENTER_WEIGHT * abs(sum(pitches) / len(pitches) - RH_CENTER)
        movement = _voice_leading_distance(pitches, previous) if previous else 0.0
        return (movement + center_penalty, pitches)  # `pitches` départage de façon déterministe

    return min(_right_hand_candidates(tones), key=cost)


def _choose_left_hand(pitch_class: int, previous: int | None) -> int:
    reference = previous if previous is not None else LH_CENTER
    candidates = [p for p in range(LH_LOW, LH_HIGH + 1) if p % 12 == pitch_class]
    return min(candidates, key=lambda p: (abs(p - reference), p))


def generate_keyboard(
    chords: tuple[ChordEvent, ...], *, include_ambiguous: bool = True
) -> KeyboardResult:
    right_notes: list[NoteEvent] = []
    left_notes: list[NoteEvent] = []
    previous_right: tuple[int, ...] | None = None
    previous_left: int | None = None
    skipped = 0
    used = 0

    for chord in chords:
        if chord.ambiguous and not include_ambiguous:
            skipped += 1
            continue
        used += 1

        right = _choose_right_hand(chord.pitch_classes, previous_right)
        bass_pitch_class = (
            chord.bass_pitch_class if chord.bass_pitch_class is not None else chord.root_pitch_class
        )
        left = _choose_left_hand(bass_pitch_class, previous_left)

        for pitch in right:
            right_notes.append(_note(pitch, chord))
        left_notes.append(_note(left, chord))
        previous_right, previous_left = right, left

    return KeyboardResult(
        right_hand=Track(
            id=RIGHT_HAND_TRACK_ID,
            instrument=InstrumentKind.PIANO,
            name="Piano — main droite",
            notes=tuple(right_notes),
            display=TrackDisplaySettings(clef=Clef.TREBLE, display_order=0),
        ),
        left_hand=Track(
            id=LEFT_HAND_TRACK_ID,
            instrument=InstrumentKind.PIANO,
            name="Piano — main gauche",
            notes=tuple(left_notes),
            display=TrackDisplaySettings(clef=Clef.BASS, display_order=1, color="#ef4444"),
        ),
        chord_count=used,
        skipped_ambiguous_count=skipped,
    )


def _note(pitch: int, chord: ChordEvent) -> NoteEvent:
    return NoteEvent(
        midi_pitch=pitch,
        start_seconds=chord.start_seconds,
        duration_seconds=chord.duration_seconds,
        velocity=NOTE_VELOCITY,
        confidence=chord.confidence,
    )
