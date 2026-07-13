"""Génération d'identifiants stables.

Principe repris de la recherche (build.py de graphify) : la clé de
correspondance la plus fiable pour une entité de code est
(chemin de fichier relatif, nom du symbole) — pas une similarité de texte
floue. C'est ce qui permet une déduplication déterministe.
"""
from __future__ import annotations

import re
import unicodedata


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "x"


def make_id(*parts: str) -> str:
    """Construit un identifiant stable à partir d'une séquence de parties.

    make_id("account/account.py", "Account", "find_by_email")
        -> "account_account_py_account_find_by_email"
    """
    return "_".join(_slug(p) for p in parts if p)


def file_stem_id(relative_path: str) -> str:
    """Identifiant de base pour un fichier, dérivé de son chemin relatif complet
    (pas seulement du nom de fichier) pour éviter les collisions entre deux
    fichiers de même nom dans des dossiers différents."""
    return make_id(relative_path)
