# graphmind — MVP

Assistant de codage IA basé sur un graphe de connaissances multimodal
(code + documentation + PDF + images + vidéo), conçu pour réduire le
nombre de tokens consommés par requête tout en gardant le contrôle total
sur les données sensibles.

Ce projet est le résultat de la phase de développement du stage, faisant
suite à l'étude comparative de Microsoft GraphRAG, HippoRAG2, LlamaIndex,
et à l'étude de cas pratique du projet open-source `graphify`.

## Principes d'architecture (voir le rapport de recherche pour le détail)

- **AST/tree-sitter pour le code** — aucun appel LLM, confiance `EXTRACTED`.
- **LLM réservé au contenu non structuré** (PDF, images, vidéo) — jamais pour le code.
- **Sécurité par fichier, pas par projet** (`security.py`) : chaque fichier est
  arbitré individuellement (local via Ollama si sensible, externe sinon),
  au lieu d'un choix de backend global figé.
- **Labels de confiance** `EXTRACTED` / `INFERRED` / `AMBIGUOUS` sur chaque relation.
- **Résolution cross-modale** : les mentions de symboles de code (entre backticks)
  dans la documentation sont automatiquement reliées au nœud de code réel.
- **Résolution cross-fichier** : un appel `Account.find_by_email()` dans un
  fichier est relié à la vraie définition dans un autre fichier — y compris
  les appels de méthode (`objet.methode()`), pas seulement les appels directs —
  avec une garde anti-ambiguïté (un nom qui correspond à plusieurs définitions
  n'est jamais résolu au hasard).
- **Résolution des collisions d'identifiants** : deux fichiers différents dont
  les chemins produiraient accidentellement le même identifiant (ex :
  `auth/login.py` et `auth_login.py`) sont automatiquement différenciés
  (salage par hash du chemin d'origine), sans jamais fusionner deux entités
  distinctes par erreur.
- **Clustering par l'algorithme de Leiden** (comme Microsoft GraphRAG et
  graphify), avec repli automatique sur la modularité gloutonne de NetworkX
  si `python-igraph`/`leidenalg` ne sont pas installés — jamais d'erreur bloquante.
- **Requête par propagation de score (PPR)** : comme HippoRAG2, la requête
  identifie les nœuds-graines mentionnés dans la question, puis propage un
  score de pertinence à travers tout le graphe via l'algorithme Personalized
  PageRank (`nx.pagerank`) — un score continu qui décroît naturellement avec
  la distance, plutôt qu'une traversée en largeur (BFS) à profondeur fixe.
- **Génération réelle de légendes d'image** : les images sont envoyées à un
  modèle de vision (Claude, GPT-4o, Llama vision via Groq, ou LLaVA en local
  via Ollama) selon le backend arbitré par `security.py` ; la légende obtenue
  est ensuite reliée aux symboles de code déjà connus si elle les mentionne
  (même principe de liaison cross-modale que pour la documentation texte).
- **Séparation stricte indexation / requête** : `query.py` ne renvoie jamais le
  graphe complet, seulement un sous-graphe ciblé (les nœuds les mieux classés
  après propagation PPR).
- **Réponse en langage naturel** : la requête ne renvoie jamais de JSON brut —
  une vraie phrase est générée par le LLM configuré (Anthropic, OpenAI, Groq,
  Ollama), ou un résumé déterministe si aucun backend n'est disponible.
- **Intégration aux assistants IA** : skills prêts à l'emploi pour Claude Code
  et Blackbox AI (voir `.claude/skills/` et `.blackbox/skills/`), avec des
  garde-fous explicites contre la lecture directe du graphe ou des fichiers
  sources par l'assistant.

## Installation

```bash
pip install -r requirements.txt
```

Le clustering Leiden et la transcription vidéo sont des dépendances listées
dans `requirements.txt` — si l'installation d'un paquet compilé pose souci
sur ta machine, le programme continue de fonctionner avec un repli automatique
(modularité gloutonne pour le clustering, pas de transcription pour la vidéo).

Optionnel selon les besoins :
```bash
pip install anthropic        # backend LLM externe (Claude)
pip install openai           # backend LLM externe (GPT)
# Groq ne nécessite AUCUN paquet supplémentaire (requête HTTP directe)
```

## Configuration des clés (fichier .env recommandé)

Plutôt que de redéfinir une variable d'environnement à chaque session,
crée un fichier `.env` à la racine du projet (jamais versionné, voir
`.gitignore`) :

```
GROQ_API_KEY=ta_cle_groq
```

`graphmind` le charge automatiquement au démarrage (`envfile.py`), avant
toute autre logique — peu importe quel outil lance la commande (terminal
manuel, Claude Code, Blackbox AI...).

Backends disponibles, par ordre de priorité si plusieurs sont configurés
en même temps : `ANTHROPIC_API_KEY` > `OPENAI_API_KEY` > `GROQ_API_KEY` >
`GRAPHMIND_OLLAMA_MODEL`. Sans aucune variable définie, l'extraction
sémantique des fichiers non-code est simplement ignorée — jamais d'erreur
bloquante, comme pour un corpus 100% code.

## Usage

Construire le graphe :
```bash
python -m graphmind.cli build ./mon-projet --out ./mon-projet-graphmind-out
```

Interroger le graphe déjà construit (réponse en langage naturel) :
```bash
python -m graphmind.cli query "comment fonctionne le login ?" --out ./mon-projet-graphmind-out
```

## Intégration à un assistant IA (Claude Code / Blackbox AI)

Deux dossiers de "skill" sont fournis à la racine du projet :
- `.claude/skills/graphmind/SKILL.md` — pour Claude Code
- `.blackbox/skills/graphmind/SKILL.md` — pour Blackbox AI (extension VS Code)

Une fois copiés à la racine de ton espace de travail, l'assistant répond aux
questions sur l'architecture du code en interrogeant le graphe déjà construit
(`graphmind query`), au lieu de relire l'intégralité des fichiers sources à
chaque question — avec des garde-fous explicites contre la lecture directe
de `graph.json` ou des sources, et une limite de reformulations avant de
signaler clairement qu'une fonctionnalité n'existe pas dans le code analysé.

## Périmètre de ce MVP (limitations assumées)

- Extraction AST : **Python uniquement** pour l'instant. `detect.py` reconnaît
  déjà les extensions JS/TS (elles apparaissent dans les logs comme "pas
  encore supporté"), mais l'extracteur réel reste à écrire, sur le modèle de
  `extractors/code_python.py`. PHP et les autres langages ne sont pas encore
  reconnus du tout (à ajouter d'abord dans `detect.py`, puis un extracteur dédié).
- La génération de légende d'image nécessite un modèle réellement capable de
  vision (tous les modèles ne le sont pas) — vérifier que le modèle configuré
  supporte la vision avant d'attendre un résultat.

## Structure du projet

```
graphmind/
├── schema.py       # Node, Edge, Confidence, Modality — le format universel
├── ids.py          # génération d'identifiants stables (clé fichier+symbole)
├── security.py     # arbitrage local/externe par fichier
├── envfile.py      # chargement du fichier .env
├── llm.py          # interface LLM unifiée (Anthropic/OpenAI/Groq/Ollama)
├── detect.py       # détection et classification par modalité
├── extractors/
│   ├── code_python.py   # AST tree-sitter (Python), appels directs + méthodes,
│   │                       imports résolus vers le vrai fichier, raw_calls
│   │                       pour la résolution cross-fichier
│   ├── text_doc.py       # Markdown + liaison cross-modale
│   ├── pdf_doc.py        # pypdf + extraction sémantique LLM
│   ├── image.py          # métadonnées + légende générée par un modèle de
│   │                       vision (Claude/GPT-4o/Groq vision/LLaVA)
│   └── video.py          # transcription locale (faster-whisper) + LLM
├── build.py        # assemble tout en un graphe NetworkX + résout les
│                     collisions d'identifiants entre fichiers différents
├── cluster.py       # détection de communautés (Leiden, repli gloutonne)
├── query.py          # requête -> sous-graphe ciblé (Personalized PageRank)
├── export.py          # graph.json + graph.html (communautés, recherche,
│                         inspection de nœud) + REPORT.md
└── cli.py              # orchestration : build / query, résolution
                          cross-fichier des appels, génération de réponse
```
