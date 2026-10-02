"""Modes de séparation disponibles.

**Aucun de ces modes ne produit des instruments parfaitement isolés.** La
séparation de sources est une estimation statistique : artefacts, bruit de
fond et fuites entre pistes sont systématiques, à des degrés divers. Le champ
`notes` de chaque mode documente les limites connues — il doit être répercuté
dans toute réponse API exposant ces pistes (voir docs/API.md).
"""

from __future__ import annotations

from dataclasses import dataclass

from guitarriff.errors import InvalidSeparationModeError


@dataclass(frozen=True)
class SeparationModelInfo:
    key: str
    label: str
    stems: tuple[str, ...]
    experimental: bool
    notes: str


NONE = SeparationModelInfo(
    key="none",
    label="Aucune séparation",
    stems=("mixture",),
    experimental=False,
    notes="L'audio normalisé est utilisé tel quel, sans tentative de séparation.",
)

HTDEMUCS = SeparationModelInfo(
    key="htdemucs",
    label="Hybrid Transformer Demucs (4 pistes)",
    stems=("drums", "bass", "other", "vocals"),
    experimental=False,
    notes=(
        "La piste 'bass' est directement exploitable pour la transcription "
        "basse. La piste 'other' contient la guitare mélangée avec claviers, "
        "synthés et tout instrument non classé ailleurs — ce n'est PAS une "
        "guitare isolée. Toutes les pistes contiennent des artefacts et des "
        "fuites résiduelles d'autres instruments, à des degrés variables."
    ),
)

HTDEMUCS_6S = SeparationModelInfo(
    key="htdemucs_6s",
    label="Hybrid Transformer Demucs (6 pistes, expérimental)",
    stems=("drums", "bass", "other", "vocals", "guitar", "piano"),
    experimental=True,
    notes=(
        "Modèle qualifié d'expérimental par ses propres auteurs en amont : "
        "la piste guitare est jugée de qualité correcte mais non parfaite, "
        "la piste piano présente beaucoup de bruit de fond et d'artefacts "
        "d'après la documentation de Demucs elle-même. À ne jamais présenter "
        "comme une isolation propre, même pour la piste guitare."
    ),
)

AVAILABLE_MODES: dict[str, SeparationModelInfo] = {m.key: m for m in (NONE, HTDEMUCS, HTDEMUCS_6S)}


def get_mode(key: str) -> SeparationModelInfo:
    try:
        return AVAILABLE_MODES[key]
    except KeyError as exc:
        raise InvalidSeparationModeError(
            "Mode de séparation inconnu.",
            details={"mode": key, "available_modes": list(AVAILABLE_MODES)},
        ) from exc
