"""Tests pour graph_utils.py — conversion pondérée par confiance."""
import networkx as nx

from graphmind.graph_utils import to_weighted_simple_undirected
from graphmind.schema import Confidence


def _multidigraph_with_edges(edges):
    graph = nx.MultiDiGraph()
    for u, v, confidence in edges:
        graph.add_node(u)
        graph.add_node(v)
        graph.add_edge(u, v, confidence=confidence.value)
    return graph


def test_relations_parallele_de_meme_confiance_additionnent_leur_poids():
    graph = _multidigraph_with_edges([
        ("a", "b", Confidence.EXTRACTED),
        ("a", "b", Confidence.EXTRACTED),
    ])
    simple = to_weighted_simple_undirected(graph)
    assert simple["a"]["b"]["weight"] == 2.0


def test_relation_extracted_pese_plus_qu_une_relation_inferred():
    graph_extracted = _multidigraph_with_edges([("a", "b", Confidence.EXTRACTED)])
    graph_inferred = _multidigraph_with_edges([("a", "b", Confidence.INFERRED)])
    weight_extracted = to_weighted_simple_undirected(graph_extracted)["a"]["b"]["weight"]
    weight_inferred = to_weighted_simple_undirected(graph_inferred)["a"]["b"]["weight"]
    assert weight_extracted > weight_inferred


def test_relation_ambiguous_pese_le_moins():
    graph = _multidigraph_with_edges([
        ("a", "b", Confidence.EXTRACTED),
        ("c", "d", Confidence.INFERRED),
        ("e", "f", Confidence.AMBIGUOUS),
    ])
    simple = to_weighted_simple_undirected(graph)
    assert simple["a"]["b"]["weight"] > simple["c"]["d"]["weight"] > simple["e"]["f"]["weight"]


def test_conversion_produit_un_graphe_simple_non_oriente():
    graph = _multidigraph_with_edges([("a", "b", Confidence.EXTRACTED)])
    simple = to_weighted_simple_undirected(graph)
    assert isinstance(simple, nx.Graph)
    assert not simple.is_directed()
    assert not simple.is_multigraph()


def test_noeuds_isoles_sont_conserves():
    graph = nx.MultiDiGraph()
    graph.add_node("isole")
    simple = to_weighted_simple_undirected(graph)
    assert "isole" in simple.nodes
