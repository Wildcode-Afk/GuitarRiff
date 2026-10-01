"""Tests bout-en-bout (TestClient) de l'API d'import YouTube — réponses
yt-dlp simulées, aucun accès réseau."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from guitarriff.acquisition import youtube
from guitarriff.api.app import create_app

VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
VALID_WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16


def _client(monkeypatch, tmp_path, **env: str) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return TestClient(create_app())


def _mock_ydl(*, info: dict, download_side_effect=None) -> MagicMock:
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = info
    if download_side_effect is not None:
        mock_ydl.download.side_effect = download_side_effect
    return mock_ydl


def test_import_from_youtube_success(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    def _fake_download(urls: list[str]) -> None:
        job_dirs = list((tmp_path / "tmp" / "youtube").glob("*"))
        (job_dirs[0] / "audio.wav").write_bytes(VALID_WAV)

    mock_ydl = _mock_ydl(
        info={
            "id": "dQw4w9WgXcQ",
            "title": "Ma chanson",
            "duration": 120,
            "uploader": "Artiste",
            "webpage_url": VIDEO_URL,
            "is_live": False,
        },
        download_side_effect=_fake_download,
    )

    with patch.object(youtube.yt_dlp, "YoutubeDL", return_value=mock_ydl):
        response = client.post("/youtube-imports", json={"url": VIDEO_URL})

    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "youtube"
    assert body["title"] == "Ma chanson"
    assert body["format"] == "wav"


def test_import_from_youtube_rejects_non_youtube_url(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.post("/youtube-imports", json={"url": "https://example.com/video"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_youtube_url"


def test_import_from_youtube_rejects_video_too_long(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path, YOUTUBE_MAX_DURATION_SECONDS="60")
    mock_ydl = _mock_ydl(
        info={
            "id": "dQw4w9WgXcQ",
            "title": "Longue vidéo",
            "duration": 3600,
            "uploader": "Artiste",
            "webpage_url": VIDEO_URL,
            "is_live": False,
        }
    )

    with patch.object(youtube.yt_dlp, "YoutubeDL", return_value=mock_ydl):
        response = client.post("/youtube-imports", json={"url": VIDEO_URL})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "youtube_video_too_long"


def test_import_from_youtube_handles_unavailable_video(monkeypatch, tmp_path) -> None:
    import yt_dlp as real_yt_dlp

    client = _client(monkeypatch, tmp_path)
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.side_effect = real_yt_dlp.utils.DownloadError("Video unavailable")

    with patch.object(youtube.yt_dlp, "YoutubeDL", return_value=mock_ydl):
        response = client.post("/youtube-imports", json={"url": VIDEO_URL})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "youtube_unavailable"


def test_import_from_youtube_rejects_missing_url(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.post("/youtube-imports", json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
