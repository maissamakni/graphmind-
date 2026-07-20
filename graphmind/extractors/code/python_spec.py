"""Spécification Python — reprend EXACTEMENT le comportement de
l'extracteur Python d'origine du projet (node types déjà vérifiés)."""
from __future__ import annotations

from .base import LanguageSpec


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_python as tspython
    return Parser(Language(tspython.language()))


def _extract_call_name(node, text) -> str | None:
    fn_node = node.child_by_field_name("function")
    if fn_node is None:
        return None
    if fn_node.type == "identifier":
        return text(fn_node)
    if fn_node.type == "attribute":
        attr_node = fn_node.child_by_field_name("attribute")
        if attr_node is not None:
            return text(attr_node)
    return None


def _extract_import(node, text) -> tuple[str, str] | None:
    if node.type == "import_statement":
        for child in node.children:
            if child.type in ("dotted_name", "aliased_import"):
                module = text(child).split(" as ")[0].strip()
                return ("imports", module)
        return None
    if node.type == "import_from_statement":
        module_node = node.child_by_field_name("module_name")
        if module_node is not None:
            return ("imports_from", text(module_node).strip())
    return None


PYTHON_SPEC = LanguageSpec(
    name="python",
    parser_factory=_get_parser,
    function_node_types=frozenset({"function_definition"}),
    class_node_types=frozenset({"class_definition"}),
    call_node_types=frozenset({"call"}),
    import_node_types=frozenset({"import_statement", "import_from_statement"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
)
