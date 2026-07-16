"""Extraction pour images.

Deux étapes bien séparées, exactement comme pour pdf_doc.py et text_doc.py :
1. Lecture des métadonnées de base (Pillow) — mécanique, gratuite, aucun LLM.
2. Extraction STRUCTURÉE (entités + relations) via un modèle de VISION —
   pas une simple légende en prose : si l'image contient du code (capture
   d'écran), le modèle est explicitement invité à le LIRE et à en extraire
   les vraies fonctions/relations, exactement comme graphify le fait
   (observé concrètement : une capture d'écran de code Python affichant
   process_payment() -> charge()/generate_invoice() produit un vrai nœud
   process_payment relié par des relations "calls" aux fonctions réelles).

Les entités extraites sont ensuite reliées aux symboles de code déjà connus
par correspondance de nom exacte (même principe que text_doc.py), sans
jamais créer de nœud fantôme pour un nom non reconnu.
"""
from __future__ import annotations

import re
from pathlib import Path

from .. import llm
from ..ids import make_id
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

    # Étape 1 — métadonnées de base (jamais de LLM à ce stade)
    metadata: dict = {}
    try:
        from PIL import Image
        with Image.open(path) as img:
            metadata = {"width": img.width, "height": img.height, "format": img.format}
    except Exception:
        pass
    result.nodes.append(Node(file_id, path.name, Modality.IMAGE, relative_path, None, metadata=metadata))

    # Étape 2 — extraction structurée via modèle de vision (arbitrée par sécurité)
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
        # L'appel a échoué ou n'a rien trouvé (déjà journalisé côté llm.py
        # en cas d'échec réel) — on ne bloque jamais le pipeline, mais on
        # NE MET JAMAIS CE RÉSULTAT EN CACHE : un échec temporaire (clé
        # invalide, modèle indisponible...) ne doit pas rester bloqué
        # indéfiniment après correction du problème.
        result.nodes.append(Node(
            make_id(relative_path, "extraction_failed"),
            f"[aucune entité extraite via {backend.name} — voir les avertissements]",
            Modality.CONCEPT, relative_path,
        ))
        result.extraction_incomplete = True
        return result

    confidence = Confidence.INFERRED  # une extraction de VLM est une interprétation, jamais une certitude
    entity_ids: dict[str, str] = {}
    seen_refs: set[str] = set()

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

        # Liaison cross-modale : si l'entité extraite CORRESPOND EXACTEMENT à
        # un symbole de code déjà connu (ex: "charge" existe vraiment dans
        # stripe_adapter.py), on relie l'entité au VRAI nœud de code —
        # jamais un nœud fantôme pour un nom inventé ou non reconnu.
        target_id = known_code_symbols.get(name)
        if target_id is not None and target_id not in seen_refs:
            seen_refs.add(target_id)
            result.edges.append(Edge(
                ent_id, target_id, "references", confidence,
                relative_path, context="vision_exact_match",
            ))

    # Relations entre entités extraites (ex: process_payment --calls--> charge)
    # — si une des deux extrémités correspond à un symbole de code déjà
    # connu, on relie DIRECTEMENT vers le vrai nœud plutôt que vers le
    # concept image, pour que la relation soit exploitable par la requête.
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
