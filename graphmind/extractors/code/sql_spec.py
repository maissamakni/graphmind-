"""Spécification SQL — extraction des fonctions/procédures stockées
(CREATE FUNCTION). Pas de concept de classe, pas d'imports au sens usuel.
Aucun champ nommé fiable pour le nom de fonction ou d'appel (vérifié
empiriquement) — extraction positionnelle via le premier
`object_reference` rencontré."""
from __future__ import annotations

from .base import LanguageSpec


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_sql as tssql
    return Parser(Language(tssql.language()))


def _first_object_reference(node, text) -> str | None:
    for child in node.children:
        if child.type == "object_reference":
            return text(child)
    return None


SQL_SPEC = LanguageSpec(
    name="sql",
    parser_factory=_get_parser,
    function_node_types=frozenset({"create_function"}),
    class_node_types=frozenset(),  # pas de concept de classe en SQL
    call_node_types=frozenset({"invocation"}),
    import_node_types=frozenset(),  # pas d'imports en SQL standard
    extract_call_name=_first_object_reference,
    extract_import=lambda node, text: None,
    extract_definition_name=_first_object_reference,
)
