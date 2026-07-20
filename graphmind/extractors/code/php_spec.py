"""Spécification PHP — node types vérifiés empiriquement (fonctions
globales ET méthodes de classe, trois formes d'appel distinctes en PHP :
appel simple, appel de méthode d'instance, appel statique)."""
from __future__ import annotations

from .base import LanguageSpec


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_php as tsphp
    return Parser(Language(tsphp.language_php()))


def _extract_call_name(node, text) -> str | None:
    if node.type == "function_call_expression":
        fn_node = node.child_by_field_name("function")
        return text(fn_node) if fn_node is not None else None
    if node.type in ("member_call_expression", "scoped_call_expression"):
        # member_call_expression : $obj->method() — scoped_call_expression :
        # Classe::method() — les deux exposent le nom de méthode via "name"
        # (vérifié : pour scoped_call_expression, "name" donne bien le nom
        # de méthode, pas le nom de classe).
        name_node = node.child_by_field_name("name")
        return text(name_node) if name_node is not None else None
    return None


def _extract_import(node, text) -> tuple[str, str] | None:
    # namespace_use_declaration : pas de champ nommé simple pour le chemin
    # complet — on prend le texte brut du nœud, nettoyé de "use"/";".
    raw = text(node).strip()
    if raw.startswith("use"):
        raw = raw[3:]
    return ("imports", raw.strip().rstrip(";").strip())


PHP_SPEC = LanguageSpec(
    name="php",
    parser_factory=_get_parser,
    function_node_types=frozenset({"function_definition", "method_declaration"}),
    class_node_types=frozenset({"class_declaration"}),
    call_node_types=frozenset({"function_call_expression", "member_call_expression", "scoped_call_expression"}),
    import_node_types=frozenset({"namespace_use_declaration"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
)
