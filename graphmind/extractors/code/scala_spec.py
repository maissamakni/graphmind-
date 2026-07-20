"""Spécification Scala — node types vérifiés empiriquement, tous les
champs nommés fonctionnent correctement."""
from __future__ import annotations

from .base import LanguageSpec


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_scala as tsscala
    return Parser(Language(tsscala.language()))


def _extract_call_name(node, text) -> str | None:
    fn_node = node.children[0] if node.children else None
    if fn_node is None:
        return None
    if fn_node.type == "identifier":
        return text(fn_node)
    if fn_node.type == "field_expression":
        field_node = fn_node.child_by_field_name("field")
        if field_node is not None:
            return text(field_node)
    return None


def _extract_import(node, text) -> tuple[str, str] | None:
    return ("imports", text(node).replace("import", "", 1).strip())


SCALA_SPEC = LanguageSpec(
    name="scala",
    parser_factory=_get_parser,
    function_node_types=frozenset({"function_definition"}),
    class_node_types=frozenset({"class_definition"}),
    call_node_types=frozenset({"call_expression"}),
    import_node_types=frozenset({"import_declaration"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
)
