"""Génération d'identifiants stables et correspondance approximative.

Principe : la clé de correspondance la plus fiable pour une entité de code
est (chemin de fichier relatif, nom du symbole) — pas une similarité de
texte floue. C'est ce qui permet une déduplication déterministe.
"""
from __future__ import annotations

import difflib
import re
import unicodedata


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "x"


def make_id(*parts: str) -> str:
    """Construit un identifiant stable à partir d'une séquence de parties."""
    return "_".join(_slug(p) for p in parts if p)


def file_stem_id(relative_path: str) -> str:
    """Identifiant de base pour un fichier, dérivé de son chemin relatif complet."""
    return make_id(relative_path)


def fuzzy_find_symbol(name: str, known_symbols: dict[str, str], threshold: float = 0.85) -> str | None:
    """Cherche une correspondance APPROXIMATIVE (pas exacte) dans les
    symboles de code déjà connus — à utiliser UNIQUEMENT en dernier
    recours, après l'échec d'une correspondance exacte.

    Rattrape une faute de frappe ou une légère variation de nom (ex:
    "email_service" mentionné alors que le vrai symbole est
    "email_sercice"). Retourne None si aucune correspondance ne dépasse le
    seuil, pour ne jamais deviner au hasard. N'utilise aucune dépendance
    supplémentaire (difflib fait partie de la bibliothèque standard)."""
    best_match, best_score = None, 0.0
    for symbol in known_symbols:
        score = difflib.SequenceMatcher(None, name.lower(), symbol.lower()).ratio()
        if score > best_score:
            best_match, best_score = symbol, score
    if best_match is not None and best_score >= threshold:
        return known_symbols[best_match]
    return None
