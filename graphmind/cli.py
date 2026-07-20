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
import os
from pathlib import Path

from . import build, cache as cache_module, cluster, export, llm, query
from .config import load_config, write_example_config
from .detect import collect_files
from .extractors.code import SPECS_BY_LANGUAGE, extract_code_file
from .extractors.image import extract_image
from .extractors.pdf_doc import extract_pdf
from .extractors.text_doc import extract_text_doc
from .extractors.video import extract_video
from .ids import make_id
from .logging_config import configure_logging, get_logger
from .schema import Confidence, Edge, ExtractionResult, Modality, Node
from .security import SecurityPolicy

log = get_logger()


def _last_import_component(module: str) -> str:
    """Dernier segment d'un chemin d'import, quel que soit le séparateur
    utilisé par le langage (ex: "App\\Helper" en PHP, "com.example.Helper"
    en Kotlin/C#/Scala) — c'est ce dernier segment qui correspond au nom
    du symbole (classe/type) réellement recherché dans le code."""
    return module.replace("\\", ".").rsplit(".", 1)[-1].strip()


def _resolve_cross_file_calls(results: list[ExtractionResult]) -> None:
    """Table globale label->ids sur TOUT le corpus, résout les appels ET
    les imports non trouvés localement — garde anti-ambiguïté : un nom
    qui correspond à plusieurs définitions n'est jamais résolu au hasard.

    Pour les imports, DEUX niveaux de résolution en dernier recours :
    1. Par nom de symbole précis (ex: "App\\Utils\\Helper" -> "Helper") —
       couvre PHP/Kotlin/Scala, dont les imports nomment une classe précise.
    2. Par namespace ENTIER déclaré (ex: "App.Utils" déclaré par un autre
       fichier via `namespace App.Utils { ... }`) — couvre C#, dont les
       imports (`using App.Utils;`) nomment un namespace, jamais une classe
       précise, donc invisibles pour le niveau 1."""
    label_to_ids: dict[str, list[str]] = {}
    namespace_to_file_ids: dict[str, list[str]] = {}
    for result in results:
        for node in result.nodes:
            simple = node.label.strip("().").lstrip(".")
            if simple and simple != Path(node.source_file).name:
                label_to_ids.setdefault(simple, []).append(node.id)
        if result.declared_namespace and result.nodes:
            file_node_id = result.nodes[0].id  # le nœud fichier est toujours ajouté en premier
            namespace_to_file_ids.setdefault(result.declared_namespace, []).append(file_node_id)

    for result in results:
        for raw in result.raw_calls:
            candidates = label_to_ids.get(raw["callee_name"], [])
            if len(candidates) != 1:
                continue
            target_id = candidates[0]
            if target_id == raw["caller_id"]:
                continue
            result.edges.append(Edge(
                raw["caller_id"], target_id, "calls",
                Confidence.EXTRACTED, raw["source_file"], raw["line"],
                context="cross_file",
            ))

        for raw in result.raw_imports:
            symbol = _last_import_component(raw["module"])
            candidates = label_to_ids.get(symbol, [])
            if len(candidates) == 1:
                target_id = candidates[0]
                if target_id != raw["source_id"]:
                    result.edges.append(Edge(
                        raw["source_id"], target_id, raw["relation"],
                        Confidence.EXTRACTED, raw["source_file"], raw["line"],
                        context="cross_file_import",
                    ))
                continue

            # Niveau 2 : import de namespace entier (ex: C# "using App.Utils;")
            ns_candidates = namespace_to_file_ids.get(raw["module"].strip(), [])
            if len(ns_candidates) != 1:
                continue  # jamais résolu au hasard si ambigu ou introuvable
            target_id = ns_candidates[0]
            if target_id == raw["source_id"]:
                continue
            result.edges.append(Edge(
                raw["source_id"], target_id, raw["relation"],
                Confidence.EXTRACTED, raw["source_file"], raw["line"],
                context="cross_file_import_namespace",
            ))


