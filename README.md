# graphmind — MVP

Assistant de codage IA basé sur un graphe de connaissances multimodal
(code + documentation + PDF + images + vidéo), conçu pour réduire le
nombre de tokens consommés par requête tout en gardant le contrôle total
sur les données sensibles.

Ce projet est le résultat de la phase de développement du stage, faisant
suite à l'étude comparative de Microsoft GraphRAG, HippoRAG2, LlamaIndex,
et à l'étude de cas pratique du projet open-source `graphify`.

## Principes d'architecture

- **AST/tree-sitter pour le code** — aucun appel LLM, confiance `EXTRACTED`.
  **16 langages** (`extractors/code/`) : Python, JavaScript, TypeScript,
  React JSX/TSX, Java, C, C++, C#/.NET, Go, Rust, PHP, Kotlin, Swift,
  Dart, SQL, Scala, PowerShell — via un walker AST générique (`base.py`)
  paramétré par un `LanguageSpec` par langage (noms de nœuds tree-sitter
  réels, vérifiés empiriquement en parsant du code réel, jamais devinés).
  Trois mécanismes optionnels du walker couvrent les structures
  grammaticales moins courantes découvertes en le faisant : nom de
  définition personnalisable (Go, C/C++), corps de fonction porté par le
  nœud frère suivant plutôt que par ses enfants (Dart), "réouverture"
  d'un type déjà déclaré plutôt que création d'un doublon (`impl Type` en
  Rust), et rattachement par type récepteur plutôt que par imbrication
  syntaxique (méthodes Go, déclarées hors du struct). Un nouveau langage
  s'ajoute par un seul fichier
  `<langage>_spec.py`, sans toucher au walker.
- **LLM réservé au contenu non structuré** (PDF, images, vidéo) — jamais pour le code.
- **Sécurité par fichier, pas par projet** (`security.py`) : chaque fichier est
  arbitré individuellement (local via Ollama si sensible, externe sinon).
- **Labels de confiance** `EXTRACTED` / `INFERRED` / `AMBIGUOUS` sur chaque relation.
- **MultiDiGraph** : plusieurs relations distinctes entre les deux mêmes nœuds
  (ex: `imports_from` ET `calls`) sont toutes préservées — un simple `DiGraph`
  aurait silencieusement écrasé l'une par l'autre.
- **Pondération par confiance** (`graph_utils.py`) : le graphe est "aplati" en
  simple/non-orienté pour le clustering et la requête, chaque arête pondérée
  selon la fiabilité des relations qu'elle regroupe (EXTRACTED > INFERRED > AMBIGUOUS).
- **Clustering hiérarchique à 2 niveaux** (`community` fin + `community_group`
  large) via l'algorithme de Leiden pondéré, avec repli automatique sur la
  modularité gloutonne de NetworkX si `python-igraph`/`leidenalg` sont absents.
- **Démarrage à chaud du clustering** : si un clustering précédent existe
  (`graph.json` déjà présent), Leiden repart de cette partition plutôt que
  de zéro — convergence plus rapide, et surtout des identifiants de
  communauté **stables** d'un build à l'autre.
- **Avertissement de taille** (`cluster.LARGE_GRAPH_NODE_THRESHOLD`, 5000
  nœuds par défaut) : au-delà de ce seuil, un message explicite recommande
  `build --no-cluster` + `graphmind cluster` ponctuel.
- **Nommage sémantique des communautés** : un appel LLM par communauté (pas
  par fichier) génère un nom descriptif ("Account Auth Flow"), avec repli
  sur le nom mécanique si aucun backend disponible. Gestion explicite du
  429 (rate limit Groq) : nouvelle tentative en respectant `Retry-After`,
  plus un délai préventif entre appels consécutifs.
- **Résolution cross-fichier** : appels directs ET appels de méthode
  (`objet.methode()`), avec garde anti-ambiguïté — étendue aux **imports**
  non résolus par le chemin de fichier (`raw_imports`), résolus par
  correspondance de nom de symbole sur tout le corpus (corrige
  concrètement PHP/Kotlin/Scala, dont les namespaces ne suivent pas
  forcément le chemin de fichier).
