"""Extraction pour documents texte/Markdown.

Trois niveaux de liaison, du plus certain au plus riche :
1. Titres — mécanique, EXTRACTED.
2. Mentions `symbole` entre backticks — correspondance exacte, EXTRACTED.
3. Extraction sémantique LLM du texte complet — INFERRED, avec liaison
   cross-modale à trois niveaux : exacte, approximative (fuzzy), puis
   sémantique GROUPÉE (un seul appel LLM pour tous les concepts non
   résolus de ce fichier, au lieu d'un appel par concept).
"""
from __future__ import annotations

import re
from pathlib import Path

from .. import llm
from ..ids import fuzzy_find_symbol, make_id
from ..schema import Confidence, Edge, ExtractionResult, Modality, Node

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_CODE_MENTION_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


def extract_text_doc(
    path: Path, relative_path: str, known_code_symbols: dict[str, str],
    force_local: bool = True,
) -> ExtractionResult:
    result = ExtractionResult()
    text = path.read_text(encoding="utf-8", errors="replace")

    file_id = make_id(relative_path)
    result.nodes.append(Node(file_id, path.name, Modality.DOCUMENT, relative_path, "L1"))

    # --- Niveau 1 : titres ---
    stack: list[tuple[int, str]] = []
    for match in _HEADING_RE.finditer(text):
        level = len(match.group(1))
        title = match.group(2).strip()
        line = text.count("\n", 0, match.start()) + 1
        h_id = make_id(relative_path, title, str(line))
        result.nodes.append(Node(h_id, title, Modality.DOCUMENT, relative_path, f"L{line}"))

        while stack and stack[-1][0] >= level:
            stack.pop()
        parent_id = stack[-1][1] if stack else file_id
        result.edges.append(Edge(parent_id, h_id, "contains", Confidence.EXTRACTED, relative_path, f"L{line}"))
        stack.append((level, h_id))

    # --- Niveau 2 : mentions `symbole` entre backticks ---
    seen_refs: set[str] = set()
    for match in _CODE_MENTION_RE.finditer(text):
        symbol = match.group(1)
        target_id = known_code_symbols.get(symbol)
        if target_id is None or target_id in seen_refs:
            continue
        seen_refs.add(target_id)
        line = text.count("\n", 0, match.start()) + 1
        result.edges.append(Edge(
            file_id, target_id, "describes", Confidence.EXTRACTED,
            relative_path, f"L{line}", context="backtick_mention",
        ))

    # --- Niveau 3 : extraction sémantique LLM du texte complet (INFERRED) ---
    backend = llm.resolve_backend(force_local)
    if backend.name == "none":
        return result

    semantic = llm.extract_semantic(text, backend)
    entity_ids: dict[str, str] = {}
    pending_semantic: list[tuple[str, str]] = []  # (ent_id, name) à résoudre en bloc

    for entity in semantic.get("entities", []):
        name = entity.get("name")
        if not name:
            continue
        ent_id = make_id(relative_path, "concept", name)
        entity_ids[name] = ent_id
        result.nodes.append(Node(
            ent_id, name, Modality.CONCEPT, relative_path,
            metadata={"entity_type": entity.get("type", "concept"), "backend": backend.name},
        ))
        result.edges.append(Edge(file_id, ent_id, "contains", Confidence.INFERRED, relative_path))

        words_in_name = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", name))
        exact_match_found = False
        for symbol, target_id in known_code_symbols.items():
            if symbol in words_in_name and target_id not in seen_refs:
                exact_match_found = True
                seen_refs.add(target_id)
                result.edges.append(Edge(
                    ent_id, target_id, "references", Confidence.INFERRED,
                    relative_path, context="semantic_concept_mention",
                ))

        if not exact_match_found:
            fuzzy_target_id = fuzzy_find_symbol(name, known_code_symbols)
            if fuzzy_target_id is not None and fuzzy_target_id not in seen_refs:
                seen_refs.add(fuzzy_target_id)
                result.edges.append(Edge(
                    ent_id, fuzzy_target_id, "references", Confidence.AMBIGUOUS,
                    relative_path, context="fuzzy_concept_mention",
                ))
            elif known_code_symbols:
                # Ni exact ni approximatif : on met de côté pour un appel
                # LLM GROUPÉ (une seule requête pour tous les concepts non
                # résolus de ce fichier), au lieu d'un appel par concept.
                pending_semantic.append((ent_id, name))

    # Résolution groupée : UN SEUL appel LLM pour tous les concepts en
    # attente de ce fichier, au lieu d'un appel par concept.
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
                    relative_path, context="semantic_llm_link_batch",
                ))

    for rel in semantic.get("relations", []):
        src_name, tgt_name = rel.get("source"), rel.get("target")
        src_id = entity_ids.get(src_name)
        tgt_id = entity_ids.get(tgt_name)
        if src_id and tgt_id:
            result.edges.append(Edge(
                src_id, tgt_id, rel.get("relation", "references"),
                Confidence.INFERRED, relative_path,
            ))

    return result