def _load_previous_communities(out_dir: Path) -> tuple[dict[str, int], dict[str, int]]:
    """Charge le clustering d'un graph.json déjà existant, pour démarrer
    Leiden à chaud. Retourne des dicts vides si absent ou corrompu."""
    graph_path = out_dir / "graph.json"
    if not graph_path.is_file():
        return {}, {}
    try:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}, {}
    fine, coarse = {}, {}
    for node in data.get("nodes", []):
        node_id = node.get("id")
        if node_id is None:
            continue
        if "community" in node:
            fine[node_id] = node["community"]
        if "community_group" in node:
            coarse[node_id] = node["community_group"]
    return fine, coarse


def run_pipeline(root: Path, out_dir: Path, do_cluster: bool = True) -> None:
    root = Path(root).resolve()

    cfg = load_config(root)
    if cfg.groq_model:
        os.environ.setdefault("GRAPHMIND_GROQ_MODEL", cfg.groq_model)
    if cfg.groq_vision_model:
        os.environ.setdefault("GRAPHMIND_GROQ_VISION_MODEL", cfg.groq_vision_model)

    files = collect_files(root, cfg.extra_ignore_dirs)
    policy = SecurityPolicy(cfg.extra_sensitive_dirs)

    log.info(f"{len(files)} fichier(s) détecté(s) dans {root}")

    file_cache = cache_module.load_cache(out_dir)
    current_relative_paths = {str(f.path.relative_to(root)) for f in files}
    cache_module.prune_deleted_files(file_cache, current_relative_paths)
    cache_hits = 0
    cache_misses = 0

    def extract_or_reuse(path: Path, relative_path: str, extractor_fn):
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

    # known_modules : approximation "chemin de fichier -> chemin de module
    # pointé" (ex: auth/login.py -> auth.login). Fiable pour Python (le
    # chemin EST le module, par construction du langage) et raisonnable
    # pour Java qui suit la même convention (package com.example ↔ dossier
    # com/example) — mais PHP (PSR-4) et C# (namespaces déclarés
    # librement) ne garantissent PAS que le chemin de fichier corresponde
    # à l'espace de noms réel. Sur ces deux langages, la résolution
    # cross-fichier des imports reste donc moins fiable que pour Python —
    # limite assumée, à documenter, pas cachée.
    code_files = [f for f in files if f.modality == Modality.CODE and f.language in SPECS_BY_LANGUAGE]
    known_modules: dict[str, str] = {}
    for f in code_files:
        rel = str(f.path.relative_to(root))
        stem = rel.rsplit(".", 1)[0] if "." in rel else rel
        dotted = stem.replace("\\", "/").replace("/", ".")
        known_modules[dotted] = make_id(rel)

    for f in files:
        if f.modality != Modality.CODE:
            continue
        rel = str(f.path.relative_to(root))
        if f.language in SPECS_BY_LANGUAGE:
            r = extract_or_reuse(f.path, rel, lambda f=f, rel=rel: extract_code_file(f.path, rel, f.language, known_modules))
            results.append(r)
            for node in r.nodes:
                simple_name = node.label.strip("().").lstrip(".")
                if simple_name and simple_name != f.path.name:
                    known_code_symbols[simple_name] = node.id
        else:
            log.info(f"langage '{f.language}' pas encore supporté dans ce MVP, ignoré : {rel}")

    _resolve_cross_file_calls(results)

    for f in files:
        if f.modality == Modality.CODE:
            continue
        rel = str(f.path.relative_to(root))
        decision = policy.decide(f.path)
        if decision.force_local:
            log.info(f"sécurité : {rel} -> traitement local forcé ({decision.reason})")

        if f.modality == Modality.DOCUMENT:
            results.append(extract_or_reuse(f.path, rel, lambda f=f, rel=rel, d=decision: extract_text_doc(f.path, rel, known_code_symbols, d.force_local)))
        elif f.modality == Modality.PDF:
            results.append(extract_or_reuse(f.path, rel, lambda f=f, rel=rel, d=decision: extract_pdf(f.path, rel, d.force_local)))
        elif f.modality == Modality.IMAGE:
            results.append(extract_or_reuse(f.path, rel, lambda f=f, rel=rel, d=decision: extract_image(f.path, rel, d.force_local, known_code_symbols)))
        elif f.modality == Modality.VIDEO:
            results.append(extract_or_reuse(f.path, rel, lambda f=f, rel=rel, d=decision: extract_video(f.path, rel, d.force_local, known_code_symbols)))

    cache_module.save_cache(out_dir, file_cache)

    graph = build.build_graph(results)
    if do_cluster:
        previous_fine, previous_coarse = _load_previous_communities(out_dir)
        cluster.cluster_graph(graph, previous_fine, previous_coarse, cfg.fine_resolution, cfg.coarse_resolution)
    else:
        log.info("Clustering ignoré (--no-cluster) — les nœuds n'auront pas d'attribut 'community' "
                  "tant que `graphmind cluster` n'aura pas été lancé séparément.")
    export.export_graph(graph, out_dir)

    log.info(f"Cache : {cache_hits} fichier(s) réutilisé(s) tel quel, {cache_misses} extrait(s) réellement")
    log.info(f"Graphe construit : {graph.number_of_nodes()} nœuds, {graph.number_of_edges()} relations")
    log.info(f"Résultats écrits dans {out_dir}")


