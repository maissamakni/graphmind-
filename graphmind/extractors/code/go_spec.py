"""Spécification Go — pas de classes (struct + méthodes à récepteur). Le
nom d'un struct est sur son type_spec enfant, pas directement sur
type_declaration (vérifié empiriquement)."""
from __future__ import annotations

from .base import LanguageSpec


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_go as tsgo
    return Parser(Language(tsgo.language()))


def _extract_definition_name(node, text) -> str | None:
    if node.type == "type_declaration":
        for child in node.children:
            if child.type == "type_spec":
                name_node = child.child_by_field_name("name")
                return text(name_node) if name_node is not None else None
        return None
    # method_declaration / function_declaration : champ "name" standard.
    name_node = node.child_by_field_name("name")
    return text(name_node) if name_node is not None else None


def _extract_call_name(node, text) -> str | None:
    fn_node = node.child_by_field_name("function")
    if fn_node is None:
        return None
    if fn_node.type == "identifier":
        return text(fn_node)
    if fn_node.type == "selector_expression":
        field_node = fn_node.child_by_field_name("field")
        if field_node is not None:
            return text(field_node)
    return None


def _extract_import(node, text) -> tuple[str, str] | None:
    for child in node.children:
        if child.type == "import_spec":
            path_node = child.child_by_field_name("path")
            if path_node is not None:
                return ("imports", text(path_node).strip('"'))
    return None


def _extract_receiver_type(node, text) -> str | None:
    """Le récepteur d'une méthode Go (`func (a *Account) Method()`) donne
    le struct auquel elle doit être rattachée — vérifié empiriquement :
    le champ "receiver" contient un parameter_declaration dont le champ
    "type" est soit un type_identifier direct (récepteur par valeur),
    soit un pointer_type enveloppant un type_identifier (récepteur par
    pointeur, cas le plus courant)."""
    if node.type != "method_declaration":
        return None
    receiver = node.child_by_field_name("receiver")
    if receiver is None:
        return None
    for child in receiver.children:
        if child.type != "parameter_declaration":
            continue
        type_node = child.child_by_field_name("type")
        if type_node is None:
            continue
        if type_node.type == "type_identifier":
            return text(type_node)
        if type_node.type == "pointer_type":
            for inner in type_node.children:
                if inner.type == "type_identifier":
                    return text(inner)
    return None


GO_SPEC = LanguageSpec(
    name="go",
    parser_factory=_get_parser,
    function_node_types=frozenset({"function_declaration", "method_declaration"}),
    class_node_types=frozenset({"type_declaration"}),  # struct — le concept le plus proche d'une "classe" en Go
    call_node_types=frozenset({"call_expression"}),
    import_node_types=frozenset({"import_declaration"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
    extract_definition_name=_extract_definition_name,
    extract_receiver_type=_extract_receiver_type,
)
