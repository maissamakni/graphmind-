"""Spécification C# (.NET) — node types vérifiés empiriquement avec
tree-sitter-c-sharp."""
from __future__ import annotations

from .base import LanguageSpec


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_c_sharp as tscsharp
    return Parser(Language(tscsharp.language()))


def _extract_call_name(node, text) -> str | None:
    # invocation_expression : le champ "function" est soit un identifier
    # simple (appel local), soit un member_access_expression (obj.Method())
    # dont le champ "name" donne le nom de méthode.
    fn_node = node.child_by_field_name("function")
    if fn_node is None:
        return None
    if fn_node.type == "identifier":
        return text(fn_node)
    if fn_node.type == "member_access_expression":
        name_node = fn_node.child_by_field_name("name")
        if name_node is not None:
            return text(name_node)
    return None


def _extract_import(node, text) -> tuple[str, str] | None:
    # using_directive -> qualified_name (ex: App.Utils) ou identifier simple.
    for child in node.children:
        if child.type in ("qualified_name", "identifier"):
            return ("imports", text(child).strip())
    return None


def _extract_file_namespace(root, text) -> str | None:
    """Cherche une déclaration `namespace X.Y { ... }` n'importe où dans le
    fichier (recherche simple, pas seulement à la racine — C# autorise
    plusieurs styles de déclaration). Retourne le PREMIER namespace
    déclaré trouvé — suffisant pour la résolution d'imports "namespace
    entier" (`using X.Y;`) en dernier recours."""
    def find_first(node):
        if node.type == "namespace_declaration":
            name_node = node.child_by_field_name("name")
            return text(name_node) if name_node is not None else None
        for child in node.children:
            found = find_first(child)
            if found is not None:
                return found
        return None
    return find_first(root)


CSHARP_SPEC = LanguageSpec(
    name="csharp",
    parser_factory=_get_parser,
    function_node_types=frozenset({"method_declaration"}),
    class_node_types=frozenset({"class_declaration", "interface_declaration", "struct_declaration"}),
    call_node_types=frozenset({"invocation_expression"}),
    import_node_types=frozenset({"using_directive"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
    extract_file_namespace=_extract_file_namespace,
)
