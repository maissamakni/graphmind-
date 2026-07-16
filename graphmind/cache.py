"""Cache d'extraction — permet d'ajouter un nouveau fichier (code ou
document) sans ré-extraire tout le reste du projet.

Principe (repris de graphify) : chaque fichier est identifié par une
empreinte (hash) de son CONTENU, pas par sa date de modification — un
fichier renommé puis renommé à nouveau, ou dont seule la date change sans
que le contenu bouge, ne déclenche pas de ré-extraction inutile.

Le cache est un simple fichier JSON, stocké dans le dossier de sortie
(<out_dir>/.graphmind-cache.json) — pas de base de données, cohérent avec
le principe d'architecture compacte.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .schema import Confidence, Edge, ExtractionResult, Modality, Node

_CACHE_FILENAME = ".graphmind-cache.json"


def _file_hash(path: Path) -> str:
    """Empreinte du CONTENU du fichier (pas de sa date) — un fichier identique
    en octets produit toujours la même empreinte, peu importe son historique."""
    return hashlib.sha1(path.read_bytes()).hexdigest()


def load_cache(out_dir: Path) -> dict:
    """Charge le cache existant, ou un cache vide si le dossier de sortie
    n'existe pas encore (premier `build` sur ce projet)."""
    cache_path = out_dir / _CACHE_FILENAME
    if not cache_path.is_file():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}  # cache corrompu : on repart d'un cache vide, jamais une erreur bloquante


def save_cache(out_dir: Path, cache: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / _CACHE_FILENAME).write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def get_cached_result(cache: dict, path: Path, relative_path: str) -> ExtractionResult | None:
    """Retourne l'extraction déjà en cache pour ce fichier SI son contenu n'a
    pas changé depuis la dernière fois — sinon None (il faut ré-extraire).

    Node.to_dict()/Edge.to_dict() convertissent les enums (Modality,
    Confidence) en simples chaînes de texte pour pouvoir les écrire en JSON —
    ici on fait l'opération INVERSE, en reconstruisant les vrais objets
    Modality/Confidence à partir de ces chaînes, pas juste des dicts bruts
    (sinon node.modality.value planterait plus tard dans le pipeline, puisque
    modality serait alors une simple chaîne sans l'attribut .value).
    """
    entry = cache.get(relative_path)
    if entry is None:
        return None
    if entry.get("hash") != _file_hash(path):
        return None  # le fichier a changé depuis la dernière extraction

    data = entry["result"]
    nodes = []
    for n in data["nodes"]:
        n = dict(n)
        n["modality"] = Modality(n["modality"])
        nodes.append(Node(**n))
    edges = []
    for e in data["edges"]:
        e = dict(e)
        e["confidence"] = Confidence(e["confidence"])
        edges.append(Edge(**e))
    return ExtractionResult(nodes=nodes, edges=edges, raw_calls=list(data.get("raw_calls", [])))


def store_result(cache: dict, path: Path, relative_path: str, result: ExtractionResult) -> None:
    """Enregistre le résultat d'extraction d'un fichier, avec l'empreinte de
    son contenu actuel, pour une réutilisation lors du prochain `build`.
    to_dict() convertit déjà les enums en texte — rien à faire de plus ici.

    IMPORTANT : si result.extraction_incomplete est True (échec du backend,
    aucun backend disponible...), on N'ENREGISTRE RIEN dans le cache — sinon
    un échec ponctuel (clé invalide, modèle temporairement indisponible,
    bug depuis corrigé...) resterait bloqué indéfiniment, puisque le fichier
    source lui-même n'a pas changé et continuerait à "matcher" le cache à
    chaque build futur, empêchant toute nouvelle tentative.
    """
    if result.extraction_incomplete:
        cache.pop(relative_path, None)  # retire aussi une éventuelle ancienne entrée réussie périmée
        return
    cache[relative_path] = {
        "hash": _file_hash(path),
        "result": {
            "nodes": [n.to_dict() for n in result.nodes],
            "edges": [e.to_dict() for e in result.edges],
            "raw_calls": result.raw_calls,
        },
    }


def prune_deleted_files(cache: dict, current_relative_paths: set[str]) -> None:
    """Retire du cache les fichiers qui n'existent plus dans le projet —
    sans ça, un fichier supprimé continuerait à apparaître indéfiniment
    dans le graphe reconstruit."""
    for relative_path in list(cache.keys()):
        if relative_path not in current_relative_paths:
            del cache[relative_path]


def check_status(cache: dict, files: list[tuple[Path, str]]) -> dict:
    """Vérifie SANS RIEN EXTRAIRE si le projet a changé depuis le dernier
    build — juste des empreintes de fichiers, quasi instantané et gratuit.

    files : liste de (chemin_absolu, chemin_relatif) pour chaque fichier
    actuellement détecté dans le projet.

    Sert à décider si `graphmind build` vaut la peine d'être relancé, sans
    même lancer le pipeline complet pour le découvrir — utile pour un
    assistant IA qui orchestre plusieurs commandes et veut éviter tout
    travail (et donc tout coût, y compris son propre coût de raisonnement)
    inutile.
    """
    new_files, changed_files, unchanged_files = [], [], []
    for abs_path, rel_path in files:
        entry = cache.get(rel_path)
        if entry is None:
            new_files.append(rel_path)
        elif entry.get("hash") != _file_hash(abs_path):
            changed_files.append(rel_path)
        else:
            unchanged_files.append(rel_path)

    current_rel_paths = {rel for _, rel in files}
    deleted_files = [rel for rel in cache if rel not in current_rel_paths]

    return {
        "new": new_files,
        "changed": changed_files,
        "unchanged": unchanged_files,
        "deleted": deleted_files,
        "needs_rebuild": bool(new_files or changed_files or deleted_files),
    }
