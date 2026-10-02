"""Suivi de la progression d'une séparation en cours.

Stockage en mémoire (process unique) — pas de file de jobs partagée ni de
persistance entre redémarrages. Limitation assumée, documentée dans
docs/PROJECT_STATUS.md : la progression d'une séparation en cours est perdue
si le serveur redémarre, mais le résultat déjà mis en cache sur disque (voir
`acquisition/storage.py`) survit, lui, à un redémarrage — seul l'état d'un
traitement *en cours* est volatile.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum
from time import time


class Stage(StrEnum):
    QUEUED = "queued"
    LOADING_MODEL = "loading_model"
    SEPARATING = "separating"
    WRITING_STEMS = "writing_stems"
    DONE = "done"
    ERROR = "error"


# Progression approximative par étape — volontairement grossière (quelques
# paliers), pas un pourcentage continu fin : nous n'avons pas pu vérifier de
# façon fiable, dans cet environnement, une éventuelle API de callback
# interne à Demucs permettant un suivi plus précis (voir docs/MODELS.md).
_STAGE_PROGRESS: dict[Stage, int] = {
    Stage.QUEUED: 0,
    Stage.LOADING_MODEL: 10,
    Stage.SEPARATING: 50,
    Stage.WRITING_STEMS: 90,
    Stage.DONE: 100,
    Stage.ERROR: 100,
}


@dataclass
class ProgressEntry:
    stage: Stage
    progress_percent: int
    started_at: float
    error_message: str | None = None
    stems: list[str] | None = None
    updated_at: float = field(default_factory=time)


class ProgressStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, str], ProgressEntry] = {}

    def start(self, file_id: str, mode: str) -> None:
        with self._lock:
            self._entries[(file_id, mode)] = ProgressEntry(
                stage=Stage.QUEUED,
                progress_percent=_STAGE_PROGRESS[Stage.QUEUED],
                started_at=time(),
            )

    def set_stage(self, file_id: str, mode: str, stage: Stage) -> None:
        with self._lock:
            existing = self._entries.get((file_id, mode))
            started_at = existing.started_at if existing else time()
            self._entries[(file_id, mode)] = ProgressEntry(
                stage=stage, progress_percent=_STAGE_PROGRESS[stage], started_at=started_at
            )

    def set_done(self, file_id: str, mode: str, stems: list[str]) -> None:
        with self._lock:
            existing = self._entries.get((file_id, mode))
            started_at = existing.started_at if existing else time()
            self._entries[(file_id, mode)] = ProgressEntry(
                stage=Stage.DONE,
                progress_percent=_STAGE_PROGRESS[Stage.DONE],
                started_at=started_at,
                stems=stems,
            )

    def set_error(self, file_id: str, mode: str, message: str) -> None:
        with self._lock:
            existing = self._entries.get((file_id, mode))
            started_at = existing.started_at if existing else time()
            self._entries[(file_id, mode)] = ProgressEntry(
                stage=Stage.ERROR,
                progress_percent=_STAGE_PROGRESS[Stage.ERROR],
                started_at=started_at,
                error_message=message,
            )

    def get(self, file_id: str, mode: str) -> ProgressEntry | None:
        with self._lock:
            return self._entries.get((file_id, mode))

    def is_running(self, file_id: str, mode: str) -> bool:
        entry = self.get(file_id, mode)
        return entry is not None and entry.stage not in (Stage.DONE, Stage.ERROR)


# Instance unique du processus — cohérent avec le reste de l'application
# (pas encore de déploiement multi-worker, voir docs/PROJECT_STATUS.md).
progress_store = ProgressStore()
