"""Spécification Swift — node types vérifiés empiriquement."""
from __future__ import annotations

from .base import LanguageSpec


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_swift as tsswift
    return Parser(Language(tsswift.language()))


def _extract_call_name(node, text) -> str | None:
    # call_expression -> premier enfant nommé : soit un identifiant simple
    # (appel local), soit une navigation_expression dont le champ
    # navigation_suffix.suffix donne le nom de méthode.
    named_children = [c for c in node.children if c.is_named]
    if not named_children:
        return None
    first = named_children[0]
    if first.type == "simple_identifier":
        return text(first)
    if first.type == "navigation_expression":
        for child in first.children:
            if child.type == "navigation_suffix":
                suffix_node = child.child_by_field_name("suffix")
                if suffix_node is not None:
                    return text(suffix_node)
    return None


def _extract_import(node, text) -> tuple[str, str] | None:
    for child in node.children:
        if child.type == "identifier":
            return ("imports", text(child).strip())
    return None


SWIFT_SPEC = LanguageSpec(
    name="swift",
    parser_factory=_get_parser,
    function_node_types=frozenset({"function_declaration"}),
    class_node_types=frozenset({"class_declaration"}),
    call_node_types=frozenset({"call_expression"}),
    import_node_types=frozenset({"import_declaration"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
)
