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
- **Nommage sémantique des communautés** : un appel LLM par communauté (pas
  par fichier) génère un nom descriptif ("Account Auth Flow"), avec repli
  sur le nom mécanique (nœud le plus connecté) si aucun backend disponible.
- **Résolution cross-fichier** : appels directs ET appels de méthode
  (`objet.methode()`), avec garde anti-ambiguïté (un nom qui correspond à
  plusieurs définitions n'est jamais résolu au hasard).
- **Résolution des collisions d'identifiants** : deux fichiers différents
  dont les chemins produiraient accidentellement le même identifiant sont
  automatiquement différenciés (salage par hash du chemin d'origine).
- **Résolution cross-modale** : mentions de symboles de code dans la
  documentation (backticks), et surtout **lecture visuelle de code affiché**
  dans une image ou une vidéo (capture d'écran) — un vrai nœud de fonction
  est créé avec ses relations réelles, pas une simple légende en prose.
- **Vidéo à deux sources indépendantes** : transcription audio locale
  (faster-whisper) ET extraction d'images clés (PyAV) pour lire du contenu
  visuel même sans narration.
- **Requête par Personalized PageRank** (comme HippoRAG2), restreinte aux
  composantes connexes contenant les graines — évite qu'un résidu numérique
  de nœuds sans rapport ne pollue la réponse (bug rencontré et corrigé).
- **Réponse en langage naturel**, jamais de JSON brut — génération via LLM
  ou résumé déterministe si aucun backend.
- **Cache d'extraction incrémental** (`cache.py`) : seuls les fichiers
  nouveaux ou modifiés sont réellement (re)traités. Un échec d'extraction
  n'est **jamais** mis en cache — une correction de bug ou une clé enfin
  valide permet une nouvelle tentative automatique au prochain `build`.
- **Construction et clustering découplés** (`build --no-cluster` +
  `graphmind cluster` séparée) : sur un gros projet, on peut mettre à jour
  le graphe rapidement sans payer à chaque fois le coût du recalcul complet
  des communautés (limite structurelle partagée avec graphify lui-même).
- **Vérification légère** (`graphmind status`) : dit en un instant si une
  reconstruction est nécessaire, sans rien extraire.
- **Intégration aux assistants IA** : skills prêts à l'emploi pour Claude Code
  et Blackbox AI, avec garde-fous contre la lecture directe du graphe/des
  fichiers sources, et une limite de reformulations avant d'admettre
  qu'une fonctionnalité n'existe pas dans le code analysé.

## Installation

```bash
pip install -r requirements.txt
```

Optionnel selon les besoins :
```bash
pip install faster-whisper   # transcription audio + extraction de frames vidéo (installe aussi 'av')
pip install anthropic        # backend LLM externe (Claude)
pip install openai           # backend LLM externe (GPT)
# Groq ne nécessite AUCUN paquet supplémentaire (requête HTTP directe)
```

## Configuration des clés (fichier .env recommandé)

Crée un fichier `.env` à la racine du projet (jamais versionné, voir
`.gitignore`) :

```
GROQ_API_KEY=ta_cle_groq
```

Chargé automatiquement au démarrage (`envfile.py`), avant toute autre
logique — peu importe quel outil lance la commande (terminal manuel,
Claude Code, Blackbox AI...).

Backends disponibles, par ordre de priorité si plusieurs sont configurés en
même temps : `ANTHROPIC_API_KEY` > `OPENAI_API_KEY` > `GROQ_API_KEY` >
`GRAPHMIND_OLLAMA_MODEL`. Sans aucune variable définie, l'extraction
sémantique des fichiers non-code est simplement ignorée — jamais d'erreur
bloquante.

⚠️ Le catalogue de modèles Groq change fréquemment (plusieurs dépréciations
rencontrées pendant le développement) — si un modèle cesse de fonctionner,
vérifier la liste actuelle via :
```powershell
Invoke-WebRequest -Uri "https://api.groq.com/openai/v1/models" -Headers @{Authorization = "Bearer $env:GROQ_API_KEY"}
```

## Usage

Construire le graphe (avec clustering complet) :
```bash
python -m graphmind.cli build ./mon-projet --out ./mon-projet-graphmind-out
```

Construction rapide sans clustering (gros projet, mise à jour fréquente) :
```bash
python -m graphmind.cli build ./mon-projet --out ./mon-projet-graphmind-out --no-cluster
python -m graphmind.cli cluster --out ./mon-projet-graphmind-out   # à relancer ponctuellement
```

Vérifier si une reconstruction est nécessaire, sans rien extraire :
```bash
python -m graphmind.cli status ./mon-projet --out ./mon-projet-graphmind-out
```

Interroger le graphe déjà construit (réponse en langage naturel) :
```bash
python -m graphmind.cli query "comment fonctionne le login ?" --out ./mon-projet-graphmind-out
```

## Intégration à un assistant IA (Claude Code / Blackbox AI)

Deux dossiers de "skill" sont fournis (livrés séparément) :
- `.claude/skills/graphmind/SKILL.md` — pour Claude Code
- `.blackbox/skills/graphmind/SKILL.md` — pour Blackbox AI (extension VS Code)

Une fois copiés à la racine de l'espace de travail, l'assistant répond aux
questions sur l'architecture du code en interrogeant le graphe déjà
construit, au lieu de relire l'intégralité des fichiers sources — avec un
garde-fou explicite contre la lecture directe de `graph.json` et une limite
de reformulations avant de signaler clairement qu'une fonctionnalité
n'existe pas dans le code analysé.

## Périmètre de ce MVP (limitations assumées)

- Extraction AST : **Python uniquement**. `detect.py` reconnaît déjà les
  extensions JS/TS (affichées comme "pas encore supporté" dans les logs),
  mais l'extracteur réel reste à écrire, sur le modèle de `code_python.py`.
  PHP et les autres langages ne sont pas encore reconnus du tout.
- La génération de légende/extraction d'image nécessite un modèle
  réellement capable de vision (tous les modèles ne le sont pas, et le
  catalogue change souvent chez certains fournisseurs).
- Le clustering (Leiden comme la modularité gloutonne) reste un **recalcul
  complet à chaque fois** — pas de mise à jour incrémentale des
  communautés. Limite structurelle partagée avec graphify lui-même (son
  propre journal affiche "Re-clustering..." à chaque mise à jour).
- La liaison cross-modale entre un document texte et le code repose sur une
  correspondance de nom exacte (backticks ou extraction LLM) — pas de
  similarité sémantique approximative (embeddings), pour ne jamais créer de
  lien hasardeux.

## Structure du projet

```
graphmind/
├── schema.py        # Node, Edge, Confidence, Modality, ExtractionResult
│                       (avec extraction_incomplete pour le cache)
├── ids.py            # génération d'identifiants stables (clé fichier+symbole)
├── security.py       # arbitrage local/externe par fichier
├── envfile.py         # chargement du fichier .env
├── cache.py            # cache d'extraction par empreinte de contenu —
│                          ne met JAMAIS en cache un échec
├── graph_utils.py       # conversion du graphe multi-relationnel en graphe
│                           simple pondéré par confiance (clustering + requête)
├── llm.py                # interface LLM unifiée (Anthropic/OpenAI/Groq/Ollama) :
│                            extraction sémantique texte/image, description
│                            d'image, nommage de communautés, réponse finale
├── detect.py              # détection et classification par modalité
├── extractors/
│   ├── code_python.py       # AST tree-sitter : appels directs + méthodes,
│   │                           imports résolus vers le vrai fichier, raw_calls
│   ├── text_doc.py           # titres + backticks (EXTRACTED) + extraction
│   │                            LLM enrichie du texte complet (INFERRED)
│   ├── pdf_doc.py             # pypdf + extraction sémantique LLM
│   ├── image.py                # métadonnées + extraction STRUCTURÉE
│   │                              (entités/relations) via modèle de vision,
│   │                              capable de lire du code affiché à l'écran
│   └── video.py                 # transcription audio (faster-whisper) +
│                                    extraction visuelle de frames (PyAV),
│                                    deux sources indépendantes
├── build.py                # assemble en MultiDiGraph + résout les
│                              collisions d'identifiants entre fichiers
├── cluster.py                # clustering hiérarchique Leiden pondéré
│                                (2 niveaux), repli modularité gloutonne
├── query.py                   # requête -> sous-graphe ciblé (Personalized
│                                 PageRank, restreint aux composantes connexes)
├── export.py                   # graph.json + graph.html (communautés
│                                  nommées, taille de nœud par degré,
│                                  recherche, inspection) + REPORT.md
└── cli.py                       # orchestration : build / cluster / status /
                                    query, résolution cross-fichier, cache
```
