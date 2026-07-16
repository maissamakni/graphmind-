"""Utilitaires partagés entre cluster.py et query.py.

Le graphe principal est un MultiDiGraph (plusieurs relations distinctes
possibles entre les deux mêmes nœuds — cf. build.py). Certains algorithmes
(détection de communautés, PageRank) ont besoin d'un graphe SIMPLE (une
seule arête par paire de nœuds) et NON ORIENTÉ. Ce module fait cette
conversion une seule fois, en pondérant chaque arête simplifiée selon la
confiance des relations d'origine qu'elle regroupe — c'est ce qui permet à
la propagation PPR et au clustering de faire davantage confiance à une
relation EXTRACTED (certaine) qu'à une relation INFERRED (déduite).
"""
from __future__ import annotations

import networkx as nx

from .schema import Confidence

# Poids par niveau de confiance — reflète la fiabilité de chaque relation
# dans les calculs de graphe (clustering, propagation PPR). Une relation
# EXTRACTED (lecture AST directe) pèse plus lourd qu'une relation INFERRED
# (déduite par LLM), qui elle-même pèse plus qu'une relation AMBIGUOUS.
CONFIDENCE_WEIGHT = {
    Confidence.EXTRACTED.value: 1.0,
    Confidence.INFERRED.value: 0.6,
    Confidence.AMBIGUOUS.value: 0.3,
}
_DEFAULT_WEIGHT = 0.5  # relation sans confiance renseignée (ne devrait pas arriver, filet de sécurité)


def to_weighted_simple_undirected(graph: nx.MultiDiGraph) -> nx.Graph:
    """Convertit le MultiDiGraph en graphe simple non orienté, où chaque
    paire de nœuds n'a plus qu'UNE SEULE arête, dont le poids est la SOMME
    des poids (par confiance) de toutes les relations parallèles d'origine
    entre ces deux nœuds.

    Deux nœuds reliés par 3 relations EXTRACTED différentes se retrouvent
    donc avec un poids plus élevé (3.0) que deux nœuds reliés par une seule
    relation INFERRED (0.6) — une paire "richement" connectée par du code
    certain compte davantage qu'une simple mention déduite par LLM.
    """
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
