"""Détection des formats audio réellement supportés.

Principe de sécurité : on ne fait jamais confiance à l'extension du fichier
ni au `Content-Type` déclaré par le client — les deux sont trivialement
falsifiables. La décision d'accepter ou non un fichier se base sur la
signature binaire (« magic bytes ») lue au début du fichier lui-même.

L'extension déclarée doit malgré tout être cohérente avec le contenu détecté
(elle sert uniquement à choisir un nom de fichier lisible côté métadonnées,
jamais à construire un chemin sur le disque — voir `storage.py`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# Nombre d'octets suffisant pour identifier chacun des formats ci-dessous.
SNIFF_SIZE = 64


@dataclass(frozen=True)
class AudioFormat:
    key: str  # identifiant stable (utilisé dans l'API et le stockage)
    label: str  # nom lisible
    extensions: tuple[str, ...]  # extensions acceptées pour ce format
    content_type: str  # Content-Type renvoyé dans les métadonnées


WAV = AudioFormat("wav", "WAV", (".wav",), "audio/wav")
FLAC = AudioFormat("flac", "FLAC", (".flac",), "audio/flac")
OGG = AudioFormat("ogg", "OGG (Vorbis/Opus)", (".ogg", ".oga"), "audio/ogg")
M4A = AudioFormat("m4a", "M4A/AAC (MP4 audio)", (".m4a",), "audio/mp4")
MP3 = AudioFormat("mp3", "MP3", (".mp3",), "audio/mpeg")

SUPPORTED_FORMATS: tuple[AudioFormat, ...] = (WAV, FLAC, OGG, M4A, MP3)

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    ext for fmt in SUPPORTED_FORMATS for ext in fmt.extensions
)


def _is_wav(header: bytes) -> bool:
    return header[:4] == b"RIFF" and header[8:12] == b"WAVE"


def _is_flac(header: bytes) -> bool:
    return header[:4] == b"fLaC"


def _is_ogg(header: bytes) -> bool:
    return header[:4] == b"OggS"


def _is_m4a(header: bytes) -> bool:
    # Conteneur MP4/QuickTime : boîte "ftyp" à l'offset 4.
    return header[4:8] == b"ftyp"


def _is_mp3(header: bytes) -> bool:
    if header[:3] == b"ID3":
        return True
    # Sans tag ID3 : recherche d'un "frame sync" MPEG (11 bits à 1) en tout
    # début de fichier — suffisant pour distinguer un vrai flux MP3 d'un
    # fichier renommé au hasard, sans prétendre valider le flux entier.
    return len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0


_DETECTORS: tuple[tuple[AudioFormat, Callable[[bytes], bool]], ...] = (
    (WAV, _is_wav),
    (FLAC, _is_flac),
    (OGG, _is_ogg),
    (M4A, _is_m4a),
    (MP3, _is_mp3),
)


def detect_format(header: bytes) -> AudioFormat | None:
    """Identifie le format audio à partir des premiers octets du fichier.

    Renvoie `None` si aucun format supporté n'est reconnu — c'est au code
    appelant de traduire cela en erreur utilisateur (voir `errors.py`).
    """

    for fmt, detector in _DETECTORS:
        if detector(header):
            return fmt
    return None


def extension_matches_format(extension: str, fmt: AudioFormat) -> bool:
    return extension.lower() in fmt.extensions
