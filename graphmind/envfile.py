"""Chargement d'un fichier .env — sans dépendance externe."""
from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(start_dir: Path | None = None) -> None:
    """Cherche un fichier .env en remontant depuis start_dir (ou le
    répertoire courant), et charge ses variables dans os.environ — sans
    écraser une variable déjà présente."""
    current = Path(start_dir or os.getcwd()).resolve()
    for directory in [current, *current.parents]:
        env_path = directory / ".env"
        if env_path.is_file():
            _apply_env_file(env_path)
            return


def _apply_env_file(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
