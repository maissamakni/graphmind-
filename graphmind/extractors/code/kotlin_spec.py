"""Spécification Kotlin — call_expression n'expose pas de champ nommé
fiable pour la fonction appelée (vérifié empiriquement : le champ
"function" retourne None) ; extraction positionnelle nécessaire."""
from __future__ import annotations

from .base import LanguageSpec


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_kotlin as tskotlin
    return Parser(Language(tskotlin.language()))


def _extract_call_name(node, text) -> str | None:
    if not node.children:
        return None
    first = node.children[0]
    if first.type == "identifier":
        return text(first)
    if first.type == "navigation_expression":
        named_children = [c for c in first.children if c.is_named]
        if named_children:
            return text(named_children[-1])  # dernier identifiant = nom de méthode (x.y.verify -> "verify")
    return None


def _extract_import(node, text) -> tuple[str, str] | None:
    for child in node.children:
        if child.type == "qualified_identifier" or child.type == "identifier":
            return ("imports", text(child).strip())
    return None


KOTLIN_SPEC = LanguageSpec(
    name="kotlin",
    parser_factory=_get_parser,
    function_node_types=frozenset({"function_declaration"}),
    class_node_types=frozenset({"class_declaration"}),
    call_node_types=frozenset({"call_expression"}),
    import_node_types=frozenset({"import"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
)
