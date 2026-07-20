"""Spécification Rust — `impl Compte { ... }` RÉOUVRE le struct `Compte`
déjà déclaré (mécanisme reopens_node_types), plutôt que de créer un
second nœud portant le même nom (vérifié empiriquement : impl_item expose
un champ "type", pas "name", et ce nom correspond à un struct déjà
déclaré par ailleurs)."""
from __future__ import annotations

from .base import LanguageSpec


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_rust as tsrust
    return Parser(Language(tsrust.language()))


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
    for child in node.children:
        if child.type == "scoped_identifier":
            return ("imports", text(child).strip())
    return None


def _extract_reopened_name(node, text) -> str | None:
    type_node = node.child_by_field_name("type")
    return text(type_node) if type_node is not None else None


RUST_SPEC = LanguageSpec(
    name="rust",
    parser_factory=_get_parser,
    function_node_types=frozenset({"function_item"}),
    class_node_types=frozenset({"struct_item"}),
    call_node_types=frozenset({"call_expression"}),
    import_node_types=frozenset({"use_declaration"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
    reopens_node_types=frozenset({"impl_item"}),
    extract_reopened_name=_extract_reopened_name,
)
