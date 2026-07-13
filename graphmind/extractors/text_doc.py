"""Extraction pour documents texte/Markdown.

Point clé (le vrai défi identifié pendant la recherche) : ce module ne se
contente pas d'extraire les titres, il détecte aussi les mentions
explicites d'identifiants de code (entre backticks, ex: `calculate_total`)
et crée une relation `references` vers le nœud de code correspondant s'il
existe déjà dans le graphe — c'est le mécanisme de résolution cross-modale.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..ids import make_id
from ..schema import Confidence, Edge, ExtractionResult, Modality, Node

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_CODE_MENTION_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


def extract_text_doc(path: Path, relative_path: str, known_code_symbols: dict[str, str]) -> ExtractionResult:
    """known_code_symbols : {nom_du_symbole: node_id} déjà extraits du code,
    pour permettre la liaison cross-modale doc -> code sans deviner."""
    result = ExtractionResult()
    text = path.read_text(encoding="utf-8", errors="replace")

    file_id = make_id(relative_path)
    result.nodes.append(Node(file_id, path.name, Modality.DOCUMENT, relative_path, "L1"))

    stack: list[tuple[int, str]] = []  # (niveau, id) pour l'imbrication des titres
    last_pos = 0
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
        last_pos = match.end()

    # Liaison cross-modale : chaque mention `symbole` dans le texte devient
    # une relation "references" vers le nœud de code correspondant, UNIQUEMENT
    # si ce symbole existe déjà (pas de nœud fantôme créé au hasard).
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

    return result
