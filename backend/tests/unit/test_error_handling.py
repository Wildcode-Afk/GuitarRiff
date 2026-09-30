"""Vérifie que les erreurs (404, 405, 422, 500) renvoient toutes la même
enveloppe JSON cohérente et ne révèlent jamais de détail interne sensible
(chemin système, trace, message d'exception brut)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from guitarriff.api.app import create_app
from guitarriff.errors import AppError, NotFoundError, register_error_handlers


def test_unknown_route_returns_json_error_envelope() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "http_404"
    assert "message" in body["error"]


def test_wrong_method_returns_405_error_envelope() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/health")

    assert response.status_code == 405
    body = response.json()
    assert body["error"]["code"] == "http_405"


def test_invalid_query_param_type_returns_422_error_envelope() -> None:
    app = create_app()
    with TestClient(app) as client:
        # `verbose` attend un booléen : une valeur non convertible doit être rejetée.
        response = client.get("/health", params={"verbose": "pas-un-booleen"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["errors"]
    # Le détail doit rester structuré (loc/msg/type), sans objet Python brut.
    for err in body["error"]["details"]["errors"]:
        assert set(err.keys()) == {"loc", "msg", "type"}


def test_app_error_subclass_returns_its_own_status_and_code() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom-not-found")
    def _boom_not_found() -> None:
        raise NotFoundError("Ressource introuvable.", details={"id": "abc123"})

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom-not-found")

    assert response.status_code == 404
    body = response.json()
    assert body["error"] == {
        "code": "not_found",
        "message": "Ressource introuvable.",
        "details": {"id": "abc123"},
    }


def test_unhandled_exception_returns_generic_500_without_leaking_details() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom-internal")
    def _boom_internal() -> None:
        raise RuntimeError("secret internal detail: /home/max/private/data.db")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom-internal")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    # Le message d'exception original (et tout chemin qu'il contient) ne doit
    # jamais atteindre la réponse HTTP.
    assert "secret internal detail" not in response.text
    assert "/home/max" not in response.text


def test_app_error_base_class_defaults() -> None:
    err = AppError("test")
    assert err.status_code == 400
    assert err.error_code == "app_error"
    assert err.details == {}