- **Résolution des collisions d'identifiants** : deux fichiers différents
  dont les chemins produiraient accidentellement le même identifiant sont
  automatiquement différenciés (salage par hash du chemin d'origine).
- **Résolution cross-modale à trois niveaux, du plus certain au plus coûteux** :
  1. **Exacte** (backticks, extraction LLM, lecture visuelle de code affiché)
     — un vrai nœud de fonction est créé avec ses relations réelles.
  2. **Approximative** (`ids.fuzzy_find_symbol`, sans dépendance
     supplémentaire) : rattrape les fautes de frappe (ex: "email_service"
     mentionné alors que le vrai fichier est "email_sercice") — `AMBIGUOUS`.
  3. **Sémantique en dernier recours, GROUPÉE** (`llm.semantic_link_batch`) :
     un appel LLM regroupant TOUS les concepts non résolus d'un même
     fichier (pas un appel par concept) demande une correspondance PAR LE
     SENS (ex: "paiement" ↔ "billing") — le nom retourné doit correspondre
     EXACTEMENT à un symbole réel, sinon rejeté ; `AMBIGUOUS`.
- **Vidéo à deux sources indépendantes** : transcription audio locale
  (faster-whisper) ET extraction d'images clés (PyAV) pour lire du contenu
  visuel même sans narration.
- **Requête par Personalized PageRank** (comme HippoRAG2), restreinte aux
  composantes connexes contenant les graines — évite qu'un résidu numérique
  de nœuds sans rapport ne pollue la réponse.
- **Réponse hiérarchique** : `_build_context()` organise la réponse en deux
  sections explicites — "faits de code certains" et "contexte documentaire
  associé" — exploitant la hiérarchie document/image/vidéo → concept →
  code déjà présente dans le graphe, plutôt qu'une liste plate.
- **Cache d'extraction incrémental** (`cache.py`) : seuls les fichiers
  nouveaux ou modifiés sont réellement (re)traités. Un échec d'extraction
  n'est **jamais** mis en cache.
- **Construction et clustering découplés** (`build --no-cluster` +
  `graphmind cluster` séparée).
- **Vérification légère** (`graphmind status`).
- **Configuration centralisée** (`graphmind.toml` optionnel, `config.py`) :
  mots-clés sensibles, dossiers ignorés, résolutions de clustering, modèles
  LLM — personnalisables sans toucher au code (`graphmind init-config`).
- **Journalisation** (`logging_config.py`) : `stdout` reste toujours pur
  (uniquement la réponse de `query` ou le JSON de `status`) ; les logs de
  progression vont sur `stderr`, avec `-v`/`-q`/`GRAPHMIND_LOG_LEVEL`.
- **Intégration aux assistants IA** : skills pour Claude Code, Blackbox AI
  et GitHub Copilot, avec garde-fous contre la lecture directe du graphe.

## Installation

```bash
pip install -r requirements.txt
```

Optionnel selon les besoins :
```bash
pip install faster-whisper   # transcription audio + extraction de frames vidéo (installe aussi 'av')
pip install anthropic        # backend LLM externe (Claude)
pip install openai           # backend LLM externe (GPT)
pip install pytest           # tests automatisés
# Groq ne nécessite AUCUN paquet supplémentaire (requête HTTP directe)
```

## Configuration des clés (fichier .env recommandé)

Crée un fichier `.env` à la racine du projet (jamais versionné) :
```
GROQ_API_KEY=ta_cle_groq
```
Chargé automatiquement au démarrage, avant toute autre logique. Ordre de
priorité si plusieurs backends configurés : `ANTHROPIC_API_KEY` >
`OPENAI_API_KEY` > `GROQ_API_KEY` > `GRAPHMIND_OLLAMA_MODEL`.

⚠️ Le catalogue de modèles Groq change fréquemment — vérifier la liste
actuelle via :
```powershell
Invoke-WebRequest -Uri "https://api.groq.com/openai/v1/models" -Headers @{Authorization = "Bearer $env:GROQ_API_KEY"}
```

## Usage

```bash
# Construire le graphe (avec clustering complet)
python -m graphmind.cli build ./mon-projet --out ./mon-projet-graphmind-out

# Construction rapide sans clustering (gros projet, mise à jour fréquente)
python -m graphmind.cli build ./mon-projet --out ./mon-projet-graphmind-out --no-cluster
python -m graphmind.cli cluster --out ./mon-projet-graphmind-out

# Vérifier si une reconstruction est nécessaire, sans rien extraire
python -m graphmind.cli status ./mon-projet --out ./mon-projet-graphmind-out

# Interroger le graphe déjà construit
python -m graphmind.cli query "comment fonctionne le login ?" --out ./mon-projet-graphmind-out

# Générer un exemple de configuration
python -m graphmind.cli init-config ./mon-projet

# Verbosité
python -m graphmind.cli -v build ...   # verbeux (DEBUG)
python -m graphmind.cli -q build ...   # silencieux (WARNING/ERROR)
```

## Tests automatisés

```bash
pip install pytest
python -m pytest tests/ -v
```
95 tests couvrant en priorité les modules à l'origine des bugs réellement
rencontrés pendant le développement (résolution des collisions
d'identifiants, préservation des relations parallèles via MultiDiGraph,
cache qui ne retient jamais un échec, restriction du PPR aux composantes
connexes, stabilité du warm start, rejet des hallucinations LLM).

## Intégration à un assistant IA (Claude Code / Blackbox AI / Copilot)

Trois skills sont fournis (livrés séparément) :
- `.claude/skills/graphmind/SKILL.md` — Claude Code
- `.blackbox/skills/graphmind/SKILL.md` — Blackbox AI
- `.github/copilot-instructions.md` — GitHub Copilot

Une fois copiés à la racine de l'espace de travail ouvert dans l'éditeur
(vérifier lequel — Claude Code utilise la racine du dépôt Git le plus
proche, pas nécessairement le dossier ouvert dans l'éditeur), l'assistant
répond aux questions sur l'architecture en interrogeant le graphe déjà
construit, avec un garde-fou contre la lecture directe du graphe et une
limite de reformulations avant d'admettre qu'une fonctionnalité n'existe
pas dans le code analysé.



## Structure du projet

```
graphmind/
├── schema.py          # Node, Edge, Confidence, Modality, ExtractionResult
├── ids.py             # identifiants stables + fuzzy_find_symbol
├── security.py        # arbitrage local/externe par fichier
├── envfile.py         # chargement du fichier .env
├── config.py           # configuration centralisée (graphmind.toml optionnel)
├── logging_config.py    # journalisation (stdout pur, logs sur stderr)
├── cache.py              # cache d'extraction — ne met JAMAIS en cache un échec
├── graph_utils.py         # graphe pondéré par confiance (clustering + requête)
├── llm.py                  # interface LLM unifiée : extraction texte/image,
│                              nommage de communautés, semantic_link_batch,
│                              réponse finale — seul point d'appel IA
├── detect.py                # détection et classification par modalité
├── extractors/
│   ├── code/                   # extraction multi-langages (16 langages)
│   │   ├── base.py                # walker AST générique, paramétré par LanguageSpec
│   │   ├── python_spec.py          # + java_spec, php_spec, csharp_spec,
│   │   │                             javascript_spec, typescript_spec, tsx_spec,
│   │   │                             c_spec, cpp_spec, go_spec, rust_spec,
│   │   │                             kotlin_spec, swift_spec, dart_spec,
│   │   │                             sql_spec, scala_spec, powershell_spec
│   ├── text_doc.py              # titres + backticks + LLM enrichi + batch
│   ├── pdf_doc.py                 # pypdf + extraction sémantique LLM
│   ├── image.py                    # extraction structurée via vision + batch
│   └── video.py                     # audio (faster-whisper) + frames (PyAV)
├── build.py                    # MultiDiGraph + résolution des collisions
├── cluster.py                    # clustering hiérarchique Leiden + warm start
├── query.py                        # PPR restreint aux composantes connexes
├── export.py                         # graph.json + graph.html + REPORT.md
└── cli.py                              # build / cluster / status / query /
                                           init-config, contexte hiérarchique

tests/              # suite pytest (95 tests)
```
