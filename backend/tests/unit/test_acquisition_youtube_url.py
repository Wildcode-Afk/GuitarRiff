"""Vérifie la validation et la normalisation des URL YouTube, sans réseau."""

from __future__ import annotations

import pytest

from guitarriff.acquisition.youtube_url import extract_video_id, normalize_youtube_url
from guitarriff.errors import InvalidYoutubeUrlError

VIDEO_ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtube.com/watch?v={VIDEO_ID}",
        f"http://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"https://music.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&list=PL123&index=2",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"  https://www.youtube.com/watch?v={VIDEO_ID}  ",
    ],
)
def test_normalize_accepts_known_youtube_url_forms(url: str) -> None:
    assert normalize_youtube_url(url) == f"https://www.youtube.com/watch?v={VIDEO_ID}"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://vimeo.com/123456",
        "https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ",
        "ftp://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "javascript:alert(1)",
        "https://user:pass@www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch?v=",
        "https://www.youtube.com/",
        "https://www.youtube.com/channel/UC1234567890",
        "not a url at all",
        "",
        "   ",
    ],
)
def test_normalize_rejects_unsupported_or_malicious_urls(url: str) -> None:
    with pytest.raises(InvalidYoutubeUrlError):
        normalize_youtube_url(url)


def test_extract_video_id_returns_the_canonical_id() -> None:
    assert extract_video_id(f"https://youtu.be/{VIDEO_ID}") == VIDEO_ID
