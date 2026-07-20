"""Étape de requête : transforme une question en un sous-graphe ciblé via
Personalized PageRank, restreint aux composantes connexes contenant les
graines (corrige un bug réel : un résidu numérique non nul sur des nœuds
déconnectés polluait sinon les réponses)."""
from __future__ import annotations

import re

import networkx as nx

from .graph_utils import to_weighted_simple_undirected


def find_seed_nodes(graph: nx.MultiDiGraph, question: str) -> list[str]:
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", question))
    seeds = []
    for node_id, data in graph.nodes(data=True):
        label = str(data.get("label", "")).strip("().").lstrip(".")
        if label and label in words:
            seeds.append(node_id)
    return seeds


def query(graph: nx.MultiDiGraph, question: str, top_k: int = 20) -> dict:
    seeds = find_seed_nodes(graph, question)
    if not seeds:
        return {"seeds": [], "nodes": [], "edges": [], "note": "aucun nœud correspondant trouvé"}

    weighted_undirected = to_weighted_simple_undirected(graph)

    # Restriction aux composantes connexes contenant au moins une graine —
    # sans ça, un nœud d'une composante totalement isolée reçoit quand même
    # un score PPR résiduel non nul (~10⁻⁶, dû au nombre fini d'itérations
    # partant d'une estimation initiale uniforme), suffisant pour polluer
    # le classement sur un petit graphe.
    relevant_nodes: set[str] = set()
    for component in nx.connected_components(weighted_undirected):
        if component & set(seeds):
            relevant_nodes |= component
    scoped_graph = weighted_undirected.subgraph(relevant_nodes)

    personalization = {node_id: (1.0 if node_id in seeds else 0.0) for node_id in scoped_graph.nodes}
    try:
        scores = nx.pagerank(scoped_graph, alpha=0.85, personalization=personalization, weight="weight")
    except nx.PowerIterationFailedConvergence:
        scores = {node_id: 1.0 for node_id in scoped_graph.nodes}

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    visited = {node_id for node_id, _ in ranked[:top_k]} | set(seeds)
    if len(visited) > top_k:
        non_seed_ranked = [n for n, _ in ranked if n not in seeds]
        keep_extra = max(0, top_k - len(seeds))
        visited = set(seeds) | set(non_seed_ranked[:keep_extra])

    sub = graph.subgraph(visited)

    return {
        "seeds": seeds,
        "nodes": [dict(data, id=n, ppr_score=round(scores.get(n, 0.0), 5)) for n, data in sub.nodes(data=True)],
        "edges": [dict(data, source=u, target=v) for u, v, data in sub.edges(data=True)],
    }
