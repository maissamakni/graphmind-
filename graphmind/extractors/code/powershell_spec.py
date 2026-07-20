"""Spécification PowerShell — supporte les classes PS5+ (class_statement /
class_method_definition), en plus des fonctions de script classiques.
Particularité vérifiée empiriquement : appels ET imports (Import-Module)
partagent le MÊME type de nœud `command`, différenciés uniquement par
leur contenu — d'où `command` présent dans call_node_types ET
import_node_types, chaque extracteur retournant None s'il ne reconnaît
pas son cas."""
from __future__ import annotations

from .base import LanguageSpec


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_powershell as tsps
    return Parser(Language(tsps.language()))


def _extract_definition_name(node, text) -> str | None:
    if node.type == "function_statement":
        for child in node.children:
            if child.type == "function_name":
                return text(child)
        return None
    if node.type in ("class_statement", "class_method_definition"):
        # Aucun champ nommé exposé par cette grammaire (vérifié
        # empiriquement) — le premier enfant direct de type "simple_name"
        # porte le nom (jamais ambigu avec un type de retour éventuel,
        # dont les enfants sont "type_literal", sans simple_name direct).
        for child in node.children:
            if child.type == "simple_name":
                return text(child)
        return None
    return None


def _command_name_text(node, text) -> str | None:
    name_node = node.child_by_field_name("command_name")
    return text(name_node) if name_node is not None else None


def _extract_call_name(node, text) -> str | None:
    name = _command_name_text(node, text)
    if name is None or name.lower() == "import-module":
        return None  # les imports sont traités séparément, jamais comme un appel
    return name


def _extract_import(node, text) -> tuple[str, str] | None:
    name = _command_name_text(node, text)
    if name is None or name.lower() != "import-module":
        return None
    for child in node.children:
        if child.type == "command_elements":
            return ("imports", text(child).strip())
    return None


POWERSHELL_SPEC = LanguageSpec(
    name="powershell",
    parser_factory=_get_parser,
    function_node_types=frozenset({"function_statement", "class_method_definition"}),
    class_node_types=frozenset({"class_statement"}),
    call_node_types=frozenset({"command"}),
    import_node_types=frozenset({"command"}),
    extract_call_name=_extract_call_name,
    extract_import=_extract_import,
    extract_definition_name=_extract_definition_name,
)
