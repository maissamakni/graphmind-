"""Configuration centralisée du projet, via un fichier `graphmind.toml`
optionnel à la racine du projet analysé. Utilise tomllib (bibliothèque
standard Python 3.11+) — aucune dépendance supplémentaire.

Sans fichier `graphmind.toml` présent, toutes les valeurs par défaut
s'appliquent exactement comme avant — ce module est strictement additif.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from .logging_config import get_logger

log = get_logger()

_CONFIG_FILENAME = "graphmind.toml"

_EXAMPLE_CONFIG = """\
# graphmind.toml — configuration optionnelle, à placer à la racine du
# projet analysé (pas dans le dossier de graphmind lui-même).
# Toutes les sections sont optionnelles ; une valeur absente garde son
# comportement par défaut.

[security]
# Mots-clés supplémentaires (en plus de la liste par défaut : secret,
# confidentiel, private, credentials, internal, rh...) qui, s'ils
# apparaissent dans le chemin d'un fichier, forcent un traitement local.
extra_sensitive_dirs = ["brevet", "acquisition"]

[detect]
# Dossiers supplémentaires à ignorer complètement (en plus de .git,
# node_modules, __pycache__, .venv...).
extra_ignore_dirs = ["vendor", "generated"]

[cluster]
# Résolution du clustering Leiden — plus bas = communautés plus grandes
# et moins nombreuses. Valeurs par défaut : 0.6 (fin) / 0.15 (large).
fine_resolution = 0.6
coarse_resolution = 0.15

[llm]
# Remplace le modèle par défaut choisi automatiquement pour chaque backend.
# groq_model = "openai/gpt-oss-120b"
# groq_vision_model = "meta-llama/llama-4-scout-17b-16e-instruct"
"""


@dataclass
class GraphmindConfig:
    extra_sensitive_dirs: list[str] = field(default_factory=list)
    extra_ignore_dirs: list[str] = field(default_factory=list)
    fine_resolution: float = 0.6
    coarse_resolution: float = 0.15
    groq_model: str | None = None
    groq_vision_model: str | None = None


def load_config(root: Path) -> GraphmindConfig:
    """Cherche `graphmind.toml` à la racine du projet analysé et le charge.
    Retourne une configuration par défaut si le fichier est absent — et
    journalise un avertissement (sans jamais bloquer) s'il est mal formé."""
    config_path = Path(root) / _CONFIG_FILENAME
    if not config_path.is_file():
        return GraphmindConfig()

    try:
        if sys.version_info >= (3, 11):
            import tomllib
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
        else:  # pragma: no cover
            import tomli as tomllib
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
    except Exception as exc:
        log.warning(f"impossible de lire {config_path} ({exc}) — configuration par défaut utilisée.")
        return GraphmindConfig()

    security = data.get("security", {})
    detect = data.get("detect", {})
    cluster_cfg = data.get("cluster", {})
    llm_cfg = data.get("llm", {})

    log.info(f"configuration chargée depuis {config_path}")

    return GraphmindConfig(
        extra_sensitive_dirs=list(security.get("extra_sensitive_dirs", [])),
        extra_ignore_dirs=list(detect.get("extra_ignore_dirs", [])),
        fine_resolution=float(cluster_cfg.get("fine_resolution", 0.6)),
        coarse_resolution=float(cluster_cfg.get("coarse_resolution", 0.15)),
        groq_model=llm_cfg.get("groq_model"),
        groq_vision_model=llm_cfg.get("groq_vision_model"),
    )


def write_example_config(destination: Path) -> None:
    destination.write_text(_EXAMPLE_CONFIG, encoding="utf-8")
