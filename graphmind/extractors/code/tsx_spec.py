"""Spécification TSX (TypeScript + JSX) — mêmes node types que
JavaScript/TypeScript (vérifié empiriquement), grammaire dédiée
tree_sitter_typescript.language_tsx()."""
from __future__ import annotations

from .base import LanguageSpec
from .javascript_spec import _extract_call_name, _extract_import


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_typescript as tsts
    return Parser(Language(tsts.language_tsx()))


TSX_SPEC = LanguageSpec(
    name="tsx",
    parser_factory=_get_parser,
    function_node_types=frozenset({"function_declaration", "method_definition"}),
    class_node_types=frozenset({"class_declaration"}),
    call_node_types=frozenset({"call_expression"}),
    import_node_types=frozenset({"import_statement"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
)
