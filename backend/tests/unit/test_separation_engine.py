"""Tests de `separation/engine.py`.

Le cas "Demucs non installé" est testé **réellement, sans mock** : cette
dépendance optionnelle n'est pas installée dans cet environnement de test
(voir pyproject.toml), ce qui permet de vérifier pour de vrai le
comportement attendu en son absence — sans jamais avoir besoin de
télécharger quoi que ce soit.

Les cas "Demucs installé" sont simulés via un faux `_import_demucs`, pour ne
jamais dépendre d'un vrai modèle téléchargé."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from guitarriff.errors import (
    DemucsNotInstalledError,
    SeparationError,
    SeparationModelUnavailableError,
)
from guitarriff.separation import engine
from guitarriff.separation.models import HTDEMUCS
from guitarriff.separation.progress import Stage


def test_run_separation_raises_when_demucs_not_installed_for_real(tmp_path: Path) -> None:
    # Pas de mock ici : Demucs est réellement absent de cet environnement.
    with pytest.raises(DemucsNotInstalledError):
        engine.run_separation(
            tmp_path / "source.wav",
            tmp_path / "out",
            HTDEMUCS,
            allow_model_download=True,
        )


def _fake_torch_stack(sources_tensor, sample_names):
    """Construit un faux (torch, apply_model, AudioFile, save_audio, get_model)
    suffisant pour exercer la logique de `engine.run_separation` sans aucune
    dépendance réelle à torch/demucs."""

    fake_model = MagicMock()
    fake_model.samplerate = 44100
    fake_model.audio_channels = 2
    fake_model.sources = sample_names
    fake_model.eval = MagicMock()

    fake_audio_file_instance = MagicMock()
    fake_audio_file_instance.read.return_value = MagicMock(
        mean=MagicMock(
            return_value=MagicMock(
                mean=MagicMock(return_value=0.0), std=MagicMock(return_value=1.0)
            )
        )
    )
    # Permet `wav - ref.mean()` / `wav / ref.std()` sans vraie arithmétique tensorielle :
    fake_wav = MagicMock()
    fake_wav.__sub__ = MagicMock(return_value=fake_wav)
    fake_wav.__truediv__ = MagicMock(return_value=fake_wav)
    fake_wav.__getitem__ = MagicMock(return_value=fake_wav)
    fake_wav.mean.return_value.mean.return_value = 0.0
    fake_wav.mean.return_value.std.return_value = 1.0
    fake_audio_file_instance.read.return_value = fake_wav

    fake_audio_file_cls = MagicMock(return_value=fake_audio_file_instance)

    fake_apply_model = MagicMock(return_value=[sources_tensor])

    fake_save_audio = MagicMock()

    fake_get_model = MagicMock(return_value=fake_model)

    fake_torch = MagicMock()
    fake_torch.no_grad.return_value.__enter__ = MagicMock(return_value=None)
    fake_torch.no_grad.return_value.__exit__ = MagicMock(return_value=False)

    return fake_torch, fake_apply_model, fake_audio_file_cls, fake_save_audio, fake_get_model


def test_run_separation_success_writes_all_stems(tmp_path: Path) -> None:
    stem_names = ["drums", "bass", "other", "vocals"]
    fake_sources = MagicMock()
    fake_sources.__mul__ = MagicMock(return_value=fake_sources)
    fake_sources.__add__ = MagicMock(return_value=fake_sources)
    # zip(estimated_sources, model.sources) doit pouvoir itérer : on simule
    # une liste de 4 "waveforms" factices.
    fake_sources.__iter__ = MagicMock(return_value=iter([MagicMock() for _ in stem_names]))

    fakes = _fake_torch_stack(fake_sources, stem_names)
    stages_seen: list[Stage] = []

    with patch.object(engine, "_import_demucs", return_value=fakes):
        produced = engine.run_separation(
            tmp_path / "source.wav",
            tmp_path / "out",
            HTDEMUCS,
            allow_model_download=True,
            on_stage=stages_seen.append,
        )

    assert produced == stem_names
    assert stages_seen == [Stage.LOADING_MODEL, Stage.SEPARATING, Stage.WRITING_STEMS]
    # save_audio doit avoir été appelé une fois par piste.
    fake_save_audio = fakes[3]
    assert fake_save_audio.call_count == len(stem_names)


def test_run_separation_raises_when_download_disabled(tmp_path: Path) -> None:
    fakes = _fake_torch_stack(MagicMock(), ["drums", "bass", "other", "vocals"])

    with patch.object(engine, "_import_demucs", return_value=fakes):
        with pytest.raises(SeparationModelUnavailableError):
            engine.run_separation(
                tmp_path / "source.wav",
                tmp_path / "out",
                HTDEMUCS,
                allow_model_download=False,
            )

    # get_model ne doit même pas avoir été tenté.
    fake_get_model = fakes[4]
    fake_get_model.assert_not_called()


def test_run_separation_raises_when_model_loading_fails(tmp_path: Path) -> None:
    fakes = _fake_torch_stack(MagicMock(), ["drums", "bass", "other", "vocals"])
    fake_get_model = fakes[4]
    fake_get_model.side_effect = RuntimeError("réseau indisponible")

    with patch.object(engine, "_import_demucs", return_value=fakes):
        with pytest.raises(SeparationModelUnavailableError):
            engine.run_separation(
                tmp_path / "source.wav",
                tmp_path / "out",
                HTDEMUCS,
                allow_model_download=True,
            )


def test_run_separation_raises_separation_error_on_apply_model_failure(tmp_path: Path) -> None:
    fakes = _fake_torch_stack(MagicMock(), ["drums", "bass", "other", "vocals"])
    fake_apply_model = fakes[1]
    fake_apply_model.side_effect = RuntimeError("crash interne")

    with patch.object(engine, "_import_demucs", return_value=fakes):
        with pytest.raises(SeparationError):
            engine.run_separation(
                tmp_path / "source.wav",
                tmp_path / "out",
                HTDEMUCS,
                allow_model_download=True,
            )
