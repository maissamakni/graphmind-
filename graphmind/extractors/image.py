"""Extraction pour images.

Extraction STRUCTURÉE (entités + relations) via un modèle de vision — pas
une simple légende : si l'image contient du code (capture d'écran), le
modèle est invité à le LIRE et en extraire les vraies fonctions/relations.
Liaison cross-modale à trois niveaux (exact, fuzzy, sémantique groupé)."""
from __future__ import annotations

import re
from pathlib import Path

from .. import llm
from ..ids import fuzzy_find_symbol, make_id
from ..schema import Confidence, Edge, ExtractionResult, Modality, Node

_MEDIA_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif",
}


def extract_image(
    path: Path, relative_path: str, force_local: bool,
    known_code_symbols: dict[str, str],
) -> ExtractionResult:
    result = ExtractionResult()
    file_id = make_id(relative_path)

    metadata: dict = {}
    try:
        from PIL import Image
        with Image.open(path) as img:
            metadata = {"width": img.width, "height": img.height, "format": img.format}
    except Exception:
        pass
    result.nodes.append(Node(file_id, path.name, Modality.IMAGE, relative_path, None, metadata=metadata))

    backend = llm.resolve_backend(force_local)
    if backend.name == "none":
        result.nodes.append(Node(
            make_id(relative_path, "no_extraction"),
            "[extraction non effectuée — aucun backend vision sécurisé configuré]",
            Modality.CONCEPT, relative_path,
        ))
        result.extraction_incomplete = True
        return result

    media_type = _MEDIA_TYPES.get(path.suffix.lower(), "image/png")
    try:
        image_bytes = path.read_bytes()
    except OSError:
        return result

    semantic = llm.extract_semantic_from_image(image_bytes, media_type, backend)
    entities = semantic.get("entities", [])
    if not entities:
        result.nodes.append(Node(
            make_id(relative_path, "extraction_failed"),
            f"[aucune entité extraite via {backend.name} — voir les avertissements]",
            Modality.CONCEPT, relative_path,
        ))
        result.extraction_incomplete = True
        return result

    confidence = Confidence.INFERRED
    entity_ids: dict[str, str] = {}
    seen_refs: set[str] = set()
    pending_semantic: list[tuple[str, str]] = []

    for entity in entities:
        name = entity.get("name")
        if not name:
            continue
        ent_id = make_id(relative_path, "concept", name)
        entity_ids[name] = ent_id
        result.nodes.append(Node(
            ent_id, name, Modality.IMAGE, relative_path,
            metadata={"entity_type": entity.get("type", "concept"), "backend": backend.name},
        ))
        result.edges.append(Edge(file_id, ent_id, "illustrates", confidence, relative_path))

        target_id = known_code_symbols.get(name)
        if target_id is not None and target_id not in seen_refs:
            seen_refs.add(target_id)
            result.edges.append(Edge(
                ent_id, target_id, "references", confidence,
                relative_path, context="vision_exact_match",
            ))
        elif target_id is None:
            fuzzy_target_id = fuzzy_find_symbol(name, known_code_symbols)
            if fuzzy_target_id is not None and fuzzy_target_id not in seen_refs:
                seen_refs.add(fuzzy_target_id)
                result.edges.append(Edge(
                    ent_id, fuzzy_target_id, "references", Confidence.AMBIGUOUS,
                    relative_path, context="vision_fuzzy_match",
                ))
            elif known_code_symbols:
                pending_semantic.append((ent_id, name))

    if pending_semantic:
        names_to_resolve = [name for _, name in pending_semantic]
        resolved = llm.semantic_link_batch(names_to_resolve, list(known_code_symbols.keys()), backend)
        for ent_id, name in pending_semantic:
            symbol = resolved.get(name)
            if symbol is None:
                continue
            target_id = known_code_symbols[symbol]
            if target_id not in seen_refs:
                seen_refs.add(target_id)
                result.edges.append(Edge(
                    ent_id, target_id, "references", Confidence.AMBIGUOUS,
                    relative_path, context="vision_semantic_llm_link_batch",
                ))

    for rel in semantic.get("relations", []):
        src_name, tgt_name = rel.get("source"), rel.get("target")
        if not src_name or not tgt_name:
            continue
        src_id = known_code_symbols.get(src_name) or entity_ids.get(src_name)
        tgt_id = known_code_symbols.get(tgt_name) or entity_ids.get(tgt_name)
        if src_id and tgt_id:
            result.edges.append(Edge(
                src_id, tgt_id, rel.get("relation", "references"),
                confidence, relative_path,
            ))

    return result
