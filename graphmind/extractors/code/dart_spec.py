"""Spécification Dart — la grammaire sépare SIGNATURE et CORPS d'une
fonction/méthode en deux nœuds FRÈRES (pas parent/enfant), vérifié
empiriquement : `function_signature`/`method_signature` et le
`function_body` qui suit sont deux enfants distincts du même parent.
Nécessite le mécanisme body_in_next_sibling_types du walker générique."""
from __future__ import annotations

from .base import LanguageSpec


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_dart as tsdart
    return Parser(Language(tsdart.language()))


def _extract_definition_name(node, text) -> str | None:
    if node.type == "class_definition":
        name_node = node.child_by_field_name("name")
        return text(name_node) if name_node is not None else None
    if node.type == "function_signature":
        name_node = node.child_by_field_name("name")
        return text(name_node) if name_node is not None else None
    if node.type == "method_signature":
        # method_signature enveloppe un function_signature enfant, qui
        # seul expose le champ "name" (vérifié empiriquement).
        for child in node.children:
            if child.type == "function_signature":
                name_node = child.child_by_field_name("name")
                return text(name_node) if name_node is not None else None
    return None


def _extract_call_name(node, text) -> str | None:
    """Dart n'a pas de nœud "call_expression" isolé : un appel se
    reconnaît à un `selector` contenant `argument_part`, dont le nom
    appelé se trouve dans le nœud FRÈRE PRÉCÉDENT (vérifié empiriquement) :
    - appel simple `verify(x)` : le frère précédent est directement
      l'identifiant `verify`.
    - appel qualifié `helper.check(x)` : le frère précédent est un autre
      `selector`, qui enveloppe un `unconditional_assignable_selector`
      dont le dernier enfant nommé est l'identifiant `check`.
    """
    has_call_args = any(c.type == "argument_part" for c in node.children)
    if not has_call_args:
        return None

    prev = node.prev_sibling
    if prev is None:
        return None
    if prev.type == "identifier":
        return text(prev)
    if prev.type == "selector":
        for child in prev.children:
            if child.type == "unconditional_assignable_selector":
                for inner in child.children:
                    if inner.type == "identifier":
                        return text(inner)
    return None


def _extract_import(node, text) -> tuple[str, str] | None:
    for child in node.children:
        if child.type == "configurable_uri":
            for uri_child in child.children:
                if uri_child.type == "uri":
                    return ("imports", text(uri_child).strip("'\""))
    return None


DART_SPEC = LanguageSpec(
    name="dart",
    parser_factory=_get_parser,
    function_node_types=frozenset({"function_signature", "method_signature"}),
    class_node_types=frozenset({"class_definition"}),
    call_node_types=frozenset({"selector"}),
    import_node_types=frozenset({"library_import"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
    extract_definition_name=_extract_definition_name,
    body_in_next_sibling_types=frozenset({"function_signature", "method_signature"}),
    skip_own_children_types=frozenset({"method_signature"}),
)
