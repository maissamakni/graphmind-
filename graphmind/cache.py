"""Cache d'extraction — permet d'ajouter un nouveau fichier sans
ré-extraire tout le reste du projet. Ne met JAMAIS en cache un échec
d'extraction (extraction_incomplete), pour permettre une nouvelle
tentative automatique après correction d'un problème."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .schema import Confidence, Edge, ExtractionResult, Modality, Node

_CACHE_FILENAME = ".graphmind-cache.json"


def _file_hash(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def load_cache(out_dir: Path) -> dict:
    cache_path = out_dir / _CACHE_FILENAME
    if not cache_path.is_file():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(out_dir: Path, cache: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / _CACHE_FILENAME).write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def get_cached_result(cache: dict, path: Path, relative_path: str) -> ExtractionResult | None:
    """Reconstruit les enums (Modality, Confidence) depuis le texte stocké,
    sinon node.modality.value planterait plus tard (ce serait une simple chaîne)."""
    entry = cache.get(relative_path)
    if entry is None:
        return None
    if entry.get("hash") != _file_hash(path):
        return None

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
    return ExtractionResult(
        nodes=nodes, edges=edges,
        raw_calls=list(data.get("raw_calls", [])),
        raw_imports=list(data.get("raw_imports", [])),
    )


def store_result(cache: dict, path: Path, relative_path: str, result: ExtractionResult) -> None:
    """N'enregistre RIEN si result.extraction_incomplete est True — un échec
    ponctuel ne doit jamais rester bloqué indéfiniment en cache."""
    if result.extraction_incomplete:
        cache.pop(relative_path, None)
        return
    cache[relative_path] = {
        "hash": _file_hash(path),
        "result": {
            "nodes": [n.to_dict() for n in result.nodes],
            "edges": [e.to_dict() for e in result.edges],
            "raw_calls": result.raw_calls,
            "raw_imports": result.raw_imports,
        },
    }


def prune_deleted_files(cache: dict, current_relative_paths: set[str]) -> None:
    for relative_path in list(cache.keys()):
        if relative_path not in current_relative_paths:
            del cache[relative_path]


def check_status(cache: dict, files: list[tuple[Path, str]]) -> dict:
    """Vérifie SANS RIEN EXTRAIRE si le projet a changé — coût quasi nul."""
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
