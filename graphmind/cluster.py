"""Étape 4 : détection de communautés — pondération par confiance,
clustering hiérarchique à deux niveaux, démarrage à chaud, avertissement
de taille. Repli sur la modularité gloutonne si Leiden indisponible."""
from __future__ import annotations

import networkx as nx

from .graph_utils import to_weighted_simple_undirected
from .logging_config import get_logger

log = get_logger()

FINE_RESOLUTION = 0.6
COARSE_RESOLUTION = 0.15

# Au-delà de ce nombre de nœuds, le recalcul complet du clustering à chaque
# build devient sensible en temps — avertissement explicite plutôt qu'une
# lenteur silencieuse.
LARGE_GRAPH_NODE_THRESHOLD = 5000


def _build_initial_membership(node_list: list[str], previous: dict[str, int] | None) -> list[int] | None:
    """Vecteur de démarrage à chaud pour leidenalg. Un nœud absent du
    clustering précédent reçoit un nouvel indice jamais utilisé (démarre
    comme singleton, pas rattaché arbitrairement à une communauté existante)."""
    if not previous:
        return None
    next_new_idx = (max(previous.values(), default=-1)) + 1
    membership = []
    for node_id in node_list:
        if node_id in previous:
            membership.append(previous[node_id])
        else:
            membership.append(next_new_idx)
            next_new_idx += 1
    return membership


def _leiden_partition(weighted_undirected: nx.Graph, resolution: float, initial: dict[str, int] | None = None):
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

    initial_membership = _build_initial_membership(node_list, initial)
    partition = leidenalg.find_partition(
        ig_graph, leidenalg.RBConfigurationVertexPartition,
        resolution_parameter=resolution, weights="weight",
        initial_membership=initial_membership,
    )
    return node_list, partition


def _cluster_with_leiden(
    graph: nx.MultiDiGraph, weighted_undirected: nx.Graph,
    previous_fine: dict[str, int] | None = None,
    previous_coarse: dict[str, int] | None = None,
    fine_resolution: float = FINE_RESOLUTION,
    coarse_resolution: float = COARSE_RESOLUTION,
) -> bool:
    try:
        node_list, fine_partition = _leiden_partition(weighted_undirected, fine_resolution, previous_fine)
        _, coarse_partition = _leiden_partition(weighted_undirected, coarse_resolution, previous_coarse)
    except ImportError:
        return False
    except Exception as exc:
        log.warning(f"Leiden a échoué ({exc}) — repli sur la modularité gloutonne.")
        return False

    for community_idx, member_indices in enumerate(fine_partition):
        for idx in member_indices:
            graph.nodes[node_list[idx]]["community"] = community_idx
    for group_idx, member_indices in enumerate(coarse_partition):
        for idx in member_indices:
            graph.nodes[node_list[idx]]["community_group"] = group_idx
    return True


def _cluster_with_greedy_modularity(graph: nx.MultiDiGraph, weighted_undirected: nx.Graph) -> None:
    communities = nx.algorithms.community.greedy_modularity_communities(weighted_undirected, weight="weight")
    for idx, community in enumerate(communities):
        for node_id in community:
            graph.nodes[node_id]["community"] = idx
            graph.nodes[node_id]["community_group"] = idx


def cluster_graph(
    graph: nx.MultiDiGraph,
    previous_fine: dict[str, int] | None = None,
    previous_coarse: dict[str, int] | None = None,
    fine_resolution: float = FINE_RESOLUTION,
    coarse_resolution: float = COARSE_RESOLUTION,
) -> None:
    """previous_fine/previous_coarse : clustering précédent pour démarrer à
    chaud (plus rapide, identifiants stables d'un build à l'autre)."""
    if graph.number_of_nodes() == 0:
        return

    if graph.number_of_nodes() > LARGE_GRAPH_NODE_THRESHOLD:
        log.warning(
            f"graphe volumineux ({graph.number_of_nodes()} nœuds) — le clustering complet peut "
            f"devenir coûteux à chaque build. Envisager `build --no-cluster` pour les mises à jour "
            f"fréquentes, et `graphmind cluster` seulement ponctuellement."
        )

    weighted_undirected = to_weighted_simple_undirected(graph)
    if not _cluster_with_leiden(graph, weighted_undirected, previous_fine, previous_coarse, fine_resolution, coarse_resolution):
        _cluster_with_greedy_modularity(graph, weighted_undirected)
