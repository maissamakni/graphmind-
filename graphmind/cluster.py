"""Étape 4 : détection de communautés.

Utilise l'algorithme de Leiden (python-igraph + leidenalg) — le même
algorithme que Microsoft GraphRAG et graphify, qui offre une meilleure
garantie de qualité que la modularité gloutonne utilisée dans une version
précédente de ce module.

Repli automatique : si `python-igraph`/`leidenalg` ne sont pas installés
(dépendances optionnelles, pas dans requirements.txt de base), on retombe
sur l'algorithme de modularité gloutonne inclus nativement dans NetworkX —
jamais d'erreur bloquante, cohérent avec le reste du projet.
"""
from __future__ import annotations

import sys

import networkx as nx


def _cluster_with_leiden(graph: nx.DiGraph) -> bool:
    """Tente le clustering via Leiden. Retourne True si réussi (attribut
    'community' déjà posé sur chaque nœud), False si les paquets sont absents
    ou l'appel échoue — l'appelant doit alors utiliser le repli gloutonne."""
    try:
        import igraph as ig
        import leidenalg
    except ImportError:
        return False

    try:
        undirected = graph.to_undirected()
        node_list = list(undirected.nodes())
        index_of = {node_id: i for i, node_id in enumerate(node_list)}

        ig_graph = ig.Graph()
        ig_graph.add_vertices(len(node_list))
        ig_graph.add_edges([(index_of[u], index_of[v]) for u, v in undirected.edges()])

        partition = leidenalg.find_partition(ig_graph, leidenalg.ModularityVertexPartition)

        for community_idx, member_indices in enumerate(partition):
            for idx in member_indices:
                graph.nodes[node_list[idx]]["community"] = community_idx
        return True
    except Exception as exc:
        print(f"[graphmind] avertissement : Leiden a échoué ({exc}) — repli sur la modularité gloutonne.", file=sys.stderr)
        return False


def _cluster_with_greedy_modularity(graph: nx.DiGraph) -> None:
    undirected = graph.to_undirected()
    communities = nx.algorithms.community.greedy_modularity_communities(undirected)
    for idx, community in enumerate(communities):
        for node_id in community:
            graph.nodes[node_id]["community"] = idx


def cluster_graph(graph: nx.DiGraph) -> None:
    """Ajoute un attribut 'community' (entier) à chaque nœud, en place.

    Essaie Leiden en premier (meilleure qualité, cohérent avec GraphRAG et
    graphify) ; retombe automatiquement sur la modularité gloutonne si
    Leiden n'est pas disponible."""
    if graph.number_of_nodes() == 0:
        return
    if not _cluster_with_leiden(graph):
        _cluster_with_greedy_modularity(graph)
