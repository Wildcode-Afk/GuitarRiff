"""Lecture de métadonnées et normalisation audio via FFmpeg/ffprobe.

## Format cible — justifié, pas arbitraire

Ce module convertit tout audio vers exactement :

- **22050 Hz**, **mono**, **PCM 16 bits**.

Ce n'est pas un choix arbitraire : `basic-pitch` (le modèle de transcription
retenu — voir docs/ARCHITECTURE.md et docs/TECHNICAL_DECISIONS.md) déclare
explicitement, dans son propre code source (`basic_pitch/constants.py`,
vérifié directement dans l'environnement du projet) :

    AUDIO_SAMPLE_RATE = 22050
    AUDIO_N_CHANNELS = 1

Le PCM 16 bits est retenu pour le conteneur intermédiaire plutôt qu'un format
flottant plus large : `librosa` (utilisé en interne par `basic-pitch`)
reconvertit de toute façon tout flux en `float32` normalisé au chargement,
quel que soit le bit-depth source — un conteneur 16 bits (96 dB de plage
dynamique, largement suffisant pour de l'audio musical déjà compressé/mixé)
évite donc de doubler inutilement la taille des fichiers intermédiaires sans
aucun gain de précision mesurable pour cet usage.

Si une étape de séparation d'instruments (Demucs, V2 — voir
docs/FEATURE_MATRIX.md) est ajoutée plus tard, elle a ses propres exigences
(généralement 44100 Hz stéréo) : ce module ne les anticipe pas, un réglage
dédié sera à faire à ce moment-là plutôt que de deviner aujourd'hui.

## Sécurité

`source_path`/`target_path` doivent toujours être des chemins déjà internes
et validés (ex. produits par `AudioFileStorage`) — ce module ne construit
jamais un chemin ni une commande à partir d'une chaîne fournie directement
par un utilisateur. Les appels `ffmpeg`/`ffprobe` passent toujours par une
liste d'arguments (`subprocess.run([...], shell=False)`), jamais par une
chaîne shell interpolée.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from guitarriff.errors import (
    AudioProcessingError,
    AudioProcessingTimeoutError,
    FFmpegUnavailableError,
    InvalidAudioFileError,
)
from guitarriff.logging_config import get_logger

logger = get_logger(__name__)

# Valeurs imposées par basic-pitch (voir docstring ci-dessus) — volontairement
# non configurables via l'environnement : ce n'est pas une préférence de
# déploiement mais une contrainte du modèle de transcription retenu.
TARGET_SAMPLE_RATE = 22050
TARGET_CHANNELS = 1
TARGET_SAMPLE_FORMAT = "s16"  # PCM 16 bits signé


@dataclass(frozen=True)
class AudioProbe:
    duration_seconds: float
    sample_rate: int
    channels: int
    codec_name: str


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def require_ffmpeg() -> None:
    if not ffmpeg_available():
        raise FFmpegUnavailableError("FFmpeg (ou ffprobe) n'est pas disponible sur ce système.")


def probe_audio(path: Path, *, timeout_seconds: int) -> AudioProbe:
    """Lit les métadonnées réelles d'un fichier audio via `ffprobe`."""

    require_ffmpeg()
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired as exc:
        raise AudioProcessingTimeoutError(
            "L'analyse du fichier audio a dépassé le délai maximal."
        ) from exc

    if result.returncode != 0:
        logger.warning(
            "ffprobe a échoué sur %s (code %d): %s",
            path.name,
            result.returncode,
            result.stderr.decode(errors="replace").strip(),
        )
        raise InvalidAudioFileError("Le fichier audio est invalide ou illisible.")

    try:
        data = json.loads(result.stdout)
        audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
        if not audio_streams:
            raise InvalidAudioFileError("Aucun flux audio détecté dans ce fichier.")
        stream = audio_streams[0]
        duration_raw = data.get("format", {}).get("duration") or stream.get("duration")
        return AudioProbe(
            duration_seconds=float(duration_raw),
            sample_rate=int(stream["sample_rate"]),
            channels=int(stream["channels"]),
            codec_name=str(stream.get("codec_name", "unknown")),
        )
    except InvalidAudioFileError:
        raise
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidAudioFileError(
            "Impossible d'interpréter les métadonnées du fichier audio."
        ) from exc


def normalize_audio(source_path: Path, target_path: Path, *, timeout_seconds: int) -> None:
    """Convertit `source_path` vers le format interne cible et écrit le
    résultat à `target_path`.

    Écrit d'abord dans un fichier temporaire (`<target>.tmp`) puis le
    renomme atomiquement vers `target_path` une fois la conversion réussie —
    `target_path` n'existe donc jamais dans un état partiel/corrompu, et le
    fichier temporaire est systématiquement nettoyé (succès ou échec).
    """

    require_ffmpeg()
    tmp_path = target_path.with_name(target_path.name + ".tmp")
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-ac",
        str(TARGET_CHANNELS),
        "-ar",
        str(TARGET_SAMPLE_RATE),
        "-sample_fmt",
        TARGET_SAMPLE_FORMAT,
        "-f",
        "wav",
        str(tmp_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout_seconds, check=False)
        if result.returncode != 0 or not tmp_path.is_file():
            logger.error(
                "ffmpeg a échoué sur %s (code %d): %s",
                source_path.name,
                result.returncode,
                result.stderr.decode(errors="replace").strip(),
            )
            raise AudioProcessingError("La conversion du fichier audio a échoué.")
        tmp_path.replace(target_path)
    except subprocess.TimeoutExpired as exc:
        raise AudioProcessingTimeoutError(
            "La conversion audio a dépassé le délai maximal."
        ) from exc
    finally:
        tmp_path.unlink(missing_ok=True)
