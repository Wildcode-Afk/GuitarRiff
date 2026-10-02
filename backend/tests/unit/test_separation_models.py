"""Tests de `separation/models.py` — vérifie que les limites connues de
chaque mode sont bien documentées (pas seulement que le code tourne)."""

from __future__ import annotations

import pytest

from guitarriff.errors import InvalidSeparationModeError
from guitarriff.separation.models import get_mode


def test_none_mode_has_mixture_stem() -> None:
    mode = get_mode("none")
    assert mode.stems == ("mixture",)
    assert mode.experimental is False


def test_htdemucs_mode_documents_that_other_is_not_isolated_guitar() -> None:
    mode = get_mode("htdemucs")
    assert mode.stems == ("drums", "bass", "other", "vocals")
    assert mode.experimental is False
    assert "guitare" in mode.notes.lower()
    assert "pas une guitare isolée" in mode.notes.lower() or "pas" in mode.notes.lower()
    assert "artefacts" in mode.notes.lower()


def test_htdemucs_6s_mode_is_marked_experimental_with_known_caveats() -> None:
    mode = get_mode("htdemucs_6s")
    assert "guitar" in mode.stems
    assert "piano" in mode.stems
    assert mode.experimental is True
    assert "expérimental" in mode.notes.lower()
    assert "piano" in mode.notes.lower()


def test_get_mode_rejects_unknown_key() -> None:
    with pytest.raises(InvalidSeparationModeError) as exc_info:
        get_mode("spleeter")

    assert exc_info.value.details["mode"] == "spleeter"
    assert "available_modes" in exc_info.value.details
