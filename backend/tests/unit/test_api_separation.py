"""Tests bout-en-bout (TestClient) de l'API de séparation.

Deux familles de tests :
1. Avec `separation.service.run_separation` simulé (comportement "heureux").
2. **Un vrai test d'intégration sans aucun mock** qui exploite l'absence
   réelle de Demucs dans cet environnement pour vérifier la gestion d'un
   modèle absent de bout en bout — sans réseau ni téléchargement.
"""

from __future__ import annotations

import subprocess
import time as time_module
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from guitarriff.api.app import create_app
from guitarriff.separation import service as separation_service
from guitarriff.separation.progress import progress_store


def _generate_test_wav(path: Path, *, duration: float = 1.0) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _client(monkeypatch, tmp_path, **env: str) -> TestClient:
    progress_store._entries.clear()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return TestClient(create_app())


def _upload(client: TestClient, tmp_path: Path, *, duration: float = 1.0) -> str:
    source = tmp_path / "gen.wav"
    _generate_test_wav(source, duration=duration)
    response = client.post(
        "/audio-files", files={"file": ("chanson.wav", source.read_bytes(), "audio/wav")}
    )
    assert response.status_code == 201
    return response.json()["file_id"]


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    deadline = time_module.time() + timeout
    while time_module.time() < deadline:
        if predicate():
            return True
        time_module.sleep(interval)
    return predicate()


def test_separation_mode_none_completes_synchronously(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path)

    response = client.post(f"/audio-files/{file_id}/separate", json={"mode": "none"})

    assert response.status_code == 202
    body = response.json()
    assert body["stage"] == "done"
    assert body["stems"] == ["mixture"]


def test_separation_unknown_file_returns_404(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.post(
        "/audio-files/11111111-1111-1111-1111-111111111111/separate", json={"mode": "none"}
    )

    assert response.status_code == 404


def test_separation_invalid_mode_returns_400(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path)

    response = client.post(f"/audio-files/{file_id}/separate", json={"mode": "spleeter"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_separation_mode"


def test_separation_audio_too_long_returns_422(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path, AUDIO_MAX_DURATION_SECONDS="1")
    file_id = _upload(client, tmp_path, duration=3.0)

    # Vérification de durée faite de manière synchrone avant tout démarrage
    # en arrière-plan : l'erreur est immédiate, pas via le statut async.
    response = client.post(f"/audio-files/{file_id}/separate", json={"mode": "htdemucs"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "audio_too_long"


def test_separation_happy_path_with_mocked_engine(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path)

    def fake_run_separation(
        source_path, output_dir, model_info, *, allow_model_download, on_stage=None
    ):
        output_dir.mkdir(parents=True, exist_ok=True)
        for stem in model_info.stems:
            (output_dir / f"{stem}.wav").write_bytes(b"RIFF....WAVEfmt fake content")
        return list(model_info.stems)

    with patch.object(separation_service, "run_separation", side_effect=fake_run_separation):
        start_response = client.post(f"/audio-files/{file_id}/separate", json={"mode": "htdemucs"})
        assert start_response.status_code == 202

        done = _wait_until(
            lambda: (
                client.get(f"/audio-files/{file_id}/separate/htdemucs").json()["stage"] == "done"
            )
        )
        assert done

    status_body = client.get(f"/audio-files/{file_id}/separate/htdemucs").json()
    assert status_body["stems"] == ["drums", "bass", "other", "vocals"]
    assert "guitare" in status_body["notes"].lower()

    # Téléchargement d'une piste produite.
    stem_response = client.get(f"/audio-files/{file_id}/separate/htdemucs/stems/bass")
    assert stem_response.status_code == 200
    assert stem_response.content == b"RIFF....WAVEfmt fake content"


def test_download_stem_rejects_unknown_stem_name(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path)

    response = client.get(f"/audio-files/{file_id}/separate/htdemucs/stems/triangle")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_download_stem_before_computed_returns_404(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path)

    response = client.get(f"/audio-files/{file_id}/separate/htdemucs/stems/bass")

    assert response.status_code == 404


def test_separation_without_demucs_installed_is_handled_gracefully_real(
    monkeypatch, tmp_path
) -> None:
    """Test d'intégration réel, sans aucun mock : Demucs n'est pas installé
    dans cet environnement (dépendance optionnelle, voir pyproject.toml),
    donc ce test exerce pour de vrai le chemin "modèle absent" — sans
    réseau ni téléchargement d'aucune sorte."""

    client = _client(monkeypatch, tmp_path)
    file_id = _upload(client, tmp_path)

    start_response = client.post(f"/audio-files/{file_id}/separate", json={"mode": "htdemucs"})
    assert start_response.status_code == 202

    errored = _wait_until(
        lambda: client.get(f"/audio-files/{file_id}/separate/htdemucs").json()["stage"] == "error"
    )
    assert errored
    status_body = client.get(f"/audio-files/{file_id}/separate/htdemucs").json()
    assert "demucs" in status_body["error"].lower() or "install" in status_body["error"].lower()


def test_health_verbose_reports_separation_capabilities(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.get("/health", params={"verbose": True})

    assert response.status_code == 200
    separation_caps = response.json()["checks"]["separation"]
    assert separation_caps["torch_installed"] is False
    assert separation_caps["demucs_installed"] is False
    assert separation_caps["recommended_device"] == "cpu"
