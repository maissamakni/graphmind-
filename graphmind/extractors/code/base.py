"""Moteur d'extraction de code GÉNÉRIQUE, paramétré par langage.

Architecture : un seul walker AST commun (`extract_code`), configuré par
un `LanguageSpec` qui décrit UNIQUEMENT ce qui change d'un langage à
l'autre. Tous les noms de nœuds tree-sitter référencés dans les fichiers
`*_spec.py` ont été vérifiés empiriquement (parsés avec le vrai
analyseur), jamais devinés.

Au-delà du cas simple (nom de définition sur un champ "name", appel bien
identifié, import bien identifié), certaines grammaires ont des
structures moins courantes, chacune couverte par un mécanisme dédié et
optionnel (inutilisé par défaut, donc sans risque pour les langages qui
n'en ont pas besoin) :

- `extract_definition_name` : certains langages n'exposent pas de champ
  "name" direct sur le nœud de définition (ex: Go — le nom d'un struct
  est sur un enfant `type_spec`, pas sur `type_declaration` lui-même).
- `body_in_next_sibling_types` : certaines grammaires séparent la
  signature et le corps d'une fonction en deux nœuds FRÈRES plutôt qu'en
  parent/enfant (ex: Dart). Le corps consommé de cette façon est marqué
  pour ne JAMAIS être revisité par le parcours normal ensuite (sinon,
  double comptage des appels qu'il contient).
- `reopens_node_types` : certaines constructions ne créent pas un nouveau
  type mais complètent un type déjà déclaré ailleurs (ex: `impl Compte
  { ... }` en Rust reprend le struct `Compte` existant, n'en crée pas un
  second).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ...ids import make_id
from ...schema import Confidence, Edge, ExtractionResult, Modality, Node


def _default_definition_name(node, text) -> str | None:
    name_node = node.child_by_field_name("name")
    return text(name_node) if name_node is not None else None


@dataclass
class LanguageSpec:
    name: str
    parser_factory: Callable[[], object]
    function_node_types: frozenset[str]
    class_node_types: frozenset[str]
    call_node_types: frozenset[str]
    import_node_types: frozenset[str]
    extract_call_name: Callable[[object, Callable[[object], str]], str | None]
    extract_import: Callable[[object, Callable[[object], str]], tuple[str, str] | None]

    # Généralisations optionnelles (cf. docstring du module) :
    extract_definition_name: Callable[[object, Callable[[object], str]], str | None] = _default_definition_name
    body_in_next_sibling_types: frozenset[str] = field(default_factory=frozenset)
    reopens_node_types: frozenset[str] = field(default_factory=frozenset)
    # Node types dont les propres enfants ne doivent PAS être parcourus
    # normalement (cas réel : method_signature en Dart enveloppe un
    # function_signature enfant qui matcherait function_node_types une
    # seconde fois si on le revisitait — son seul contenu utile est déjà
    # extrait via extract_definition_name, et son vrai corps vient de
    # body_in_next_sibling_types, pas de ses propres enfants).
    skip_own_children_types: frozenset[str] = field(default_factory=frozenset)
    extract_reopened_name: Callable[[object, Callable[[object], str]], str | None] | None = None
    # Pour une fonction/méthode dont le nom du TYPE associé n'est pas
    # déductible de son imbrication dans l'arbre (cas réel : Go, où une
    # méthode `func (a *Account) Method()` est déclarée AU MÊME NIVEAU que
    # le struct, pas à l'intérieur) — si fourni et non None, rattache la
    # méthode au nœud de ce type (créé au besoin) plutôt qu'à parent_id.
    extract_receiver_type: Callable[[object, Callable[[object], str]], str | None] | None = None
    # Extrait le namespace/package déclaré par LE FICHIER ENTIER (appelé
    # une seule fois sur la racine de l'arbre, pas par nœud) — permet en
    # dernier recours de résoudre un import qui nomme un namespace ENTIER
    # (`using App.Utils;` en C#) plutôt qu'un symbole précis, cas que la
    # résolution par nom de symbole (cli.py) ne peut pas couvrir puisque
    # le texte de l'import ne contient alors aucun nom de classe.
    extract_file_namespace: Callable[[object, Callable[[object], str]], str | None] | None = None


def extract_code(
    path: Path, relative_path: str, spec: LanguageSpec,
    known_modules: dict[str, str] | None = None,
) -> ExtractionResult:
    """Walker AST générique — la même logique de parcours pour tous les
    langages, uniquement les noms de nœuds consultés changent (via `spec`).

    Reprend les principes de l'extracteur Python d'origine : résolution
    des appels internes immédiate, résolution cross-fichier différée
    (raw_calls), imports non résolus pointant vers un id stable généré
    par make_id() plutôt qu'un nœud fantôme sans id."""
    known_modules = known_modules or {}
    result = ExtractionResult()

    try:
        parser = spec.parser_factory()
    except Exception as exc:
        result.nodes.append(Node(
            id=make_id(relative_path),
            label=path.name,
            modality=Modality.CODE,
            source_file=relative_path,
            metadata={"error": f"parseur {spec.name} indisponible: {exc}"},
        ))
        result.extraction_incomplete = True
        return result

    source = path.read_bytes()
    tree = parser.parse(source)
    root = tree.root_node

    file_id = make_id(relative_path)
    result.nodes.append(Node(file_id, path.name, Modality.CODE, relative_path, "L1"))

    def text(node) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    if spec.extract_file_namespace is not None:
        result.declared_namespace = spec.extract_file_namespace(root, text)

    known_names: dict[str, str] = {}
    seen_ids: set[str] = {file_id}
    # Empreintes (start_byte, end_byte) des nœuds déjà consommés comme
    # "corps en frère suivant" (Dart) — le parcours normal doit les
    # ignorer ensuite, sinon leurs appels seraient comptés deux fois.
    consumed_ranges: set[tuple[int, int]] = set()

    def unique_id(candidate_id: str) -> str:
        """Salage minimal en cas de collision AU SEIN DU MÊME FICHIER (cas
        réel : classe 'Login' + méthode 'login()' -> même slug insensible
        à la casse). N'affecte jamais l'id en l'absence de collision."""
        if candidate_id not in seen_ids:
            seen_ids.add(candidate_id)
            return candidate_id
        suffix = 2
        while f"{candidate_id}_{suffix}" in seen_ids:
            suffix += 1
        new_id = f"{candidate_id}_{suffix}"
        seen_ids.add(new_id)
        return new_id

    def walk(node, parent_id: str) -> None:
        if (node.start_byte, node.end_byte) in consumed_ranges:
            return  # déjà traité explicitement comme corps d'une définition frère (Dart)

        line = node.start_point[0] + 1

        if node.type in spec.reopens_node_types:
            name = spec.extract_reopened_name(node, text) if spec.extract_reopened_name else None
            if name is not None:
                target_id = known_names.get(name)
                if target_id is None:
                    # Type pas encore vu à ce stade du fichier (ordre
                    # inhabituel) : créer le nœud à la volée plutôt que de
                    # perdre les méthodes qui suivent.
                    target_id = unique_id(make_id(relative_path, name))
                    result.nodes.append(Node(target_id, name, Modality.CODE, relative_path, f"L{line}"))
                    result.edges.append(Edge(parent_id, target_id, "contains", Confidence.EXTRACTED, relative_path, f"L{line}"))
                    known_names[name] = target_id
                for child in node.children:
                    walk(child, target_id)
            return

        if node.type in spec.function_node_types:
            name = spec.extract_definition_name(node, text)
            if name is not None:
                fn_id = unique_id(make_id(relative_path, name))
                result.nodes.append(Node(fn_id, f"{name}()", Modality.CODE, relative_path, f"L{line}"))

                receiver_name = spec.extract_receiver_type(node, text) if spec.extract_receiver_type else None
                if receiver_name is not None:
                    # Rattache au type récepteur (créé au besoin), pas au
                    # parent syntaxique — cas réel : Go, où la méthode est
                    # déclarée en dehors du struct.
                    receiver_id = known_names.get(receiver_name)
                    if receiver_id is None:
                        receiver_id = unique_id(make_id(relative_path, receiver_name))
                        result.nodes.append(Node(receiver_id, receiver_name, Modality.CODE, relative_path, f"L{line}"))
                        result.edges.append(Edge(parent_id, receiver_id, "contains", Confidence.EXTRACTED, relative_path, f"L{line}"))
                        known_names[receiver_name] = receiver_id
                    result.edges.append(Edge(receiver_id, fn_id, "contains", Confidence.EXTRACTED, relative_path, f"L{line}"))
                else:
                    result.edges.append(Edge(parent_id, fn_id, "contains", Confidence.EXTRACTED, relative_path, f"L{line}"))

                known_names[name] = fn_id
                if node.type not in spec.skip_own_children_types:
                    for child in node.children:
                        walk(child, fn_id)
                if node.type in spec.body_in_next_sibling_types and node.next_sibling is not None:
                    sibling = node.next_sibling
                    walk(sibling, fn_id)
                    consumed_ranges.add((sibling.start_byte, sibling.end_byte))
            return

        if node.type in spec.class_node_types:
            name = spec.extract_definition_name(node, text)
            if name is not None:
                cls_id = unique_id(make_id(relative_path, name))
                result.nodes.append(Node(cls_id, name, Modality.CODE, relative_path, f"L{line}"))
                result.edges.append(Edge(parent_id, cls_id, "contains", Confidence.EXTRACTED, relative_path, f"L{line}"))
                known_names[name] = cls_id
                for child in node.children:
                    walk(child, cls_id)
            return

        if node.type in spec.import_node_types:
            resolved = spec.extract_import(node, text)
            if resolved is not None:
                relation, module = resolved
                mod_id = known_modules.get(module)
                if mod_id is not None:
                    result.edges.append(Edge(file_id, mod_id, relation, Confidence.EXTRACTED, relative_path, f"L{line}"))
                else:
                    # L'approximation "chemin de fichier -> module" ne
                    # correspond à aucun fichier connu (cas fréquent pour
                    # PHP/C#/Kotlin/Swift/Scala, dont les espaces de noms ne
                    # suivent pas forcément le chemin de fichier) — mis de
                    # côté pour une résolution cross-fichier globale par nom
                    # de symbole (cli.py), plutôt qu'un lien mort silencieux.
                    result.raw_imports.append({
                        "source_id": file_id,
                        "module": module,
                        "relation": relation,
                        "source_file": relative_path,
                        "line": f"L{line}",
                    })

        if node.type in spec.call_node_types:
            callee = spec.extract_call_name(node, text)
            if callee is not None:
                if callee in known_names:
                    if known_names[callee] != parent_id:
                        result.edges.append(Edge(
                            parent_id, known_names[callee], "calls",
                            Confidence.EXTRACTED, relative_path, f"L{line}",
                        ))
                else:
                    result.raw_calls.append({
                        "caller_id": parent_id,
                        "callee_name": callee,
                        "source_file": relative_path,
                        "line": f"L{line}",
                    })

        for child in node.children:
            walk(child, parent_id)

    for child in root.children:
        walk(child, file_id)

    return result
