"""Signaux synthétiques à accords connus, pour tester l'analyse harmonique
sans dépendre d'un enregistrement réel. Chaque note est une somme d'harmoniques
d'amplitude 1/k (k = 1..4) avec une courte attaque et un court relâchement.

**Ces signaux décrivent le meilleur cas** (timbre propre, durée de 2 s, aucun
instrument concurrent) : les résultats qu'ils produisent ne disent rien de la
précision sur de vrais enregistrements."""

from __future__ import annotations

import numpy as np

SR = 22050


def tone(midi: int, seconds: float, harmonics: int = 4, amp: float = 1.0) -> np.ndarray:
    f0 = 440.0 * 2 ** ((midi - 69) / 12)
    t = np.arange(int(seconds * SR)) / SR
    y = np.zeros_like(t)
    for k in range(1, harmonics + 1):
        if f0 * k < SR / 2:
            y += (1.0 / k) * np.sin(2 * np.pi * f0 * k * t)
    envelope = np.minimum(1, t / 0.02) * np.minimum(1, (seconds - t) / 0.05)
    return amp * y * envelope


def chord(midis: list[int], seconds: float) -> np.ndarray:
    return sum(tone(m, seconds, amp=1.0 / len(midis)) for m in midis)  # type: ignore[return-value]


def sequence(parts: list[tuple[list[int], float]]) -> np.ndarray:
    """Enchaîne des (notes MIDI, durée). Une liste de notes vide = silence."""

    pieces = [chord(m, s) if m else np.zeros(int(s * SR)) for m, s in parts]
    return np.concatenate(pieces).astype("float32")


def voicing(root_pitch_class: int, intervals: tuple[int, ...], base: int = 60) -> list[int]:
    """Position fondamentale en registre moyen, à partir de do4 (60)."""

    start = base + ((root_pitch_class - base) % 12)
    return [start + i for i in intervals]
