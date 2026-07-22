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


def normalize_identifier(name: str) -> str:
    """Ramène un identifiant à une forme canonique indépendante de sa
    convention de nommage (camelCase, PascalCase, snake_case, kebab-case)
    — "checkPassword", "CheckPassword" et "check_password" se ramènent
    tous à "check_password". Ce n'est PAS une supposition approximative
    comme fuzzy_find_symbol : deux identifiants qui ne diffèrent QUE par
    leur convention d'écriture désignent authentiquement le MÊME concept
    (cas réel : une documentation en snake_case décrivant une méthode Java
    en camelCase) — la correspondance normalisée reste donc aussi fiable
    qu'une correspondance exacte, pas un niveau de confiance dégradé."""
    # Insère un underscore avant chaque majuscule qui suit une minuscule
    # ou un chiffre (frontière camelCase -> snake_case), puis uniformise.
    with_boundaries = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    lowered = with_boundaries.lower()
    return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")


def build_normalized_lookup(known_symbols: dict[str, str]) -> dict[str, str]:
    """Construit une table {forme_normalisée: target_id} à partir d'une
    table {nom_de_symbole: target_id} — pour une résolution cross-modale
    insensible à la convention de nommage (cf. normalize_identifier).
    En cas de collision (deux symboles distincts partagent la même forme
    normalisée — rare), garde le premier rencontré plutôt que de deviner."""
    lookup: dict[str, str] = {}
    for symbol, target_id in known_symbols.items():
        normalized = normalize_identifier(symbol)
        if normalized not in lookup:
            lookup[normalized] = target_id
    return lookup
