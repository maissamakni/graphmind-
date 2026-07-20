"""Spécification C++ — mêmes principes que C pour les fonctions (nom
imbriqué dans function_declarator), avec en plus les classes (champ
"name" standard, contrairement au nom de fonction)."""
from __future__ import annotations

from .base import LanguageSpec
from .c_spec import _extract_definition_name as _extract_function_name


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_cpp as tscpp
    return Parser(Language(tscpp.language()))


def _extract_definition_name(node, text) -> str | None:
    if node.type == "class_specifier":
        name_node = node.child_by_field_name("name")
        return text(name_node) if name_node is not None else None
    return _extract_function_name(node, text)  # function_definition : logique C réutilisée


def _extract_call_name(node, text) -> str | None:
    fn_node = node.child_by_field_name("function")
    if fn_node is None:
        return None
    if fn_node.type == "identifier" or fn_node.type == "field_identifier":
        return text(fn_node)
    if fn_node.type == "field_expression":
        field_node = fn_node.child_by_field_name("field")
        if field_node is not None:
            return text(field_node)
    return None


def _extract_import(node, text) -> tuple[str, str] | None:
    path_node = node.child_by_field_name("path")
    if path_node is None:
        return None
    return ("imports", text(path_node).strip('<>"'))


CPP_SPEC = LanguageSpec(
    name="cpp",
    parser_factory=_get_parser,
    function_node_types=frozenset({"function_definition"}),
    class_node_types=frozenset({"class_specifier", "struct_specifier"}),
    call_node_types=frozenset({"call_expression"}),
    import_node_types=frozenset({"preproc_include"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
    extract_definition_name=_extract_definition_name,
)
