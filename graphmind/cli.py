"""Point d'entrée : orchestre le pipeline complet.

  detect() -> extract (par modalité) -> build_graph() -> cluster_graph()
      -> export_graph() / query()

L'ordre d'extraction n'est PAS arbitraire : le code est toujours extrait
EN PREMIER, pour que son dictionnaire {nom_symbole: node_id} soit
disponible et permette la liaison cross-modale quand on extrait ensuite
les documents/PDF/images/vidéos qui mentionnent ces symboles.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import build, cache as cache_module, cluster, export, llm, query
from .detect import collect_files
from .extractors.code_python import extract_python
from .extractors.image import extract_image
from .extractors.pdf_doc import extract_pdf
from .extractors.text_doc import extract_text_doc
from .extractors.video import extract_video
from .ids import make_id
from .schema import Confidence, Edge, ExtractionResult, Modality, Node
from .security import SecurityPolicy


def _resolve_cross_file_calls(results: list[ExtractionResult]) -> None:
    """Résout les appels de fonction dont la cible n'a pas été trouvée dans
    le même fichier (raw_calls), en cherchant dans TOUS les fichiers.

    Règle de sécurité anti-"god node" (reprise de graphify) : un nom qui
    correspond à PLUSIEURS définitions différentes (ex: deux fonctions
    "execute" dans deux fichiers) n'est jamais résolu au hasard — on ne
    résout que les noms sans ambiguïté.
    """
    label_to_ids: dict[str, list[str]] = {}
    for result in results:
        for node in result.nodes:
            simple = node.label.strip("().").lstrip(".")
            if simple and simple != Path(node.source_file).name:
                label_to_ids.setdefault(simple, []).append(node.id)

    for result in results:
        for raw in result.raw_calls:
            candidates = label_to_ids.get(raw["callee_name"], [])
            if len(candidates) != 1:
                continue  # absent ou ambigu : on ne devine jamais
            target_id = candidates[0]
            if target_id == raw["caller_id"]:
                continue
            result.edges.append(Edge(
                raw["caller_id"], target_id, "calls",
                Confidence.EXTRACTED, raw["source_file"], raw["line"],
                context="cross_file",
            ))


def run_pipeline(root: Path, out_dir: Path) -> None:
    root = Path(root).resolve()
    files = collect_files(root)
    policy = SecurityPolicy()

    print(f"[graphmind] {len(files)} fichier(s) détecté(s) dans {root}")

    # Charge le cache existant (vide si c'est le premier build sur ce projet).
    # Chaque fichier sera comparé à sa version en cache par empreinte de
    # contenu — s'il n'a PAS changé, on réutilise l'extraction précédente
    # au lieu de refaire le travail (AST ou, surtout, appel LLM coûteux).
    file_cache = cache_module.load_cache(out_dir)
    current_relative_paths = {str(f.path.relative_to(root)) for f in files}
    cache_module.prune_deleted_files(file_cache, current_relative_paths)
    cache_hits = 0
    cache_misses = 0

    def extract_or_reuse(path: Path, relative_path: str, extractor_fn):
        """Retourne le résultat en cache si le fichier n'a pas changé,
        sinon appelle réellement l'extracteur et met à jour le cache."""
        nonlocal cache_hits, cache_misses
        cached = cache_module.get_cached_result(file_cache, path, relative_path)
        if cached is not None:
            cache_hits += 1
            return cached
        cache_misses += 1
        result = extractor_fn()
        cache_module.store_result(file_cache, path, relative_path, result)
        return result

    results: list[ExtractionResult] = []
    known_code_symbols: dict[str, str] = {}

    # 1. Code d'abord (aucun LLM, jamais de question de sécurité)
    python_files = [f for f in files if f.modality == Modality.CODE and f.language == "python"]
    known_modules: dict[str, str] = {}
    for f in python_files:
        rel = str(f.path.relative_to(root))
        dotted = rel[:-3].replace("\\", "/").replace("/", ".") if rel.endswith(".py") else rel
        known_modules[dotted] = make_id(rel)

    for f in files:
        if f.modality != Modality.CODE:
            continue
        rel = str(f.path.relative_to(root))
        if f.language == "python":
            r = extract_or_reuse(f.path, rel, lambda f=f, rel=rel: extract_python(f.path, rel, known_modules))
            results.append(r)
            for node in r.nodes:
                simple_name = node.label.strip("().").lstrip(".")
                if simple_name and simple_name != f.path.name:
                    known_code_symbols[simple_name] = node.id
        else:
            print(f"  (langage '{f.language}' pas encore supporté dans ce MVP, ignoré : {rel})")

    _resolve_cross_file_calls(results)

    # 2. Documents / PDF / images / vidéo, avec arbitrage de sécurité par fichier
    for f in files:
        if f.modality == Modality.CODE:
            continue
        rel = str(f.path.relative_to(root))
        decision = policy.decide(f.path)
        if decision.force_local:
            print(f"  [sécurité] {rel} -> traitement local forcé ({decision.reason})")

        if f.modality == Modality.DOCUMENT:
            results.append(extract_or_reuse(f.path, rel, lambda f=f, rel=rel: extract_text_doc(f.path, rel, known_code_symbols)))
        elif f.modality == Modality.PDF:
            results.append(extract_or_reuse(f.path, rel, lambda f=f, rel=rel, d=decision: extract_pdf(f.path, rel, d.force_local)))
        elif f.modality == Modality.IMAGE:
            results.append(extract_or_reuse(f.path, rel, lambda f=f, rel=rel, d=decision: extract_image(f.path, rel, d.force_local, known_code_symbols)))
        elif f.modality == Modality.VIDEO:
            results.append(extract_or_reuse(f.path, rel, lambda f=f, rel=rel, d=decision: extract_video(f.path, rel, d.force_local)))

    cache_module.save_cache(out_dir, file_cache)

    graph = build.build_graph(results)
    cluster.cluster_graph(graph)
    export.export_graph(graph, out_dir)

    print(f"[graphmind] Cache : {cache_hits} fichier(s) réutilisé(s) tel quel, {cache_misses} extrait(s) réellement")
    print(f"[graphmind] Graphe construit : {graph.number_of_nodes()} nœuds, {graph.number_of_edges()} relations")
    print(f"[graphmind] Résultats écrits dans {out_dir}")


