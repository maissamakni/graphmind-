"""Spécification JavaScript — sert aussi pour .jsx (la grammaire JS gère
nativement la syntaxe JSX, vérifié empiriquement : aucune erreur de parsing
sur du JSX avec cette grammaire)."""
from __future__ import annotations

from .base import LanguageSpec


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_javascript as tsjs
    return Parser(Language(tsjs.language()))


def _extract_call_name(node, text) -> str | None:
    fn_node = node.child_by_field_name("function")
    if fn_node is None:
        return None
    if fn_node.type == "identifier":
        return text(fn_node)
    if fn_node.type == "member_expression":
        prop_node = fn_node.child_by_field_name("property")
        if prop_node is not None:
            return text(prop_node)
    return None


def _extract_import(node, text) -> tuple[str, str] | None:
    source_node = node.child_by_field_name("source")
    if source_node is None:
        return None
    return ("imports", text(source_node).strip("'\""))


JAVASCRIPT_SPEC = LanguageSpec(
    name="javascript",
    parser_factory=_get_parser,
    function_node_types=frozenset({"function_declaration", "method_definition"}),
    class_node_types=frozenset({"class_declaration"}),
    call_node_types=frozenset({"call_expression"}),
    import_node_types=frozenset({"import_statement"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
)
