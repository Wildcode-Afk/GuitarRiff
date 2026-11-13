"""Résolution de la source audio d'une analyse : le mélange normalisé complet
(`"mixture"`, Étape 6) ou une piste déjà séparée (Étape 7).

Partagé par la transcription (Étape 9) et l'estimation d'accords (Étape 13) :
une seule définition de « où se trouve l'audio à analyser », et jamais un chemin
construit à partir d'une chaîne utilisateur (le nom de piste est cherché dans des
répertoires internes déjà validés).
"""

from __future__ import annotations

from pathlib import Path

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.errors import AudioNotNormalizedError, SeparatedStemNotFoundError

# Ordre de recherche des modes de séparation en cache pour une piste donnée
# (voir separation/models.py) — htdemucs_6s d'abord, seul mode à isoler une
# piste "guitar" dédiée.
SEPARATION_MODES_SEARCH_ORDER = ("htdemucs_6s", "htdemucs")


def resolve_source_path(file_id: str, source: str, storage: AudioFileStorage) -> Path:
    if source == "mixture":
        record = storage.get(file_id)
        normalized_path = storage.normalized_path(file_id)
        if not record.normalized or not normalized_path.is_file():
            raise AudioNotNormalizedError(
                "Ce fichier doit d'abord être normalisé (POST .../normalize) "
                "avant une analyse sur le mélange complet.",
                details={"file_id": file_id},
            )
        return normalized_path

    for mode in SEPARATION_MODES_SEARCH_ORDER:
        candidate = storage.separated_dir(file_id, mode) / f"{source}.wav"
        if candidate.is_file():
            return candidate

    raise SeparatedStemNotFoundError(
        "Cette piste séparée n'a pas encore été calculée (POST .../separate d'abord).",
        details={"file_id": file_id, "requested_stem": source},
    )
