"""Tests de `separation/capabilities.py` — exécutés en conditions réelles
(ce bac à sable n'a ni torch ni demucs installés : les résultats attendus
"absent" sont donc des faits vérifiés, pas des suppositions)."""

from __future__ import annotations

from unittest.mock import mock_open, patch

from guitarriff.separation import capabilities


def test_get_memory_info_mb_reads_real_proc_meminfo() -> None:
    total_mb, available_mb = capabilities.get_memory_info_mb()

    # Ce bac à sable est Linux : /proc/meminfo doit être lisible.
    assert total_mb is not None
    assert available_mb is not None
    assert total_mb > 0
    assert 0 <= available_mb <= total_mb * 1.01  # tolérance d'arrondi


def test_get_memory_info_mb_parses_known_values() -> None:
    fake_meminfo = (
        "MemTotal:       4000000 kB\nMemAvailable:   2000000 kB\nOther:          123 kB\n"
    )
    with patch("builtins.open", mock_open(read_data=fake_meminfo)):
        total_mb, available_mb = capabilities.get_memory_info_mb()

    assert total_mb == 4000000 / 1024
    assert available_mb == 2000000 / 1024


def test_get_memory_info_mb_returns_none_when_unreadable() -> None:
    with patch("builtins.open", side_effect=OSError("no such file")):
        total_mb, available_mb = capabilities.get_memory_info_mb()

    assert total_mb is None
    assert available_mb is None


def test_torch_and_demucs_not_installed_in_this_environment() -> None:
    # Fait vérifié pour cet environnement de test (dépendance optionnelle
    # volontairement non installée, voir pyproject.toml / docs/MODELS.md).
    assert capabilities.torch_installed() is False
    assert capabilities.demucs_installed() is False


def test_cuda_available_is_false_without_torch() -> None:
    assert capabilities.cuda_available() is False


def test_get_system_capabilities_recommends_cpu_in_this_environment() -> None:
    caps = capabilities.get_system_capabilities()

    assert caps.torch_installed is False
    assert caps.demucs_installed is False
    assert caps.cuda_available is False
    assert caps.recommended_device == "cpu"
    assert caps.cpu_count is not None and caps.cpu_count >= 1
