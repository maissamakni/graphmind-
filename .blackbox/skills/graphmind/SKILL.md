---
name: graphmind
description: "À utiliser pour TOUTE question sur l'architecture du code, le fonctionnement d'une fonction, les relations entre fichiers/classes/fonctions (qui appelle quoi, qui importe quoi), ou la structure générale d'un projet analysé par graphmind. Déclencheur : dès qu'un dossier '*-graphmind-out' contenant un fichier graph.json existe dans le projet. Ne JAMAIS lire directement les fichiers source (.py, .js...) pour répondre à ces questions — toujours passer par la commande graphmind query ci-dessous, qui interroge un graphe de connaissances déjà construit, au lieu de relire tout le code à chaque question."
---

# Skill graphmind

## Instructions

1. Vérifie si un dossier se terminant par `-graphmind-out` existe à la racine
   du projet ou dans un dossier voisin (ex : `customer-system-graphmind-out`).
   S'il n'existe pas, dis à l'utilisateur de d'abord lancer :
   `python -m graphmind.cli build <dossier_projet> --out <dossier_projet>-graphmind-out`

2. Si le dossier existe, réponds à la question en exécutant EXACTEMENT cette
   commande (adapte uniquement le texte de la question et le chemin --out) :

   ```
   python -m graphmind.cli query "<la question exacte de l'utilisateur>" --out <chemin_vers_le_dossier>-graphmind-out
   ```

3. Renvoie la réponse produite par cette commande à l'utilisateur, sans la
   reformuler à partir d'une lecture séparée des fichiers sources.

4. Ne lis JAMAIS le contenu des fichiers `.py`/`.js`/etc. du projet analysé
   pour répondre à ces questions — la commande `graphmind query` a déjà tout
   le contexte nécessaire dans le graphe (`graph.json`), et l'objectif de cet
   outil est justement de réduire le nombre de tokens en évitant de relire
   l'intégralité du code à chaque question.

5. N'ouvre JAMAIS `graph.json` toi-même (que ce soit avec `python -c`, `cat`,
   un script improvisé, ou tout autre moyen) pour chercher une réponse
   manuellement. C'est exactement le contournement que cet outil existe pour
   éviter — si `graphmind query` ne donne pas de réponse satisfaisante, la
   bonne réaction est de reformuler la question (voir point 6), jamais de
   lire le graphe brut par un autre chemin.

6. Si la première réponse de `graphmind query` semble vide, incomplète ou
   hors sujet, tu peux reformuler la question et relancer la commande —
   MAIS au maximum 2 reformulations (donc 3 tentatives au total). Si après
   ces 3 tentatives aucune réponse satisfaisante n'est obtenue, arrête-toi
   et dis clairement à l'utilisateur : "Cette fonctionnalité ne semble pas
   présente dans le code analysé (aucune fonction correspondante trouvée
   dans le graphe)." Ne cherche jamais la réponse par un autre moyen que
   `graphmind query`.

## Exemples

**Utilisateur** : "comment fonctionne le login ?"
**Action** : exécuter
`python -m graphmind.cli query "comment fonctionne le login ?" --out customer-system-graphmind-out`
puis renvoyer la réponse obtenue telle quelle.

**Utilisateur** : "quelle fonction appelle Transaction ?"
**Action** : exécuter
`python -m graphmind.cli query "quelle fonction appelle Transaction ?" --out customer-system-graphmind-out`