def run_cluster(out_dir: Path) -> None:
    """Recharge un graphe déjà construit et applique SEULEMENT le
    clustering, sans refaire l'extraction ni la construction du graphe."""
    import networkx as nx
    graph_path = out_dir / "graph.json"
    if not graph_path.is_file():
        log.warning(f"Aucun graphe trouvé dans {out_dir} — lance d'abord `graphmind build`.")
        return

    data = json.loads(graph_path.read_text(encoding="utf-8"))
    graph = nx.node_link_graph(data, edges="edges", directed=True, multigraph=True)

    previous_fine = {n: d["community"] for n, d in graph.nodes(data=True) if "community" in d}
    previous_coarse = {n: d["community_group"] for n, d in graph.nodes(data=True) if "community_group" in d}

    cluster.cluster_graph(graph, previous_fine, previous_coarse)
    export.export_graph(graph, out_dir)
    log.info(f"Clustering recalculé sur {graph.number_of_nodes()} nœuds.")
    log.info(f"Résultats mis à jour dans {out_dir}")


def _build_context(subgraph: dict) -> str:
    """Organise le sous-graphe en DEUX sections distinctes — faits de CODE
    certains vs CONTEXTE documentaire — exploitant la hiérarchie
    document/image/vidéo -> concept -> code déjà présente dans les données,
    plutôt qu'une liste plate mélangeant les deux niveaux."""
    label_by_id = {n["id"]: n.get("label", n["id"]) for n in subgraph["nodes"]}
    modality_by_id = {n["id"]: n.get("modality", "code") for n in subgraph["nodes"]}

    code_facts, doc_facts = [], []
    for edge in subgraph["edges"]:
        src_id, tgt_id = edge.get("source"), edge.get("target")
        src = label_by_id.get(src_id, src_id)
        tgt = label_by_id.get(tgt_id, tgt_id)
        line = f"{src} —{edge.get('relation', '?')}—> {tgt}"

        src_modality = modality_by_id.get(src_id, "code")
        tgt_modality = modality_by_id.get(tgt_id, "code")
        if src_modality != "code" or tgt_modality != "code":
            doc_facts.append(line)
        else:
            code_facts.append(line)

    parts = []
    if code_facts:
        parts.append("Faits extraits directement du code (certains) :\n" + "\n".join(code_facts))
    if doc_facts:
        parts.append("Contexte documentaire associé (documentation/image/vidéo) :\n" + "\n".join(doc_facts))
    return "\n\n".join(parts)


