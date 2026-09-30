"""Tests bout-en-bout (via TestClient) de l'API d'import de fichiers audio."""

from __future__ import annotations

from fastapi.testclient import TestClient

from guitarriff.api.app import create_app

VALID_WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16


def _client(monkeypatch, tmp_path, **env: str) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return TestClient(create_app())


def test_upload_valid_wav_returns_metadata(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.post(
        "/audio-files", files={"file": ("chanson.wav", VALID_WAV, "audio/wav")}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["format"] == "wav"
    assert body["size_bytes"] == len(VALID_WAV)
    assert body["original_filename"] == "chanson.wav"
    assert body["status"] == "stored"


def test_upload_rejects_unsupported_content(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.post(
        "/audio-files", files={"file": ("note.txt", b"hello world", "text/plain")}
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file_type"


def test_upload_rejects_oversized_file(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path, MAX_UPLOAD_SIZE_MB="1")
    oversized = VALID_WAV + b"\x00" * (2 * 1024 * 1024)

    response = client.post(
        "/audio-files", files={"file": ("big.wav", oversized, "audio/wav")}
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_upload_path_traversal_filename_is_neutralized(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.post(
        "/audio-files",
        files={"file": ("../../../etc/passwd.wav", VALID_WAV, "audio/wav")},
    )

    assert response.status_code == 201
    assert not (tmp_path / "etc").exists()
    assert "/" not in response.json()["original_filename"]


def test_get_then_delete_then_404(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    upload = client.post(
        "/audio-files", files={"file": ("chanson.wav", VALID_WAV, "audio/wav")}
    )
    file_id = upload.json()["file_id"]

    get_response = client.get(f"/audio-files/{file_id}")
    assert get_response.status_code == 200
    assert get_response.json()["file_id"] == file_id

    delete_response = client.delete(f"/audio-files/{file_id}")
    assert delete_response.status_code == 204

    after_delete = client.get(f"/audio-files/{file_id}")
    assert after_delete.status_code == 404
    assert after_delete.json()["error"]["code"] == "not_found"


def test_get_with_path_traversal_id_returns_400_not_500(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    # FastAPI normalise déjà `..` dans l'URL avant routage ; on vérifie
    # surtout qu'un id encodé (%2e%2e) — qui atteint bien notre code — est
    # rejeté proprement par la validation d'UUID plutôt que de provoquer une
    # 500 ou de toucher le système de fichiers.
    response_encoded = client.get("/audio-files/%2e%2e%2f%2e%2e%2fetc%2fpasswd")
    assert response_encoded.status_code in (400, 404)
    if response_encoded.status_code == 400:
        assert response_encoded.json()["error"]["code"] == "invalid_file_id"


def test_get_unknown_uuid_returns_404(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.get("/audio-files/11111111-1111-1111-1111-111111111111")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
