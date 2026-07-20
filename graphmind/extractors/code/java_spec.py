"""Spécification Java — tous les node types ci-dessous ont été vérifiés
empiriquement en parsant du code Java réel avec tree-sitter-java (voir
justification dans la conversation de développement), pas devinés."""
from __future__ import annotations

from .base import LanguageSpec


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_java as tsjava
    return Parser(Language(tsjava.language()))


def _extract_call_name(node, text) -> str | None:
    # method_invocation : le champ "name" donne directement le nom de la
    # méthode appelée, que l'appel soit qualifié (obj.method()) ou non.
    name_node = node.child_by_field_name("name")
    return text(name_node) if name_node is not None else None


def _extract_import(node, text) -> tuple[str, str] | None:
    # import_declaration -> scoped_identifier (chemin pointé complet,
    # ex: com.example.util.Helper).
    for child in node.children:
        if child.type == "scoped_identifier":
            return ("imports", text(child).strip())
    return None


JAVA_SPEC = LanguageSpec(
    name="java",
    parser_factory=_get_parser,
    function_node_types=frozenset({"method_declaration"}),
    class_node_types=frozenset({"class_declaration", "interface_declaration"}),
    call_node_types=frozenset({"method_invocation"}),
    import_node_types=frozenset({"import_declaration"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
)
