"""Configuration centralisée de la journalisation (logging).

Appelé une fois au démarrage de l'application (voir `api/app.py`). Le niveau de
log vient de `Settings.log_level`, jamais lu directement depuis l'environnement
ici pour garder une seule source de vérité (voir `config.py`).
"""

from __future__ import annotations

import logging
import logging.config

from guitarriff.config import Settings


def configure_logging(settings: Settings) -> None:
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": settings.log_level.value,
        },
        "loggers": {
            "guitarriff": {
                "handlers": ["console"],
                "level": settings.log_level.value,
                "propagate": False,
            },
            "uvicorn": {
                "handlers": ["console"],
                "level": settings.log_level.value,
                "propagate": False,
            },
        },
    }
    logging.config.dictConfig(logging_config)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
