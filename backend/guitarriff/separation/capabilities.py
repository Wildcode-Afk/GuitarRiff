"""Détection des capacités du système pour la séparation d'instruments.

Aucune nouvelle dépendance ajoutée pour cela : la mémoire est lue directement
depuis `/proc/meminfo` (Linux — plateforme cible de ce projet). Sur un
système où ce fichier n'existe pas, les valeurs mémoire remontent `None`
plutôt qu'une fausse estimation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SystemCapabilities:
    cpu_count: int | None
    total_memory_mb: float | None
    available_memory_mb: float | None
    torch_installed: bool
    demucs_installed: bool
    cuda_available: bool
    recommended_device: str  # "cuda" ou "cpu"


def _read_proc_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                key, _, rest = line.partition(":")
                parts = rest.strip().split()
                if not parts:
                    continue
                try:
                    values[key.strip()] = int(parts[0])  # en kio
                except ValueError:
                    continue
    except OSError:
        pass
    return values


def get_memory_info_mb() -> tuple[float | None, float | None]:
    """Renvoie (mémoire totale, mémoire disponible) en Mo, ou (None, None)
    si `/proc/meminfo` est inaccessible (plateforme non Linux)."""

    data = _read_proc_meminfo()
    total_kib = data.get("MemTotal")
    available_kib = data.get("MemAvailable")
    total_mb = total_kib / 1024 if total_kib is not None else None
    available_mb = available_kib / 1024 if available_kib is not None else None
    return total_mb, available_mb


def torch_installed() -> bool:
    try:
        import torch  # noqa: F401
    except ImportError:
        return False
    return True


def demucs_installed() -> bool:
    try:
        import demucs  # noqa: F401
    except ImportError:
        return False
    return True


def cuda_available() -> bool:
    try:
        import torch
    except ImportError:
        return False
    try:
        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001 — détection best-effort, ne doit jamais lever
        return False


def get_system_capabilities() -> SystemCapabilities:
    total_mb, available_mb = get_memory_info_mb()
    torch_ok = torch_installed()
    demucs_ok = demucs_installed()
    cuda_ok = cuda_available() if torch_ok else False
    return SystemCapabilities(
        cpu_count=os.cpu_count(),
        total_memory_mb=total_mb,
        available_memory_mb=available_mb,
        torch_installed=torch_ok,
        demucs_installed=demucs_ok,
        cuda_available=cuda_ok,
        recommended_device="cuda" if cuda_ok else "cpu",
    )
