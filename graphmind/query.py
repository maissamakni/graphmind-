"""Étape de requête : transforme une question en langage naturel en un
sous-graphe ciblé, sans jamais renvoyer le graphe complet.

Mécanisme : identification des nœuds mentionnés dans la question (les
"graines"), puis propagation d'un score de pertinence à travers le graphe
via l'algorithme Personalized PageRank (PPR) — le même principe que
HippoRAG2, plutôt qu'une simple traversée en largeur (BFS) à profondeur
fixe. Contrairement au BFS, le PPR :
  - donne un score CONTINU à chaque nœud (pas juste "atteint / pas atteint"),
    qui décroît naturellement avec la distance aux graines ;
  - capture les nœuds fortement connectés à PLUSIEURS graines à la fois
    (ex: un "pont" entre deux fonctions citées dans la question), même s'ils
    ne sont ni le nom de la fonction ni son voisin direct ;
  - ne nécessite pas de choisir une profondeur arbitraire (2 sauts, 3 sauts...) :
    le score fait naturellement ce tri, on garde juste les N meilleurs.
Tout ce calcul reste 100% déterministe et gratuit en tokens (aucun appel LLM
ici) — c'est un calcul purement algébrique sur la structure du graphe.
"""
from __future__ import annotations

import re

import networkx as nx

from .graph_utils import to_weighted_simple_undirected


def find_seed_nodes(graph: nx.MultiDiGraph, question: str) -> list[str]:
    """Trouve les nœuds dont le label apparaît (mot entier) dans la question."""
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", question))
    seeds = []
    for node_id, data in graph.nodes(data=True):
        label = str(data.get("label", "")).strip("().").lstrip(".")
        if label and label in words:
            seeds.append(node_id)
    return seeds


def query(graph: nx.MultiDiGraph, question: str, top_k: int = 20) -> dict:
    """Retourne un sous-graphe {"nodes": [...], "edges": [...]} pertinent
    pour la question, au lieu du graphe complet — c'est le levier de
    réduction de tokens central de toute l'architecture.

    top_k : nombre maximum de nœuds gardés après le classement par score PPR
    (remplace l'ancien paramètre "depth" du BFS — ici la profondeur n'est
    plus fixée à l'avance, elle émerge du score de propagation).
    """
    seeds = find_seed_nodes(graph, question)
    if not seeds:
        return {"seeds": [], "nodes": [], "edges": [], "note": "aucun nœud correspondant trouvé"}

    # Graphe "aplati" en simple/non-orienté, pondéré par la CONFIANCE des
    # relations d'origine (cf. graph_utils.py) — la propagation fait donc
    # davantage confiance à un chemin soutenu par des relations EXTRACTED
    # (lecture AST certaine) qu'à un chemin qui ne repose que sur des
    # relations INFERRED (déduites par LLM).
    weighted_undirected = to_weighted_simple_undirected(graph)

    # Restreindre aux composantes connexes qui contiennent au moins une
    # graine. Sans ça, un nœud d'une partie du projet totalement isolée
    # (ex: le module "notifications" qui n'importe jamais "database") reçoit
    # quand même un score PPR RÉSIDUEL non nul (de l'ordre de 10⁻⁶) — pas
    # zéro exact, à cause du nombre fini d'itérations de l'algorithme partant
    # d'une estimation initiale uniforme sur tous les nœuds — ce qui suffit à
    # le faire apparaître dans le classement si le graphe a peu de nœuds
    # réellement pertinents. Un simple seuil numérique est fragile (le bon
    # seuil dépend de la taille du graphe) ; restreindre aux composantes
    # connexes règle le problème à la racine plutôt que par un réglage
    # approximatif.
    relevant_nodes: set[str] = set()
    for component in nx.connected_components(weighted_undirected):
        if component & set(seeds):
            relevant_nodes |= component
    scoped_graph = weighted_undirected.subgraph(relevant_nodes)

    # Personalized PageRank : le vecteur de personnalisation concentre TOUT le
    # score de départ sur les nœuds-graines (poids égal entre elles) ; le
    # reste du graphe ne reçoit un score que par propagation depuis ces graines.
    personalization = {node_id: (1.0 if node_id in seeds else 0.0) for node_id in scoped_graph.nodes}
    try:
        scores = nx.pagerank(scoped_graph, alpha=0.85, personalization=personalization, weight="weight")
    except nx.PowerIterationFailedConvergence:
        # Repli rare (graphe pathologique) : score uniforme, tout le monde à
        # égalité — le tri par score suivant ne changera rien, mais on ne
        # plante jamais le pipeline pour autant.
        scores = {node_id: 1.0 for node_id in scoped_graph.nodes}

    # Classement par score décroissant ; les graines elles-mêmes sont
    # explicitement forcées en tête (score le plus élevé par construction),
    # donc toujours incluses même sur un graphe où le PPR convergerait mal.
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    visited = {node_id for node_id, _ in ranked[:top_k]} | set(seeds)
    if len(visited) > top_k:
        # Si l'ajout forcé des graines dépasse top_k, on retire les scores
        # les plus faibles hors-graines pour respecter la limite demandée.
        non_seed_ranked = [n for n, _ in ranked if n not in seeds]
        keep_extra = max(0, top_k - len(seeds))
        visited = set(seeds) | set(non_seed_ranked[:keep_extra])

    # sub reste tiré du graphe MultiDiGraph d'origine (pas de la version
    # aplatie) : on garde ainsi TOUTES les relations distinctes entre deux
    # nœuds (ex: "imports_from" ET "calls" tous les deux), pas juste une
    # seule arête fusionnée.
    sub = graph.subgraph(visited)

    return {
        "seeds": seeds,
        "nodes": [dict(data, id=n, ppr_score=round(scores.get(n, 0.0), 5)) for n, data in sub.nodes(data=True)],
        "edges": [dict(data, source=u, target=v) for u, v, data in sub.edges(data=True)],
    }
