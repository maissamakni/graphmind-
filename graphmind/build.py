"""Étape 3 : assemble les résultats de tous les extracteurs en un graphe
NetworkX unique.

La déduplication est simple ici car chaque extracteur utilise déjà
make_id(chemin_relatif, nom_symbole) comme clé stable — deux extractions
émettant le même id fusionnent automatiquement via G.add_node (idempotent),
exactement comme observé dans build.py de graphify.
"""
from __future__ import annotations

import hashlib

import networkx as nx

from .schema import ExtractionResult


def _disambiguate_colliding_ids(results: list[ExtractionResult]) -> None:
    """Détecte les identifiants partagés par erreur entre DEUX FICHIERS
    DIFFÉRENTS (ex: "auth/login.py" et "auth_login.py" produisent tous les
    deux "auth_login_py" via make_id, car _slug() ne distingue pas "/" de
    "_"), et les différencie en "salant" l'id avec le chemin d'origine.

    Un id partagé par plusieurs nœuds du MÊME fichier n'est PAS une
    collision — c'est le comportement normal de déduplication (même
    fonction citée deux fois, etc.) et reste inchangé.
    """
    by_id: dict[str, set[str]] = {}
    for result in results:
        for node in result.nodes:
            by_id.setdefault(node.id, set()).add(node.source_file)

    # Ne garder que les ids réellement ambigus (>1 fichier d'origine distinct)
    ambiguous_ids = {nid for nid, files in by_id.items() if len(files) > 1}
    if not ambiguous_ids:
        return

    remap: dict[tuple[str, str], str] = {}  # (ancien_id, fichier_source) -> nouvel_id
    for nid in ambiguous_ids:
        source_files = by_id[nid]
        # Tentative "naïve" : ajouter le chemin complet à l'id
        naive = {sf: f"{nid}_{hashlib.sha1(sf.encode('utf-8')).hexdigest()[:6]}" for sf in source_files}
        for sf, new_id in naive.items():
            remap[(nid, sf)] = new_id

    # Applique le remap aux nœuds
    for result in results:
        for node in result.nodes:
            key = (node.id, node.source_file)
            if key in remap:
                node.id = remap[key]

    # Applique le remap aux relations — seulement quand on peut identifier
    # sans ambiguïté à quel fichier appartient l'extrémité concernée (le cas
    # le plus courant : une relation créée dans le MÊME fichier que le nœud
    # qu'elle référence, ex: "fichier --contains--> symbole_du_fichier").
    # Une relation cross-fichier vers un id resté ambigu est laissée telle
    # quelle : elle sera alors proprement ignorée par build_graph() (aucune
    # cible trouvée), plutôt que de risquer de la relier au mauvais nœud.
    for result in results:
        for edge in result.edges:
            src_key = (edge.source, edge.source_file)
            tgt_key = (edge.target, edge.source_file)
            if src_key in remap:
                edge.source = remap[src_key]
            if tgt_key in remap:
                edge.target = remap[tgt_key]


def build_graph(results: list[ExtractionResult]) -> nx.MultiDiGraph:
    """Construit le graphe final à partir de tous les résultats d'extraction.

    Utilise un MultiDiGraph, pas un simple DiGraph : avec un DiGraph,
    G.add_edge(u, v, ...) appelé deux fois avec des attributs DIFFÉRENTS
    (ex: "imports_from" puis "calls" entre les deux mêmes fichiers) écrase
    silencieusement la première relation — un vrai bug de perte de données.
    MultiDiGraph garde les deux comme deux arêtes parallèles distinctes,
    chacune avec sa propre relation/confiance — cohérent avec la façon dont
    graphify lui-même gère ce cas (cf. edge_data()/edge_datas() dans son
    code, qui tolèrent explicitement les arêtes parallèles).
    """
    _disambiguate_colliding_ids(results)

    graph = nx.MultiDiGraph()

    for result in results:
        for node in result.nodes:
            graph.add_node(node.id, **node.to_dict())

    for result in results:
        for edge in result.edges:
            if edge.source not in graph or edge.target not in graph:
                continue  # relation vers un nœud externe/non résolu : ignorée proprement
            graph.add_edge(edge.source, edge.target, **edge.to_dict())

    return graph
