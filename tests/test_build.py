"""Tests pour build.py — construction du graphe, collisions, MultiDiGraph."""
from graphmind.build import build_graph
from graphmind.schema import Confidence, Edge, ExtractionResult, Modality, Node


def test_deux_fichiers_differents_en_collision_sont_differencies():
    same_id = "auth_login_py"
    results = [
        ExtractionResult(nodes=[Node(same_id, "login.py", Modality.CODE, "auth/login.py")]),
        ExtractionResult(nodes=[Node(same_id, "login.py", Modality.CODE, "auth_login.py")]),
    ]
    graph = build_graph(results)
    assert graph.number_of_nodes() == 2


def test_meme_fichier_extrait_deux_fois_reste_un_seul_noeud():
    node = Node("login_py", "login.py", Modality.CODE, "login.py")
    results = [ExtractionResult(nodes=[node]), ExtractionResult(nodes=[node])]
    graph = build_graph(results)
    assert graph.number_of_nodes() == 1


def test_relations_paralleles_sont_toutes_preservees():
    nodes = [
        Node("a", "login.py", Modality.CODE, "login.py"),
        Node("b", "account.py", Modality.CODE, "account.py"),
    ]
    edges = [
        Edge("a", "b", "imports_from", Confidence.EXTRACTED, "login.py"),
        Edge("a", "b", "calls", Confidence.EXTRACTED, "login.py"),
    ]
    results = [ExtractionResult(nodes=nodes, edges=edges)]
    graph = build_graph(results)
    assert graph.number_of_edges() == 2
    relations = {data["relation"] for _, _, data in graph.edges(data=True)}
    assert relations == {"imports_from", "calls"}


def test_relation_vers_noeud_inexistant_est_ignoree_proprement():
    nodes = [Node("a", "login.py", Modality.CODE, "login.py")]
    edges = [Edge("a", "id_qui_nexiste_pas", "calls", Confidence.EXTRACTED, "login.py")]
    results = [ExtractionResult(nodes=nodes, edges=edges)]
    graph = build_graph(results)
    assert graph.number_of_nodes() == 1
    assert graph.number_of_edges() == 0
