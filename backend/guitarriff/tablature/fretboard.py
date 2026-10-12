"""Configuration du manche et génération des positions candidates (corde,
case) pour une hauteur MIDI donnée.

## Convention capodastre

`fret` (dans `Position` comme dans `InstrumentSpecificInfo`, voir
`model/note_event.py`) est exprimé **relativement au capodastre** — case 0 =
corde à vide *avec* le capodastre en place, conformément à la façon dont un
guitariste lit une tablature quand un capodastre est utilisé. `capo_fret`
décale la hauteur de chaque corde à vide vers le haut :

    hauteur produite = tuning[corde] + capo_fret + fret

`max_fret` est la case maximale **absolue** du manche (ex. 24 cases) ; la
case relative au capodastre jouable va donc de `0` à `max_fret - capo_fret`.
"""

from __future__ import annotations

from dataclasses import dataclass

# Accordages par défaut — valeurs MIDI vérifiées (E2=40, cohérent avec la
# convention "60 = do central" déjà établie en Étape 8).
STANDARD_GUITAR_TUNING: tuple[int, ...] = (40, 45, 50, 55, 59, 64)  # E2 A2 D3 G3 B3 E4
STANDARD_BASS_TUNING: tuple[int, ...] = (28, 33, 38, 43)  # E1 A1 D2 G2
# Basses à plus de cordes : corde de si grave (B0 = 23), puis do aigu (C3 = 48).
STANDARD_BASS_5_TUNING: tuple[int, ...] = (23, 28, 33, 38, 43)  # B0 E1 A1 D2 G2
STANDARD_BASS_6_TUNING: tuple[int, ...] = (23, 28, 33, 38, 43, 48)  # B0 E1 A1 D2 G2 C3

DEFAULT_MAX_FRET = 24


@dataclass(frozen=True)
class FretboardConfig:
    tuning: tuple[int, ...]
    capo_fret: int = 0
    max_fret: int = DEFAULT_MAX_FRET

    def __post_init__(self) -> None:
        if len(self.tuning) == 0:
            raise ValueError("tuning ne peut pas être vide.")
        for midi_note in self.tuning:
            if not (0 <= midi_note <= 127):
                raise ValueError(
                    f"tuning: hauteur MIDI invalide (0-127 attendu), reçu {midi_note}."
                )
        if self.capo_fret < 0:
            raise ValueError("capo_fret doit être positif ou nul.")
        if self.max_fret < self.capo_fret:
            raise ValueError("max_fret doit être supérieur ou égal à capo_fret.")

    @property
    def n_strings(self) -> int:
        return len(self.tuning)

    @property
    def max_relative_fret(self) -> int:
        """Case maximale jouable, relative au capodastre."""

        return self.max_fret - self.capo_fret


@dataclass(frozen=True)
class Position:
    string_index: int  # 0 = corde la plus grave (premier élément de `tuning`)
    fret: int  # relatif au capodastre — voir docstring du module


def candidate_positions(midi_pitch: int, config: FretboardConfig) -> tuple[Position, ...]:
    """Renvoie toutes les positions (corde, case) produisant `midi_pitch`
    sur ce manche, compte tenu du capodastre et de la limite de cases.
    Tuple vide si la hauteur est hors de portée de cet accordage/instrument."""

    candidates = []
    for string_index, open_string_pitch in enumerate(config.tuning):
        relative_fret = midi_pitch - open_string_pitch - config.capo_fret
        if 0 <= relative_fret <= config.max_relative_fret:
            candidates.append(Position(string_index=string_index, fret=relative_fret))
    return tuple(candidates)
