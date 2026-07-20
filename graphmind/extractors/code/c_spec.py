"""Spécification C — pas de classes (langage procédural). Le nom d'une
fonction n'est pas un champ direct de function_definition : il faut
descendre dans son function_declarator (vérifié empiriquement)."""
from __future__ import annotations

from .base import LanguageSpec


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_c as tsc
    return Parser(Language(tsc.language()))


def _extract_definition_name(node, text) -> str | None:
    declarator = node.child_by_field_name("declarator")
    while declarator is not None and declarator.type not in ("identifier", "field_identifier"):
        inner = declarator.child_by_field_name("declarator")
        if inner is None:
            return None
        declarator = inner
    return text(declarator) if declarator is not None else None


def _extract_call_name(node, text) -> str | None:
    fn_node = node.child_by_field_name("function")
    return text(fn_node) if fn_node is not None and fn_node.type == "identifier" else None


def _extract_import(node, text) -> tuple[str, str] | None:
    path_node = node.child_by_field_name("path")
    if path_node is None:
        return None
    return ("imports", text(path_node).strip('<>"'))


C_SPEC = LanguageSpec(
    name="c",
    parser_factory=_get_parser,
    function_node_types=frozenset({"function_definition"}),
    class_node_types=frozenset(),  # le C n'a pas de classes
    call_node_types=frozenset({"call_expression"}),
    import_node_types=frozenset({"preproc_include"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
    extract_definition_name=_extract_definition_name,
)
