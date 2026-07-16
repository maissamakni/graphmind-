"""Étape 4 : détection de communautés.

Deux améliorations par rapport à une détection de communautés simple :

1. Pondération par confiance : le graphe est d'abord "aplati" en un graphe
   simple non orienté où chaque arête est pondérée selon la confiance des
   relations d'origine (EXTRACTED > INFERRED > AMBIGUOUS) — Leiden fait donc
   plus confiance aux regroupements soutenus par du code certain qu'à ceux
   qui ne reposent que sur une déduction LLM (cf. graph_utils.py).

2. Clustering hiérarchique à deux niveaux (comme Microsoft GraphRAG) :
   - 'community' : niveau FIN (résolution plus élevée) — pour naviguer
     précisément (ex: "gestion des mots de passe").
   - 'community_group' : niveau LARGE (résolution plus basse) — pour une
     vue d'ensemble (ex: "authentification & comptes"), en regroupant
     plusieurs communautés fines proches entre elles.

Repli automatique : si `python-igraph`/`leidenalg` ne sont pas installés,
on retombe sur la modularité gloutonne de NetworkX (un seul niveau, pas de
pondération par confiance — limite acceptée du repli) — jamais d'erreur
bloquante.
"""
from __future__ import annotations

import sys

import networkx as nx

from .graph_utils import to_weighted_simple_undirected

# Résolutions par défaut : plus bas = communautés plus grandes/moins nombreuses.
FINE_RESOLUTION = 0.6
COARSE_RESOLUTION = 0.15


def _leiden_partition(weighted_undirected: nx.Graph, resolution: float):
    """Retourne une partition Leiden (liste de listes d'index igraph), ou
    None si les paquets sont absents ou l'appel échoue."""
    import igraph as ig
    import leidenalg

    node_list = list(weighted_undirected.nodes())
    index_of = {node_id: i for i, node_id in enumerate(node_list)}

    ig_graph = ig.Graph()
    ig_graph.add_vertices(len(node_list))
    edges, weights = [], []
    for u, v, data in weighted_undirected.edges(data=True):
        edges.append((index_of[u], index_of[v]))
        weights.append(data.get("weight", 1.0))
    ig_graph.add_edges(edges)
    ig_graph.es["weight"] = weights

    partition = leidenalg.find_partition(
        ig_graph, leidenalg.RBConfigurationVertexPartition,
        resolution_parameter=resolution, weights="weight",
    )
    return node_list, partition


def _cluster_with_leiden(graph: nx.MultiDiGraph, weighted_undirected: nx.Graph) -> bool:
    """Clustering hiérarchique à deux niveaux via Leiden. Retourne True si
    réussi ('community' ET 'community_group' posés sur chaque nœud), False
    si les paquets sont absents ou l'appel échoue."""
    try:
        node_list, fine_partition = _leiden_partition(weighted_undirected, FINE_RESOLUTION)
        _, coarse_partition = _leiden_partition(weighted_undirected, COARSE_RESOLUTION)
    except ImportError:
        return False
    except Exception as exc:
        print(f"[graphmind] avertissement : Leiden a échoué ({exc}) — repli sur la modularité gloutonne.", file=sys.stderr)
        return False

    for community_idx, member_indices in enumerate(fine_partition):
        for idx in member_indices:
            graph.nodes[node_list[idx]]["community"] = community_idx
    for group_idx, member_indices in enumerate(coarse_partition):
        for idx in member_indices:
            graph.nodes[node_list[idx]]["community_group"] = group_idx
    return True


def _cluster_with_greedy_modularity(graph: nx.MultiDiGraph, weighted_undirected: nx.Graph) -> None:
    """Repli à un seul niveau (pas de hiérarchie) — la modularité gloutonne
    de NetworkX ne propose pas nativement un équivalent au paramètre de
    résolution de Leiden, donc pas de second niveau 'community_group' ici ;
    on le fixe à la même valeur que 'community' pour que le reste du
    pipeline (export, rapport) n'ait pas besoin de gérer un cas absent."""
    communities = nx.algorithms.community.greedy_modularity_communities(weighted_undirected, weight="weight")
    for idx, community in enumerate(communities):
        for node_id in community:
            graph.nodes[node_id]["community"] = idx
            graph.nodes[node_id]["community_group"] = idx


def cluster_graph(graph: nx.MultiDiGraph) -> None:
    """Ajoute les attributs 'community' (fin) et 'community_group' (large)
    à chaque nœud, en place. Essaie Leiden hiérarchique et pondéré en
    premier ; retombe sur la modularité gloutonne (un seul niveau) si
    Leiden n'est pas disponible."""
    if graph.number_of_nodes() == 0:
        return
    weighted_undirected = to_weighted_simple_undirected(graph)
    if not _cluster_with_leiden(graph, weighted_undirected):
        _cluster_with_greedy_modularity(graph, weighted_undirected)
