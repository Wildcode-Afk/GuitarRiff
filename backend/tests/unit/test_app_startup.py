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
