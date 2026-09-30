"""Vérifie que la détection de format se base sur le contenu réel du fichier,
pas sur l'extension ni un Content-Type déclaré."""

from __future__ import annotations

from guitarriff.acquisition.formats import (
    ALLOWED_EXTENSIONS,
    FLAC,
    M4A,
    MP3,
    OGG,
    WAV,
    detect_format,
    extension_matches_format,
)

# En-têtes minimaux, juste assez pour être reconnus par le détecteur.
VALID_WAV_HEADER = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
VALID_FLAC_HEADER = b"fLaC" + b"\x00" * 16
VALID_OGG_HEADER = b"OggS" + b"\x00" * 16
VALID_M4A_HEADER = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 8
VALID_MP3_ID3_HEADER = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 8
VALID_MP3_FRAME_SYNC_HEADER = b"\xff\xfb\x90\x00" + b"\x00" * 16


def test_detects_wav_from_riff_wave_header() -> None:
    assert detect_format(VALID_WAV_HEADER) == WAV


def test_detects_flac_from_magic_bytes() -> None:
    assert detect_format(VALID_FLAC_HEADER) == FLAC


def test_detects_ogg_from_magic_bytes() -> None:
    assert detect_format(VALID_OGG_HEADER) == OGG


def test_detects_m4a_from_ftyp_box() -> None:
    assert detect_format(VALID_M4A_HEADER) == M4A


def test_detects_mp3_from_id3_tag() -> None:
    assert detect_format(VALID_MP3_ID3_HEADER) == MP3


def test_detects_mp3_from_frame_sync() -> None:
    assert detect_format(VALID_MP3_FRAME_SYNC_HEADER) == MP3


def test_rejects_unrecognized_content() -> None:
    assert detect_format(b"this is definitely not an audio file") is None


def test_rejects_executable_content_disguised_as_audio() -> None:
    # En-tête d'exécutable ELF Linux — ne doit jamais être reconnu comme audio,
    # quel que soit le nom de fichier fourni par ailleurs.
    elf_header = b"\x7fELF" + b"\x00" * 16
    assert detect_format(elf_header) is None


def test_extension_matches_format() -> None:
    assert extension_matches_format(".wav", WAV) is True
    assert extension_matches_format(".WAV", WAV) is True
    assert extension_matches_format(".mp3", WAV) is False


def test_allowed_extensions_cover_all_supported_formats() -> None:
    assert ALLOWED_EXTENSIONS == {".wav", ".flac", ".ogg", ".oga", ".m4a", ".mp3"}
