"""Tests du module d'acquisition YouTube — entièrement simulés (mocks), sans
aucune dépendance à une vidéo YouTube réelle ni à un accès réseau."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from guitarriff.acquisition import youtube
from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.config import Settings
from guitarriff.errors import (
    YoutubeTimeoutError,
    YoutubeUnavailableError,
    YoutubeVideoTooLongError,
)

VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
VALID_WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16


def _fake_info(**overrides: object) -> dict:
    info = {
        "id": "dQw4w9WgXcQ",
        "title": "Une chanson de test",
        "duration": 180,
        "uploader": "Un artiste",
        "webpage_url": VIDEO_URL,
        "is_live": False,
    }
    info.update(overrides)
    return info


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path)


def test_fetch_metadata_returns_parsed_fields(settings: Settings) -> None:
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = _fake_info()

    with patch.object(youtube.yt_dlp, "YoutubeDL", return_value=mock_ydl):
        metadata = youtube.fetch_metadata(VIDEO_URL, settings)

    assert metadata.video_id == "dQw4w9WgXcQ"
    assert metadata.title == "Une chanson de test"
    assert metadata.duration_seconds == 180
    assert metadata.is_live is False
    mock_ydl.extract_info.assert_called_once_with(VIDEO_URL, download=False)


def test_fetch_metadata_never_passes_raw_user_url_to_ydl(settings: Settings) -> None:
    """L'URL transmise à yt-dlp doit toujours être l'URL canonique
    reconstruite, jamais la chaîne brute fournie par l'utilisateur."""
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = _fake_info()
    suspicious_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&evil=1;rm -rf /"

    with patch.object(youtube.yt_dlp, "YoutubeDL", return_value=mock_ydl):
        youtube.fetch_metadata(suspicious_url, settings)

    called_url = mock_ydl.extract_info.call_args.args[0]
    assert called_url == VIDEO_URL
    assert "evil" not in called_url
    assert "rm -rf" not in called_url


def test_fetch_metadata_raises_on_download_error(settings: Settings) -> None:
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError("vidéo privée")

    with patch.object(youtube.yt_dlp, "YoutubeDL", return_value=mock_ydl):
        with pytest.raises(YoutubeUnavailableError):
            youtube.fetch_metadata(VIDEO_URL, settings)


def test_fetch_metadata_times_out_cleanly(settings: Settings) -> None:
    def _never_returns(*_args: object, **_kwargs: object) -> None:
        import time

        time.sleep(5)

    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.side_effect = _never_returns

    fast_settings = Settings(
        _env_file=None, data_dir=settings.data_dir, youtube_download_timeout_seconds=1
    )

    with patch.object(youtube.yt_dlp, "YoutubeDL", return_value=mock_ydl):
        with pytest.raises(YoutubeTimeoutError):
            youtube.fetch_metadata(VIDEO_URL, fast_settings)


def test_download_audio_rejects_video_exceeding_max_duration(settings: Settings) -> None:
    short_settings = Settings(
        _env_file=None, data_dir=settings.data_dir, youtube_max_duration_seconds=60
    )
    storage = AudioFileStorage(short_settings)
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = _fake_info(duration=600)

    with patch.object(youtube.yt_dlp, "YoutubeDL", return_value=mock_ydl):
        with pytest.raises(YoutubeVideoTooLongError):
            youtube.download_audio(VIDEO_URL, short_settings, storage)

    # Aucune tentative de téléchargement ne doit avoir lieu si la durée est
    # déjà rejetée à partir des seules métadonnées.
    mock_ydl.download.assert_not_called()


def test_download_audio_rejects_live_stream(settings: Settings) -> None:
    storage = AudioFileStorage(settings)
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = _fake_info(is_live=True, duration=None)

    with patch.object(youtube.yt_dlp, "YoutubeDL", return_value=mock_ydl):
        with pytest.raises(YoutubeVideoTooLongError):
            youtube.download_audio(VIDEO_URL, settings, storage)


def test_download_audio_success_stores_file_with_metadata(settings: Settings) -> None:
    storage = AudioFileStorage(settings)

    def _fake_download(urls: list[str]) -> None:
        # Simule ce que ferait réellement yt-dlp + FFmpegExtractAudio : écrire
        # un fichier audio dans le répertoire de travail temporaire.
        job_dirs = list(settings.youtube_tmp_dir.glob("*"))
        assert len(job_dirs) == 1
        (job_dirs[0] / "audio.wav").write_bytes(VALID_WAV)

    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = _fake_info()
    mock_ydl.download.side_effect = _fake_download

    with patch.object(youtube.yt_dlp, "YoutubeDL", return_value=mock_ydl):
        record = youtube.download_audio(VIDEO_URL, settings, storage)

    assert record.source == "youtube"
    assert record.source_url == VIDEO_URL
    assert record.title == "Une chanson de test"
    assert record.format == "wav"

    # Le répertoire temporaire de travail doit avoir été nettoyé.
    assert list(settings.youtube_tmp_dir.glob("*")) == []

    # Les métadonnées doivent être relisibles via le stockage normal.
    fetched = storage.get(record.file_id)
    assert fetched.source == "youtube"
    assert fetched.title == "Une chanson de test"


def test_download_audio_cleans_up_tmp_dir_on_failure(settings: Settings) -> None:
    storage = AudioFileStorage(settings)
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = _fake_info()
    mock_ydl.download.side_effect = yt_dlp.utils.DownloadError("erreur réseau")

    with patch.object(youtube.yt_dlp, "YoutubeDL", return_value=mock_ydl):
        with pytest.raises(YoutubeUnavailableError):
            youtube.download_audio(VIDEO_URL, settings, storage)

    assert list(settings.youtube_tmp_dir.glob("*")) == []


def test_download_audio_raises_if_no_file_produced(settings: Settings) -> None:
    storage = AudioFileStorage(settings)
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = _fake_info()
    mock_ydl.download.return_value = None  # ne crée aucun fichier

    with patch.object(youtube.yt_dlp, "YoutubeDL", return_value=mock_ydl):
        with pytest.raises(YoutubeUnavailableError):
            youtube.download_audio(VIDEO_URL, settings, storage)


def test_download_never_uses_a_shell_or_subprocess(settings: Settings) -> None:
    """Garde-fou explicite : ce module n'invoque jamais `subprocess` ni
    `os.system` — uniquement l'API Python de yt-dlp."""
    import inspect

    source = inspect.getsource(youtube)
    assert "subprocess" not in source
    assert "os.system" not in source
    assert "shell=True" not in source
