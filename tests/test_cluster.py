"""Tests pour cluster.py — clustering et démarrage à chaud."""
import networkx as nx
import pytest

from graphmind.cluster import cluster_graph

igraph = pytest.importorskip("igraph", reason="python-igraph non installé")
pytest.importorskip("leidenalg", reason="leidenalg non installé")


def _small_graph():
    graph = nx.MultiDiGraph()
    graph.add_edge("a", "b")
    graph.add_edge("b", "c")
    graph.add_edge("d", "e")
    return graph


def test_cluster_graph_assigne_une_communaute_a_chaque_noeud():
    graph = _small_graph()
    cluster_graph(graph)
    for node_id in graph.nodes:
        assert "community" in graph.nodes[node_id]
        assert "community_group" in graph.nodes[node_id]


def test_graphe_vide_ne_plante_pas():
    graph = nx.MultiDiGraph()
    cluster_graph(graph)


def test_warm_start_produit_des_ids_de_communaute_stables():
    graph1 = _small_graph()
    cluster_graph(graph1)
    previous_fine = {n: d["community"] for n, d in graph1.nodes(data=True)}
    previous_coarse = {n: d["community_group"] for n, d in graph1.nodes(data=True)}

    graph2 = _small_graph()
    cluster_graph(graph2, previous_fine, previous_coarse)

    for node_id in graph1.nodes:
        assert graph1.nodes[node_id]["community"] == graph2.nodes[node_id]["community"]


def test_avertissement_de_taille_sur_un_gros_graphe(caplog):
    import logging
    from graphmind.cluster import LARGE_GRAPH_NODE_THRESHOLD

    graph = nx.MultiDiGraph()
    for i in range(LARGE_GRAPH_NODE_THRESHOLD + 1):
        graph.add_node(f"n{i}")
    for i in range(LARGE_GRAPH_NODE_THRESHOLD):
        graph.add_edge(f"n{i}", f"n{i + 1}")

    with caplog.at_level(logging.WARNING, logger="graphmind"):
        cluster_graph(graph)

    assert any("volumineux" in record.message for record in caplog.records)


def test_pas_d_avertissement_sur_un_petit_graphe(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="graphmind"):
        cluster_graph(_small_graph())
    assert not any("volumineux" in record.message for record in caplog.records)
