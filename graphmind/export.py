"""Étape 7 : export des livrables finaux."""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from . import llm

# Palette cyclique par communauté (assez de couleurs distinctes avant répétition)
_COMMUNITY_PALETTE = [
    "#4f8ef7", "#f7924f", "#e0554f", "#4fd68c", "#c084f5",
    "#f5d24f", "#4fc4f7", "#f77fb8", "#8cf74f", "#9d7cf7",
]

_MODALITY_ICON = {
    "code": "●", "document": "●", "pdf": "●", "image": "●", "video": "●", "concept": "●",
}

_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>graphmind</title>
<script src="https://cdn.jsdelivr.net/npm/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
  * {{ box-sizing: border-box; }}
  html,body {{ margin:0; height:100%; font-family: -apple-system, Segoe UI, sans-serif; background:#0b0d12; color:#e6e6e6; }}
  #app {{ display:flex; height:100%; width:100%; }}
  #network {{ flex:1; height:100%; }}
  #sidebar {{
    width: 300px; height:100%; background:#12141c; border-left:1px solid #23262f;
    padding:16px; overflow-y:auto; font-size:13px;
  }}
  #sidebar h3 {{ font-size:11px; letter-spacing:0.06em; color:#8a8f9c; margin:18px 0 8px; text-transform:uppercase; }}
  #search {{
    width:100%; padding:8px 10px; border-radius:6px; border:1px solid #2a2e3a;
    background:#1a1d27; color:#e6e6e6; font-size:13px;
  }}
  .community-row {{ display:flex; align-items:center; gap:8px; padding:4px 0; cursor:pointer; }}
  .dot {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; }}
  .community-label {{ flex:1; }}
  .community-count {{ color:#6a6f7c; }}
  #node-info {{ color:#8a8f9c; font-style:italic; }}
  #node-info .field {{ margin-bottom:6px; }}
  #node-info .field b {{ color:#e6e6e6; font-style:normal; display:block; font-size:11px; text-transform:uppercase; color:#6a6f7c; }}
  #footer {{ position:absolute; bottom:0; left:0; right:300px; padding:8px 14px; font-size:12px; color:#6a6f7c; background:#0b0d1299; }}
  #select-all-row {{ display:flex; align-items:center; gap:8px; padding:4px 0; }}
</style></head>
<body>
<div id="app">
  <div id="network"></div>
  <div id="sidebar">
    <input id="search" type="text" placeholder="Rechercher un nœud..." />
    <h3>Nœud sélectionné</h3>
    <div id="node-info">Cliquez un nœud pour l'inspecter</div>
    <h3>Communautés</h3>
    <div id="select-all-row">
      <input type="checkbox" id="select-all" checked />
      <span>Tout afficher</span>
    </div>
    <div id="community-list"></div>
  </div>
</div>
<div id="footer"></div>
<script>
const graphData = {graph_json};
const communityInfo = {community_json};

const modColors = {{code:"#4f8ef7", document:"#f7924f", pdf:"#e0554f", image:"#4fd68c", video:"#c084f5", concept:"#6a6f7c"}};

function communityColor(c) {{
  if (communityInfo[c]) return communityInfo[c].color;
  return "#888";
}}

// Taille des nœuds proportionnelle au nombre de connexions (comme les
// "god nodes" de graphify) — un nœud très connecté (ex: une classe centrale
// comme "Account") se voit visuellement plus important qu'un nœud isolé.
const degreeCount = {{}};
graphData.edges.forEach(e => {{
  degreeCount[e.source] = (degreeCount[e.source] || 0) + 1;
  degreeCount[e.target] = (degreeCount[e.target] || 0) + 1;
}});
const BASE_SIZE = 10;
const MAX_SIZE = 45;
const SIZE_PER_EDGE = 4;
function nodeSize(id) {{
  const degree = degreeCount[id] || 0;
  return Math.min(BASE_SIZE + degree * SIZE_PER_EDGE, MAX_SIZE);
}}

const allNodes = graphData.nodes.map(n => ({{
  id: n.id,
  label: n.label,
  size: nodeSize(n.id),
  color: {{ background: communityColor(n.community), border: communityColor(n.community) }},
  title: n.modality + " — " + n.source_file + " (" + (degreeCount[n.id] || 0) + " connexions)",
  _raw: n,
}}));
const allEdges = graphData.edges.map((e, i) => ({{
  id: i, from: e.source, to: e.target, label: e.relation, arrows: "to",
  font: {{ size: 9, color: "#8a8f9c", strokeWidth: 0 }},
  color: {{ color: e.confidence === "EXTRACTED" ? "#3d4250" : "#7a5a2a", opacity: 0.7 }},
  _raw: e,
}}));

const nodes = new vis.DataSet(allNodes);
const edges = new vis.DataSet(allEdges);

const network = new vis.Network(document.getElementById("network"), {{nodes, edges}}, {{
  physics: {{ stabilization: true, barnesHut: {{ gravitationalConstant: -4000, springLength: 120 }} }},
  nodes: {{ shape: "dot", font: {{ color: "#e6e6e6", size: 13 }} }},
  interaction: {{ hover: true }},
}});

// --- Panneau d'information sur clic ---
network.on("click", function (params) {{
  const info = document.getElementById("node-info");
  if (params.nodes.length === 0) {{
    info.innerHTML = "Cliquez un nœud pour l'inspecter";
    info.classList.add("empty");
    return;
  }}
  const n = nodes.get(params.nodes[0])._raw;
  info.classList.remove("empty");
  info.innerHTML = `
    <div class="field"><b>Label</b>${{n.label}}</div>
    <div class="field"><b>Modalité</b>${{n.modality}}</div>
    <div class="field"><b>Fichier source</b>${{n.source_file}}</div>
    <div class="field"><b>Position</b>${{n.source_location || "—"}}</div>
    <div class="field"><b>Communauté</b>${{communityInfo[n.community] ? communityInfo[n.community].label : n.community}}</div>
  `;
}});

// --- Liste des communautés (sidebar) ---
const listEl = document.getElementById("community-list");
const hiddenCommunities = new Set();

Object.keys(communityInfo).sort((a,b) => communityInfo[b].count - communityInfo[a].count).forEach(cid => {{
  const info = communityInfo[cid];
  const row = document.createElement("div");
  row.className = "community-row";
  row.innerHTML = `
    <input type="checkbox" data-cid="${{cid}}" checked />
    <span class="dot" style="background:${{info.color}}"></span>
    <span class="community-label">${{info.label}}</span>
    <span class="community-count">${{info.count}}</span>
  `;
  listEl.appendChild(row);
}});

function applyFilters() {{
  const query = document.getElementById("search").value.trim().toLowerCase();
  const updates = allNodes.map(n => {{
    const communityHidden = hiddenCommunities.has(String(n._raw.community));
    const matchesSearch = !query || n.label.toLowerCase().includes(query);
    return {{ id: n.id, hidden: communityHidden || !matchesSearch }};
  }});
  nodes.update(updates);
}}

listEl.addEventListener("change", (ev) => {{
  const cid = ev.target.getAttribute("data-cid");
  if (!cid) return;
  if (ev.target.checked) hiddenCommunities.delete(cid); else hiddenCommunities.add(cid);
  document.getElementById("select-all").checked = hiddenCommunities.size === 0;
  applyFilters();
}});

document.getElementById("select-all").addEventListener("change", (ev) => {{
  hiddenCommunities.clear();
  if (!ev.target.checked) {{
    Object.keys(communityInfo).forEach(cid => hiddenCommunities.add(cid));
  }}
  listEl.querySelectorAll("input[type=checkbox]").forEach(cb => cb.checked = ev.target.checked);
  applyFilters();
}});

document.getElementById("search").addEventListener("input", applyFilters);

document.getElementById("footer").textContent =
  `${{graphData.nodes.length}} nœuds · ${{graphData.edges.length}} relations · ${{Object.keys(communityInfo).length}} communautés`;
</script>
</body></html>
"""


def _build_community_info(graph: nx.DiGraph) -> dict:
    """Pour chaque communauté : une couleur stable, un label représentatif
    et le nombre de nœuds.

    Le label est d'abord tenté via un nommage sémantique par LLM (un seul
    appel PAR COMMUNAUTÉ, pas par fichier — même principe que le résumé de
    communauté de Microsoft GraphRAG), à partir des labels des membres les
    plus connectés. Si aucun backend n'est disponible ou que l'appel échoue,
    on retombe sur le nom MÉCANIQUE (le nœud le plus connecté du groupe) —
    jamais d'erreur bloquante, jamais de communauté sans nom.
    """
    groups: dict[str, list[str]] = {}
    for node_id, data in graph.nodes(data=True):
        cid = str(data.get("community", "0"))
        groups.setdefault(cid, []).append(node_id)

    degrees = dict(graph.to_undirected().degree())
    backend = llm.resolve_backend(force_local=False)
    info: dict[str, dict] = {}
    for idx, (cid, members) in enumerate(sorted(groups.items(), key=lambda kv: int(kv[0]))):
        ranked_members = sorted(members, key=lambda n: degrees.get(n, 0), reverse=True)
        representative = ranked_members[0]
        mechanical_label = graph.nodes[representative].get("label", representative)

        top_labels = [str(graph.nodes[m].get("label", m)) for m in ranked_members[:8]]
        semantic_label = llm.name_community(top_labels, backend) if len(members) > 1 else None

        info[cid] = {
            "label": semantic_label or mechanical_label,
            "count": len(members),
            "color": _COMMUNITY_PALETTE[idx % len(_COMMUNITY_PALETTE)],
        }
    return info


def export_graph(graph: nx.DiGraph, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    data = nx.node_link_data(graph, edges="edges")
    graph_json = json.dumps(data, ensure_ascii=False)
    (out_dir / "graph.json").write_text(graph_json, encoding="utf-8")

    community_info = _build_community_info(graph)
    html = _HTML_TEMPLATE.format(
        graph_json=graph_json,
        community_json=json.dumps(community_info, ensure_ascii=False),
    )
    (out_dir / "graph.html").write_text(html, encoding="utf-8")

    report_lines = ["# Rapport du graphe\n"]
    report_lines.append(f"- Nœuds : {graph.number_of_nodes()}")
    report_lines.append(f"- Relations : {graph.number_of_edges()}\n")

    by_modality: dict[str, int] = {}
    for _, data_n in graph.nodes(data=True):
        mod = data_n.get("modality", "?")
        by_modality[mod] = by_modality.get(mod, 0) + 1
    report_lines.append("## Répartition par modalité")
    for mod, count in sorted(by_modality.items()):
        report_lines.append(f"- {mod} : {count}")

    degrees = sorted(graph.degree, key=lambda x: x[1], reverse=True)[:5]
    report_lines.append("\n## Nœuds les plus connectés")
    for node_id, degree in degrees:
        label = graph.nodes[node_id].get("label", node_id)
        report_lines.append(f"- {label} ({degree} connexions)")

    (out_dir / "REPORT.md").write_text("\n".join(report_lines), encoding="utf-8")
