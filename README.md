# graphmind — MVP

Assistant de codage IA basé sur un graphe de connaissances multimodal
(code + documentation + PDF + images + vidéo), conçu pour réduire le
nombre de tokens consommés par requête tout en gardant le contrôle total
sur les données sensibles.

Ce projet est le résultat de la phase de développement du stage, faisant
suite à l'étude comparative de Microsoft GraphRAG, HippoRAG2, LlamaIndex,
et à l'étude de cas pratique du projet open-source `graphify`.

## Principes d'architecture (voir le rapport de recherche pour le détail)

- **AST/tree-sitter pour tout le code** — aucun appel LLM, confiance `EXTRACTED`.
- **LLM réservé au contenu non structuré** (PDF, images, vidéo) — jamais pour le code.
- **Sécurité par fichier, pas par projet** (`security.py`) : chaque fichier est
  arbitré individuellement (local via Ollama si sensible, externe sinon),
  au lieu d'un choix de backend global figé.
- **Labels de confiance** `EXTRACTED` / `INFERRED` / `AMBIGUOUS` sur chaque relation.
- **Résolution cross-modale** : les mentions de symboles de code (entre backticks)
  dans la documentation sont automatiquement reliées au nœud de code réel —
  c'est le mécanisme central différenciant de cette architecture.
- **Séparation stricte indexation / requête** : `query.py` ne renvoie jamais le
  graphe complet, seulement un sous-graphe ciblé (BFS borné en profondeur).

## Installation

```bash
pip install -r requirements.txt
```

Optionnel selon les besoins :
```bash
pip install faster-whisper   # transcription vidéo/audio locale
pip install anthropic        # backend LLM externe (Claude)
pip install openai           # backend LLM externe (GPT)
```

## Usage

Construire le graphe :
```bash
python -m graphmind.cli build ./mon-projet --out ./mon-projet-out
```

Interroger le graphe déjà construit :
```bash
python -m graphmind.cli query "comment fonctionne le login ?" --out ./mon-projet-out
```

Configurer un backend LLM (pour PDF/images/vidéo) :
```bash
export ANTHROPIC_API_KEY=...        # backend externe
# ou
export GRAPHMIND_OLLAMA_MODEL=llama3   # backend 100% local
```
Sans aucune variable définie, l'extraction sémantique des fichiers non-code
est simplement ignorée (comme pour un corpus 100% code) — jamais d'erreur bloquante.

## Périmètre de ce MVP (limitations assumées)

- Extraction AST : **Python uniquement** pour l'instant (architecture prévue
  pour ajouter facilement JS/TS/Java sur le même modèle que `code_python.py`).
- Extraction sémantique image/PDF/vidéo : squelette fonctionnel, la génération
  réelle de légendes d'image n'est pas encore branchée (`extractors/image.py`).
- Clustering : modularité gloutonne de NetworkX (pas Leiden), pour rester sans
  dépendance lourde supplémentaire.
- Requête : BFS simple (pas de propagation par score type PPR) — piste
  d'amélioration documentée dans le rapport de recherche.

## Structure du projet

```
graphmind/
├── schema.py       # Node, Edge, Confidence, Modality — le format universel
├── ids.py          # génération d'identifiants stables (clé fichier+symbole)
├── security.py     # arbitrage local/externe par fichier
├── llm.py          # interface LLM unifiée (le SEUL point d'appel réseau)
├── detect.py       # détection et classification par modalité
├── extractors/
│   ├── code_python.py   # AST tree-sitter, confiance EXTRACTED
│   ├── text_doc.py       # Markdown + liaison cross-modale
│   ├── pdf_doc.py        # pypdf + extraction sémantique LLM
│   ├── image.py          # métadonnées + légende LLM (squelette)
│   └── video.py          # transcription locale (faster-whisper) + LLM
├── build.py        # assemble tout en un graphe NetworkX
├── cluster.py       # détection de communautés
├── query.py         # requête -> sous-graphe ciblé (BFS)
├── export.py         # graph.json + graph.html + REPORT.md
└── cli.py             # point d'entrée (build / query)
```
