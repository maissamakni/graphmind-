"""Utilitaires partagés entre cluster.py et query.py : convertit le
MultiDiGraph en graphe simple pondéré par confiance."""
from __future__ import annotations

import networkx as nx

from .schema import Confidence

CONFIDENCE_WEIGHT = {
    Confidence.EXTRACTED.value: 1.0,
    Confidence.INFERRED.value: 0.6,
    Confidence.AMBIGUOUS.value: 0.3,
}
_DEFAULT_WEIGHT = 0.5


def to_weighted_simple_undirected(graph: nx.MultiDiGraph) -> nx.Graph:
    """Convertit en graphe simple non orienté, où chaque paire de nœuds n'a
    plus qu'UNE arête, pondérée par la SOMME des poids de confiance de
    toutes les relations parallèles d'origine entre ces deux nœuds."""
    simple = nx.Graph()
    simple.add_nodes_from(graph.nodes())

    for u, v, data in graph.edges(data=True):
        confidence = data.get("confidence", "")
        weight = CONFIDENCE_WEIGHT.get(confidence, _DEFAULT_WEIGHT)
        if simple.has_edge(u, v):
            simple[u][v]["weight"] += weight
        else:
            simple.add_edge(u, v, weight=weight)

    return simple
