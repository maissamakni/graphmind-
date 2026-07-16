"""Extraction pour documents texte/Markdown.

Trois niveaux de liaison, du plus certain au plus riche :
1. Titres (imbrication par niveau #/##/###...) — mécanique, EXTRACTED.
2. Mentions `symbole` entre backticks — liaison cross-modale EXACTE vers un
   symbole de code déjà connu, EXTRACTED (correspondance de texte exacte,
   pas une supposition).
3. Extraction sémantique LLM du texte complet (comme pdf_doc.py) — fait
   émerger des CONCEPTS que le texte ne nomme pas forcément avec le nom
   exact du code (ex: "authentification par JWT" plutôt que le nom d'une
   fonction précise), reliés au code connu par simple présence du mot dans
   le concept généré. INFERRED, arbitré par security.py comme pour PDF/image.

C'est ce troisième niveau qui permet des communautés mieux fusionnées entre
code et documentation (comme observé chez graphify), là où les backticks
seuls ne suffisent pas si le README ne les utilise pas.
"""
from __future__ import annotations

import re
from pathlib import Path

from .. import llm
from ..ids import make_id
from ..schema import Confidence, Edge, ExtractionResult, Modality, Node

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_CODE_MENTION_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


def extract_text_doc(
    path: Path, relative_path: str, known_code_symbols: dict[str, str],
    force_local: bool = True,
) -> ExtractionResult:
    """known_code_symbols : {nom_du_symbole: node_id} déjà extraits du code,
    pour permettre la liaison cross-modale doc -> code sans deviner.

    force_local : par défaut True (sécurité maximale) si l'appelant ne
    précise rien — un document texte est traité comme potentiellement
    sensible tant que security.py n'a pas explicitement dit le contraire.
    """
    result = ExtractionResult()
    text = path.read_text(encoding="utf-8", errors="replace")

    file_id = make_id(relative_path)
    result.nodes.append(Node(file_id, path.name, Modality.DOCUMENT, relative_path, "L1"))

    # --- Niveau 1 : titres (mécanique, EXTRACTED) ---
    stack: list[tuple[int, str]] = []  # (niveau, id) pour l'imbrication des titres
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

    # --- Niveau 2 : mentions `symbole` entre backticks (correspondance
    # exacte, EXTRACTED — pas une supposition, le texte cite le nom réel) ---
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
        return result  # comportement inchangé sans backend : niveaux 1+2 seulement

    semantic = llm.extract_semantic(text, backend)
    entity_ids: dict[str, str] = {}
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

        # Liaison cross-modale enrichie : si le concept généré par le LLM
        # contient (en toutes lettres) le nom d'un symbole de code déjà
        # connu, on relie le concept au VRAI nœud de code — même sans
        # backtick dans le texte d'origine. Toujours vers un symbole
        # EXISTANT uniquement, jamais un nœud fantôme inventé.
        words_in_name = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", name))
        for symbol, target_id in known_code_symbols.items():
            if symbol in words_in_name and target_id not in seen_refs:
                seen_refs.add(target_id)
                result.edges.append(Edge(
                    ent_id, target_id, "references", Confidence.INFERRED,
                    relative_path, context="semantic_concept_mention",
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
