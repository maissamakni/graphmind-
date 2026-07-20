"""Configuration centralisée du logging.

Sépare LOGS (progression, avertissements — stderr) de RÉSULTAT (réponse
d'une requête, JSON de `status` — stdout), pour un usage en script/CI.
"""
from __future__ import annotations

import logging
import os
import sys

_LOGGER_NAME = "graphmind"


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


def configure_logging(verbosity: int = 0) -> None:
    """verbosity : 0 = INFO (défaut), 1+ = DEBUG, -1 = WARNING seulement.
    GRAPHMIND_LOG_LEVEL a toujours la priorité si définie."""
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return

    env_level = os.environ.get("GRAPHMIND_LOG_LEVEL")
    if env_level:
        level = getattr(logging, env_level.upper(), logging.INFO)
    elif verbosity >= 1:
        level = logging.DEBUG
    elif verbosity <= -1:
        level = logging.WARNING
    else:
        level = logging.INFO

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(
        fmt="[graphmind] %(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
