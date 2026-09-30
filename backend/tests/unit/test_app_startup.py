"""Vérifie que l'application FastAPI démarre et répond correctement, sans
dépendre d'aucune fonctionnalité audio (Étape 2 — fondations uniquement)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from guitarriff.api.app import create_app


def test_app_starts_and_health_endpoint_responds() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "app_env" in body
    assert "job_concurrency" in body


def test_health_reflects_configuration(monkeypatch) -> None:
    monkeypatch.setenv("JOB_CONCURRENCY", "1")
    monkeypatch.setenv("YTDLP_ENABLED", "true")

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")

    body = response.json()
    assert body["job_concurrency"] == 1
    assert body["ytdlp_enabled"] is True


def test_health_verbose_reports_checks_without_leaking_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health", params={"verbose": True})

    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["data_dir_writable"] is True
    # Aucun chemin absolu du système de fichiers ne doit apparaître dans la réponse.
    assert str(tmp_path) not in response.text


def test_version_endpoint_returns_name_and_version() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/version")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "guitarriff"
    assert "version" in body


def test_cors_allows_configured_frontend_origin(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
