"""Validation et normalisation des URL YouTube.

Principe de sécurité : on n'accepte qu'un ensemble restreint d'hôtes YouTube
connus, et on en extrait un identifiant de vidéo au format attendu (11
caractères alphanumériques/`-`/`_`). L'URL transmise ensuite à `yt-dlp` est
**toujours reconstruite** à partir de cet identifiant validé
(`https://www.youtube.com/watch?v=<id>`) — jamais la chaîne fournie par
l'utilisateur telle quelle. Cela élimine toute tentative d'injection de
paramètres ou d'URL détournée (ex. vers un autre site que yt-dlp traiterait
différemment) avant même d'atteindre la bibliothèque de téléchargement.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from guitarriff.errors import InvalidYoutubeUrlError

_ALLOWED_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }
)

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _extract_video_id(parsed) -> str | None:  # noqa: ANN001
    host = parsed.hostname or ""

    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
        return candidate or None

    path = parsed.path
    if path == "/watch":
        query = parse_qs(parsed.query)
        values = query.get("v")
        return values[0] if values else None

    for prefix in ("/shorts/", "/embed/", "/live/"):
        if path.startswith(prefix):
            return path[len(prefix) :].split("/")[0]

    return None


def normalize_youtube_url(raw_url: str) -> str:
    """Valide `raw_url` et renvoie une URL YouTube canonique.

    Lève `InvalidYoutubeUrlError` si l'URL n'est pas une URL YouTube reconnue
    (hôte non autorisé, schéma inattendu, identifiant de vidéo introuvable ou
    de forme invalide).
    """

    try:
        parsed = urlparse(raw_url.strip())
    except ValueError as exc:
        raise InvalidYoutubeUrlError("URL YouTube invalide.") from exc

    if parsed.scheme not in ("http", "https"):
        raise InvalidYoutubeUrlError("Seules les URL http(s) sont acceptées.")

    # Rejette toute URL contenant des identifiants (`user:pass@host`), un
    # vecteur classique de confusion d'hôte.
    if "@" in (parsed.netloc or ""):
        raise InvalidYoutubeUrlError("URL YouTube invalide.")

    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        raise InvalidYoutubeUrlError(
            "Seules les URL YouTube sont acceptées.", details={"host": host or None}
        )

    video_id = _extract_video_id(parsed)
    if not video_id or not _VIDEO_ID_RE.match(video_id):
        raise InvalidYoutubeUrlError("Impossible d'extraire un identifiant de vidéo valide.")

    return f"https://www.youtube.com/watch?v={video_id}"


def extract_video_id(raw_url: str) -> str:
    """Raccourci : normalise puis renvoie uniquement l'identifiant de vidéo."""

    normalized = normalize_youtube_url(raw_url)
    return parse_qs(urlparse(normalized).query)["v"][0]