def _build_context(subgraph: dict) -> str:
    """Transforme le sous-graphe (nœuds/relations) en phrases simples,
    lisibles par un humain ou un LLM — jamais du JSON brut affiché."""
    label_by_id = {n["id"]: n.get("label", n["id"]) for n in subgraph["nodes"]}
    lines = []
    for edge in subgraph["edges"]:
        src = label_by_id.get(edge.get("source"), edge.get("source"))
        tgt = label_by_id.get(edge.get("target"), edge.get("target"))
        relation = edge.get("relation", "?")
        lines.append(f"{src} —{relation}—> {tgt}")
    return "\n".join(lines)


def run_query(out_dir: Path, question: str) -> None:
    import networkx as nx
    data = json.loads((out_dir / "graph.json").read_text(encoding="utf-8"))
    graph = nx.node_link_graph(data, edges="edges", directed=True)
    subgraph = query.query(graph, question)

    if not subgraph["nodes"]:
        print("Aucun nœud du graphe ne correspond à cette question. "
              "Essayez de reformuler avec un nom de fonction/classe précis.")
        return

    context = _build_context(subgraph)
    backend = llm.resolve_backend(force_local=False)
    answer = llm.answer_question(question, context, backend)
    print(answer)


def main() -> None:
    from .envfile import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(prog="graphmind")
    sub = parser.add_subparsers(dest="command", required=True)

    build_cmd = sub.add_parser("build", help="Construit le graphe depuis un dossier")
    build_cmd.add_argument("path", type=Path)
    build_cmd.add_argument("--out", type=Path, default=Path("graphmind-out"))

    query_cmd = sub.add_parser("query", help="Interroge un graphe déjà construit")
    query_cmd.add_argument("question", type=str)
    query_cmd.add_argument("--out", type=Path, default=Path("graphmind-out"))

    args = parser.parse_args()
    if args.command == "build":
        run_pipeline(args.path, args.out)
    elif args.command == "query":
        run_query(args.out, args.question)


if __name__ == "__main__":
    main()
