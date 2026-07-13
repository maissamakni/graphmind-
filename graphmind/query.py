"""Étape de requête : transforme une question en langage naturel en un
sous-graphe ciblé, sans jamais renvoyer le graphe complet.

Mécanisme (identique dans l'esprit à ce qu'on a observé avec `graphify
query`) : identifier le(s) nœud(s) mentionné(s) dans la question, puis
une traversée BFS bornée en profondeur pour ramener un sous-graphe
compact plutôt que l'intégralité du corpus.
"""
from __future__ import annotations

import re

import networkx as nx


def find_seed_nodes(graph: nx.DiGraph, question: str) -> list[str]:
    """Trouve les nœuds dont le label apparaît (mot entier) dans la question."""
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", question))
    seeds = []
    for node_id, data in graph.nodes(data=True):
        label = str(data.get("label", "")).strip("().").lstrip(".")
        if label and label in words:
            seeds.append(node_id)
    return seeds


def query(graph: nx.DiGraph, question: str, depth: int = 2, max_nodes: int = 30) -> dict:
    """Retourne un sous-graphe {"nodes": [...], "edges": [...]} pertinent
    pour la question, au lieu du graphe complet — c'est le levier de
    réduction de tokens central de toute l'architecture."""
    seeds = find_seed_nodes(graph, question)
    if not seeds:
        return {"seeds": [], "nodes": [], "edges": [], "note": "aucun nœud correspondant trouvé"}

    undirected = graph.to_undirected()
    visited: set[str] = set(seeds)
    frontier = set(seeds)
    for _ in range(depth):
        next_frontier: set[str] = set()
        for node_id in frontier:
            next_frontier.update(undirected.neighbors(node_id))
        next_frontier -= visited
        visited.update(next_frontier)
        frontier = next_frontier
        if len(visited) >= max_nodes:
            break

    visited = set(list(visited)[:max_nodes])
    sub = graph.subgraph(visited)

    return {
        "seeds": seeds,
        "nodes": [dict(data, id=n) for n, data in sub.nodes(data=True)],
        "edges": [dict(data, source=u, target=v) for u, v, data in sub.edges(data=True)],
    }
