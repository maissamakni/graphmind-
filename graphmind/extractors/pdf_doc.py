"""Extraction pour fichiers PDF.

Deux étapes bien séparées (cf. discussion sur extract_pdf_text) :
1. pypdf extrait le texte brut — mécanique, gratuit, aucun LLM.
2. Le texte est ensuite envoyé à un backend LLM (choisi par security.py)
   pour en tirer des entités/relations structurées — seule cette étape
   coûte des tokens et peut être locale ou externe.
"""
from __future__ import annotations

from pathlib import Path

from .. import llm
from ..ids import make_id
from ..schema import Confidence, Edge, ExtractionResult, Modality, Node


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def extract_pdf(path: Path, relative_path: str, force_local: bool) -> ExtractionResult:
    result = ExtractionResult()
    file_id = make_id(relative_path)
    result.nodes.append(Node(file_id, path.name, Modality.PDF, relative_path, "L1"))

    text = _extract_pdf_text(path)
    if not text.strip():
        return result

    backend = llm.resolve_backend(force_local)
    semantic = llm.extract_semantic(text, backend)

    confidence = Confidence.INFERRED if backend.name != "none" else Confidence.AMBIGUOUS
    for entity in semantic.get("entities", []):
        name = entity.get("name")
        if not name:
            continue
        ent_id = make_id(relative_path, name)
        result.nodes.append(Node(
            ent_id, name, Modality.PDF, relative_path, None,
            metadata={"entity_type": entity.get("type", "concept"), "backend": backend.name},
        ))
        result.edges.append(Edge(file_id, ent_id, "contains", confidence, relative_path))

    for rel in semantic.get("relations", []):
        src_name, tgt_name = rel.get("source"), rel.get("target")
        if not src_name or not tgt_name:
            continue
        result.edges.append(Edge(
            make_id(relative_path, src_name), make_id(relative_path, tgt_name),
            rel.get("relation", "references"), confidence, relative_path,
        ))

    if backend.name == "none":
        result.nodes.append(Node(
            make_id(relative_path, "extraction_incomplete"),
            "[extraction sémantique non effectuée — aucun backend sécurisé configuré]",
            Modality.CONCEPT, relative_path,
            metadata={"reason": semantic.get("_skipped", "no backend")},
        ))

    return result
