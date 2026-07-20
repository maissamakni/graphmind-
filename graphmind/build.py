"""Étape 3 : assemble les résultats de tous les extracteurs en un graphe
NetworkX unique (MultiDiGraph, pas DiGraph — préserve toutes les relations
distinctes entre les deux mêmes nœuds)."""
from __future__ import annotations

import hashlib

import networkx as nx

from .schema import ExtractionResult


def _disambiguate_colliding_ids(results: list[ExtractionResult]) -> None:
    """Détecte les identifiants partagés par erreur entre DEUX FICHIERS
    DIFFÉRENTS (ex: "auth/login.py" et "auth_login.py" produisent tous les
    deux "auth_login_py" via make_id), et les différencie en salant l'id
    avec un hash du chemin d'origine. Un id partagé par plusieurs nœuds du
    MÊME fichier n'est PAS une collision (déduplication normale)."""
    by_id: dict[str, set[str]] = {}
    for result in results:
        for node in result.nodes:
            by_id.setdefault(node.id, set()).add(node.source_file)

    ambiguous_ids = {nid for nid, files in by_id.items() if len(files) > 1}
    if not ambiguous_ids:
        return

    remap: dict[tuple[str, str], str] = {}
    for nid in ambiguous_ids:
        source_files = by_id[nid]
        naive = {sf: f"{nid}_{hashlib.sha1(sf.encode('utf-8')).hexdigest()[:6]}" for sf in source_files}
        for sf, new_id in naive.items():
            remap[(nid, sf)] = new_id

    for result in results:
        for node in result.nodes:
            key = (node.id, node.source_file)
            if key in remap:
                node.id = remap[key]

    for result in results:
        for edge in result.edges:
            src_key = (edge.source, edge.source_file)
            tgt_key = (edge.target, edge.source_file)
            if src_key in remap:
                edge.source = remap[src_key]
            if tgt_key in remap:
                edge.target = remap[tgt_key]


def build_graph(results: list[ExtractionResult]) -> nx.MultiDiGraph:
    """MultiDiGraph : avec un simple DiGraph, deux relations DIFFÉRENTES
    entre les mêmes deux nœuds (ex: imports_from puis calls) s'écrasent
    silencieusement l'une l'autre — bug réel corrigé par ce choix."""
    _disambiguate_colliding_ids(results)

    graph = nx.MultiDiGraph()

    for result in results:
        for node in result.nodes:
            graph.add_node(node.id, **node.to_dict())

    for result in results:
        for edge in result.edges:
            if edge.source not in graph or edge.target not in graph:
                continue
            graph.add_edge(edge.source, edge.target, **edge.to_dict())

    return graph
