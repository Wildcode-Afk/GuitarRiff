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

    data_dir: Path = Path("./data")

    # Décision D6 : concurrence prudente par défaut (empreinte mémoire de
    # TensorFlow/PyTorch sur machine modeste). Ajustable une fois le
    # matériel cible mieux connu.
    job_concurrency: int = Field(default=1, ge=1)

    # Décision Q1 : yt-dlp est prévu, mais pas encore implémenté à ce stade
    # (squelette uniquement — aucune fonctionnalité audio à cette étape).
    ytdlp_enabled: bool = True

    @field_validator("data_dir")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()


def get_settings() -> Settings:
    """Point d'entrée unique pour récupérer la configuration.

    Pas de cache global ici volontairement : les tests doivent pouvoir
    instancier des `Settings` différentes (via des variables d'environnement
    ou un `.env` de test) sans effet de bord entre les cas de test.
    """

    return Settings()