def run_query(out_dir: Path, question: str) -> None:
    import networkx as nx
    data = json.loads((out_dir / "graph.json").read_text(encoding="utf-8"))
    graph = nx.node_link_graph(data, edges="edges", directed=True, multigraph=True)
    subgraph = query.query(graph, question)

    if not subgraph["nodes"]:
        print("Aucun nœud du graphe ne correspond à cette question. "
              "Essayez de reformuler avec un nom de fonction/classe précis.")
        return

    context = _build_context(subgraph)
    backend = llm.resolve_backend(force_local=False)
    answer = llm.answer_question(question, context, backend)
    print(answer)


def run_status(root: Path, out_dir: Path) -> None:
    root = Path(root).resolve()
    files = collect_files(root)
    file_cache = cache_module.load_cache(out_dir)

    file_pairs = [(f.path, str(f.path.relative_to(root))) for f in files]
    status = cache_module.check_status(file_cache, file_pairs)

    print(json.dumps(status, indent=2, ensure_ascii=False))
    if status["needs_rebuild"]:
        log.info(f"Reconstruction nécessaire : {len(status['new'])} nouveau(x), "
                  f"{len(status['changed'])} modifié(s), {len(status['deleted'])} supprimé(s).")
    else:
        log.info("Rien n'a changé — inutile de relancer `build`.")


def run_init_config(root: Path) -> None:
    destination = Path(root) / "graphmind.toml"
    if destination.exists():
        log.warning(f"{destination} existe déjà — rien écrit, pour ne jamais écraser une configuration existante.")
        return
    write_example_config(destination)
    log.info(f"Exemple de configuration écrit dans {destination}")


def main() -> None:
    from .envfile import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(prog="graphmind")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                         help="Augmente la verbosité (messages DEBUG en plus des INFO).")
    parser.add_argument("-q", "--quiet", action="store_true",
                         help="Réduit la verbosité (WARNING/ERROR uniquement).")
    sub = parser.add_subparsers(dest="command", required=True)

    build_cmd = sub.add_parser("build", help="Construit le graphe depuis un dossier")
    build_cmd.add_argument("path", type=Path)
    build_cmd.add_argument("--out", type=Path, default=Path("graphmind-out"))
    build_cmd.add_argument("--no-cluster", action="store_true",
                            help="Ignore le recalcul des communautés (rapide) — à relancer séparément via `graphmind cluster`")

    cluster_cmd = sub.add_parser("cluster", help="Recalcule uniquement le clustering d'un graphe déjà construit")
    cluster_cmd.add_argument("--out", type=Path, default=Path("graphmind-out"))

    status_cmd = sub.add_parser("status", help="Vérifie si une reconstruction est nécessaire, sans rien extraire")
    status_cmd.add_argument("path", type=Path)
    status_cmd.add_argument("--out", type=Path, default=Path("graphmind-out"))

    init_config_cmd = sub.add_parser("init-config", help="Génère un exemple de graphmind.toml commenté")
    init_config_cmd.add_argument("path", type=Path, nargs="?", default=Path("."),
                                  help="Dossier où écrire graphmind.toml")

    query_cmd = sub.add_parser("query", help="Interroge un graphe déjà construit")
    query_cmd.add_argument("question", type=str)
    query_cmd.add_argument("--out", type=Path, default=Path("graphmind-out"))

    args = parser.parse_args()
    verbosity = -1 if args.quiet else args.verbose
    configure_logging(verbosity)

    if args.command == "build":
        run_pipeline(args.path, args.out, do_cluster=not args.no_cluster)
    elif args.command == "cluster":
        run_cluster(args.out)
    elif args.command == "status":
        run_status(args.path, args.out)
    elif args.command == "query":
        run_query(args.out, args.question)
    elif args.command == "init-config":
        run_init_config(args.path)


if __name__ == "__main__":
    main()
