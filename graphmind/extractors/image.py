"""Extraction pour images.

Deux étapes bien séparées, exactement comme pour pdf_doc.py :
1. Lecture des métadonnées de base (Pillow) — mécanique, gratuite, aucun LLM.
2. Génération d'une légende sémantique via un modèle de VISION (coûteuse,
   arbitrée par security.py) — seule cette étape peut décrire le CONTENU
   visuel de l'image (un schéma d'architecture, une capture d'écran...).

La légende obtenue est ensuite scannée pour des mentions de symboles de code
déjà connus (même principe de liaison cross-modale que text_doc.py), pour
relier une image d'architecture aux vraies fonctions/classes qu'elle illustre.
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

    # Étape 2 — légende sémantique via modèle de vision (arbitrée par sécurité)
    backend = llm.resolve_backend(force_local)
    if backend.name == "none":
        result.nodes.append(Node(
            make_id(relative_path, "no_caption"),
            "[légende non générée — aucun backend vision sécurisé configuré]",
            Modality.CONCEPT, relative_path,
        ))
        return result

    media_type = _MEDIA_TYPES.get(path.suffix.lower(), "image/png")
    try:
        image_bytes = path.read_bytes()
    except OSError:
        return result

    caption = llm.describe_image(image_bytes, media_type, backend)
    if not caption:
        # L'appel a échoué (déjà journalisé par describe_image) — on ne
        # bloque jamais le pipeline, on documente juste l'absence de résultat.
        result.nodes.append(Node(
            make_id(relative_path, "caption_failed"),
            f"[échec de la génération de légende via {backend.name}]",
            Modality.CONCEPT, relative_path,
        ))
        return result

    confidence = Confidence.INFERRED  # une légende de VLM est une interprétation, jamais une certitude
    caption_id = make_id(relative_path, "caption")
    result.nodes.append(Node(caption_id, caption[:200], Modality.IMAGE, relative_path,
                              metadata={"backend": backend.name, "full_caption": caption}))
    result.edges.append(Edge(file_id, caption_id, "contains", Confidence.EXTRACTED, relative_path))

    # Liaison cross-modale : si la légende mentionne un symbole de code déjà
    # connu (ex: "montre la fonction find_by_email"), relier l'image au VRAI
    # nœud de code — jamais de nœud fantôme créé pour un nom non reconnu.
    seen_refs: set[str] = set()
    words_in_caption = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", caption))
    for symbol, target_id in known_code_symbols.items():
        if symbol in words_in_caption and target_id not in seen_refs:
            seen_refs.add(target_id)
            result.edges.append(Edge(
                caption_id, target_id, "illustrates", confidence,
                relative_path, context="vision_caption_mention",
            ))

    return result
