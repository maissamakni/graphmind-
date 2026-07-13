"""Extraction structurelle du code Python via tree-sitter — aucun appel LLM.

Produit : nœuds (fichier, fonctions, classes) et relations (contains, imports,
calls), toutes marquées EXTRACTED puisqu'elles viennent d'une lecture
grammaticale déterministe, pas d'une interprétation.
"""
from __future__ import annotations

from pathlib import Path

from ..ids import make_id
from ..schema import Confidence, Edge, ExtractionResult, Modality, Node


def _get_parser():
    from tree_sitter import Language, Parser
    import tree_sitter_python as tspython
    return Parser(Language(tspython.language()))


def extract_python(path: Path, relative_path: str, known_modules: dict[str, str] | None = None) -> ExtractionResult:
    known_modules = known_modules or {}
    result = ExtractionResult()
    try:
        parser = _get_parser()
    except Exception as exc:  # tree-sitter absent : dégrade gracieusement
        result.nodes.append(Node(
            id=make_id(relative_path),
            label=path.name,
            modality=Modality.CODE,
            source_file=relative_path,
            metadata={"error": f"tree-sitter indisponible: {exc}"},
        ))
        return result

    source = path.read_bytes()
    tree = parser.parse(source)
    root = tree.root_node

    file_id = make_id(relative_path)
    result.nodes.append(Node(file_id, path.name, Modality.CODE, relative_path, "L1"))

    def text(node) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    known_names: dict[str, str] = {}  # nom de fonction/classe -> id (pour les appels)

    def walk(node, parent_id: str) -> None:
        line = node.start_point[0] + 1

        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = text(name_node)
                fn_id = make_id(relative_path, name)
                result.nodes.append(Node(fn_id, f"{name}()", Modality.CODE, relative_path, f"L{line}"))
                result.edges.append(Edge(parent_id, fn_id, "contains", Confidence.EXTRACTED, relative_path, f"L{line}"))
                known_names[name] = fn_id
                body = node.child_by_field_name("body")
                if body is not None:
                    for child in body.children:
                        walk(child, fn_id)
            return

        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = text(name_node)
                cls_id = make_id(relative_path, name)
                result.nodes.append(Node(cls_id, name, Modality.CODE, relative_path, f"L{line}"))
                result.edges.append(Edge(parent_id, cls_id, "contains", Confidence.EXTRACTED, relative_path, f"L{line}"))
                known_names[name] = cls_id
                body = node.child_by_field_name("body")
                if body is not None:
                    for child in body.children:
                        walk(child, cls_id)
            return

        if node.type == "import_statement":
            for child in node.children:
                if child.type in ("dotted_name", "aliased_import"):
                    module = text(child).split(" as ")[0].strip()
                    mod_id = known_modules.get(module, make_id(module))
                    result.edges.append(Edge(file_id, mod_id, "imports", Confidence.EXTRACTED, relative_path, f"L{line}"))

        if node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            if module_node is not None:
                module = text(module_node).strip()
                mod_id = known_modules.get(module, make_id(module))
                result.edges.append(Edge(file_id, mod_id, "imports_from", Confidence.EXTRACTED, relative_path, f"L{line}"))

        if node.type == "call":
            fn_node = node.child_by_field_name("function")
            callee: str | None = None

            if fn_node is not None and fn_node.type == "identifier":
                # Appel direct : find_by_email(email)
                callee = text(fn_node)
            elif fn_node is not None and fn_node.type == "attribute":
                # Appel de méthode : Account.find_by_email(email) ou
                # user.check_password(password) — on ignore le récepteur
                # (Account / user) et on résout seulement par le nom de la
                # méthode, avec la même garde anti-ambiguïté que pour les
                # appels directs (résolution cross-fichier dans cli.py).
                attr_node = fn_node.child_by_field_name("attribute")
                if attr_node is not None:
                    callee = text(attr_node)

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
