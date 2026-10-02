"""Configuration de l'application, chargée depuis les variables d'environnement.

Toute la configuration passe par cette classe unique (`Settings`). Aucune autre
partie du code ne doit lire `os.environ` directement : cela garde la configuration
centralisée, typée et testable.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    development = "development"
    production = "production"
    test = "test"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    """Configuration validée de l'application.

    Les valeurs par défaut correspondent aux décisions prises dans
    docs/TECHNICAL_DECISIONS.md (notamment D6 : concurrence de jobs = 1).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: AppEnv = AppEnv.development
    log_level: LogLevel = LogLevel.INFO

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)

    # Origines autorisées pour les appels du frontend (CORS), en chaîne brute
    # séparée par des virgules (ex. "http://localhost:5173,http://127.0.0.1:5173").
    # Stocké en str plutôt qu'en list[str] : pydantic-settings tente de
    # décoder les champs de type liste comme du JSON depuis l'environnement,
    # ce qui casserait un simple `CORS_ORIGINS=a,b,c`. Utiliser
    # `cors_origins_list` pour la valeur exploitable.
    cors_origins: str = "http://localhost:5173"

    data_dir: Path = Path("./data")

    # Décision D6 : concurrence prudente par défaut (empreinte mémoire de
    # TensorFlow/PyTorch sur machine modeste). Ajustable une fois le
    # matériel cible mieux connu.
    job_concurrency: int = Field(default=1, ge=1)

    # Décision Q1 : yt-dlp est prévu, mais pas encore implémenté à ce stade
    # (squelette uniquement — aucune fonctionnalité audio à cette étape).
    ytdlp_enabled: bool = True

    # Taille maximale acceptée pour un fichier audio importé (Étape 4).
    # 100 Mo par défaut : large pour un fichier audio compressé, mais borné
    # pour éviter qu'un import ne sature le disque/la mémoire sur une
    # machine modeste (voir docs/TECHNICAL_DECISIONS.md, D6).
    max_upload_size_mb: int = Field(default=100, ge=1)

    # Décision Q1 (docs/TECHNICAL_DECISIONS.md) : acquisition YouTube via
    # yt-dlp, usage personnel, sous la responsabilité de l'utilisateur final.
    youtube_max_duration_seconds: int = Field(default=900, ge=1)  # 15 min
    youtube_download_timeout_seconds: int = Field(default=120, ge=1)

    # Durée maximale (en secondes) acceptée pour TOUT fichier audio traité,
    # quelle que soit sa source (upload local ou YouTube) — vérifiée au
    # moment de la normalisation, où la durée réelle devient connue pour les
    # deux cas de façon uniforme (voir acquisition/formats.py pour les
    # vérifications propres à chaque source en amont).
    audio_max_duration_seconds: int = Field(default=1200, ge=1)  # 20 min

    # Délai maximal (en secondes) accordé à un seul appel ffprobe/ffmpeg.
    ffmpeg_timeout_seconds: int = Field(default=120, ge=1)

    # Séparation d'instruments (Demucs, dépendance optionnelle — voir
    # docs/MODELS.md). Désactivée par défaut tant que la bibliothèque n'est
    # pas installée ; voir separation/capabilities.py pour la détection.
    separation_min_available_memory_mb: int = Field(default=1500, ge=1)
    separation_timeout_seconds: int = Field(default=900, ge=1)  # 15 min (CPU)
    separation_allow_model_download: bool = True

    @field_validator("data_dir")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def uploads_dir(self) -> Path:
        """Répertoire de stockage des fichiers audio importés.

        Toujours dérivé de `data_dir`, jamais construit à partir d'une
        entrée utilisateur (voir `acquisition/storage.py`).
        """

        return self.data_dir / "uploads"

    @property
    def youtube_tmp_dir(self) -> Path:
        """Répertoire temporaire contrôlé pour les téléchargements YouTube en
        cours, nettoyé après coup — voir `acquisition/youtube.py`."""

        return self.data_dir / "tmp" / "youtube"


def get_settings() -> Settings:
    """Point d'entrée unique pour récupérer la configuration.

    Pas de cache global ici volontairement : les tests doivent pouvoir
    instancier des `Settings` différentes (via des variables d'environnement
    ou un `.env` de test) sans effet de bord entre les cas de test.
    """

    return Settings()
