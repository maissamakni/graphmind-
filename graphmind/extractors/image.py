"""Extraction pour images.

Sans backend vision configuré : on crée juste un nœud "image" avec ses
métadonnées de base (dimensions), sans jamais halluciner un contenu.
Avec un backend : une légende sémantique est générée et ses entités
mentionnées peuvent être reliées aux symboles de code déjà connus,
exactement comme pour text_doc.py.
"""
from __future__ import annotations

from pathlib import Path

from .. import llm
from ..ids import make_id
from ..schema import Confidence, Edge, ExtractionResult, Modality, Node


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
            make_id(relative_path, "no_caption"),
            "[légende non générée — aucun backend vision sécurisé configuré]",
            Modality.CONCEPT, relative_path,
        ))
        return result

    # NOTE MVP : la génération réelle de légende via un modèle de vision
    # (Claude/GPT-4V/Gemini) suit le même schéma que pdf_doc.py — appel à
    # llm.extract_semantic avec le texte d'une légende pré-générée. Laissé
    # en TODO explicite ici pour rester dans le périmètre du MVP.
    result.nodes.append(Node(
        make_id(relative_path, "caption_todo"),
        f"[légende à générer via backend={backend.name} — non implémenté dans ce MVP]",
        Modality.CONCEPT, relative_path,
    ))
    return result
