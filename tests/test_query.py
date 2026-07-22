"""Tests pour query.py — requête par PPR, restreinte aux composantes connexes."""
import networkx as nx

from graphmind.query import find_seed_nodes, query
from graphmind.schema import Modality


def _node(graph, node_id, label):
    graph.add_node(node_id, label=label, modality=Modality.CODE.value, source_file=f"{label}.py")


def test_find_seed_nodes_trouve_un_mot_entier():
    graph = nx.MultiDiGraph()
    _node(graph, "a", "login")
    seeds = find_seed_nodes(graph, "comment fonctionne login ?")
    assert seeds == ["a"]


def test_find_seed_nodes_ne_matche_pas_un_sous_mot():
    graph = nx.MultiDiGraph()
    _node(graph, "a", "login")
    seeds = find_seed_nodes(graph, "la connexion se fait via loginout")
    assert seeds == []


def test_query_sans_graine_retourne_un_resultat_vide():
    graph = nx.MultiDiGraph()
    _node(graph, "a", "login")
    result = query(graph, "question sans rapport")
    assert result["nodes"] == []
    assert result["seeds"] == []


def test_query_ne_retourne_pas_de_noeuds_de_composantes_deconnectees():
    graph = nx.MultiDiGraph()
    _node(graph, "login_fn", "login")
    _node(graph, "check_password_fn", "check_password")
    graph.add_edge("login_fn", "check_password_fn", relation="calls", confidence="EXTRACTED")

    _node(graph, "charge_fn", "charge")
    _node(graph, "invoice_fn", "generate_invoice")
    graph.add_edge("charge_fn", "invoice_fn", relation="calls", confidence="EXTRACTED")

    result = query(graph, "comment fonctionne login ?")

    returned_ids = {n["id"] for n in result["nodes"]}
    assert "login_fn" in returned_ids
    assert "check_password_fn" in returned_ids
    assert "charge_fn" not in returned_ids
    assert "generate_invoice" not in [n["label"] for n in result["nodes"]]


def test_query_inclut_toujours_les_graines():
    graph = nx.MultiDiGraph()
    _node(graph, "login_fn", "login")
    result = query(graph, "login", top_k=1)
    returned_ids = {n["id"] for n in result["nodes"]}
    assert "login_fn" in returned_ids


def test_find_seed_nodes_rattrape_une_faute_de_frappe_en_dernier_recours():
    """Nouveau : si aucune correspondance exacte n'est trouvée, une
    correspondance approximative est tentée sur les mots de la question."""
    graph = nx.MultiDiGraph()
    _node(graph, "a", "checkPassword")
    seeds = find_seed_nodes(graph, "comment fonctionne checkPasswrd ?")
    assert seeds == ["a"]


def test_find_seed_nodes_ne_fuzzy_match_jamais_si_exact_trouve_deja():
    """La correspondance approximative ne doit JAMAIS s'appliquer si le
    niveau exact a déjà trouvé quelque chose — pour ne pas affaiblir une
    correspondance déjà certaine avec un doublon fuzzy accidentel."""
    graph = nx.MultiDiGraph()
    _node(graph, "a", "login")
    _node(graph, "b", "logi")  # suffisamment proche de "login" pour matcher en fuzzy
    seeds = find_seed_nodes(graph, "comment fonctionne login ?")
    assert seeds == ["a"]  # jamais "b", puisque "a" a déjà été trouvé par exact match


def test_find_seed_nodes_mots_courts_ignores_en_fuzzy():
    """Les mots de moins de 4 caractères ne déclenchent jamais de fuzzy
    matching (trop peu fiable sur des chaînes courtes)."""
    graph = nx.MultiDiGraph()
    _node(graph, "a", "run")
    seeds = find_seed_nodes(graph, "comment ça se passe ?")
    assert seeds == []


def test_find_seed_nodes_question_hors_sujet_ne_devine_rien():
    graph = nx.MultiDiGraph()
    _node(graph, "a", "checkPassword")
    seeds = find_seed_nodes(graph, "quelle est la capitale de la France ?")
    assert seeds == []
