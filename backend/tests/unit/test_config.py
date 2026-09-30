"""Vérifie que la configuration se charge correctement et respecte les
variables d'environnement, sans dépendre d'un vrai fichier .env."""

from __future__ import annotations

from guitarriff.config import AppEnv, LogLevel, Settings


def test_default_settings_match_documented_decisions(monkeypatch) -> None:
    """Les valeurs par défaut doivent correspondre aux décisions prises dans
    docs/TECHNICAL_DECISIONS.md (D6 : concurrence = 1 ; Q1 : yt-dlp prévu)."""
    monkeypatch.delenv("JOB_CONCURRENCY", raising=False)
    monkeypatch.delenv("YTDLP_ENABLED", raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_env == AppEnv.development
    assert settings.log_level == LogLevel.INFO
    assert settings.job_concurrency == 1
    assert settings.ytdlp_enabled is True


def test_settings_read_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("JOB_CONCURRENCY", "3")
    monkeypatch.setenv("YTDLP_ENABLED", "false")

    settings = Settings(_env_file=None)

    assert settings.app_env == AppEnv.production
    assert settings.log_level == LogLevel.DEBUG
    assert settings.job_concurrency == 3
    assert settings.ytdlp_enabled is False


def test_job_concurrency_must_be_at_least_one() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, job_concurrency=0)


def test_data_dir_is_resolved_to_absolute_path(monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", "./some/relative/dir")
    settings = Settings(_env_file=None)
    assert settings.data_dir.is_absolute()


def test_cors_origins_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.cors_origins_list == ["http://localhost:5173"]


def test_cors_origins_parsed_from_comma_separated_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS", "http://localhost:5173, http://127.0.0.1:5173,http://example.com"
    )
    settings = Settings(_env_file=None)
    assert settings.cors_origins_list == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://example.com",
    ]
