# Instructions pour Claude Code sur ce projet

Ce projet dispose d'un skill dédié : `graphmind` (voir `.claude/skills/graphmind/SKILL.md`).

**Règle impérative** : pour toute question sur l'architecture du code, le
fonctionnement d'une fonction, ou les relations entre fichiers/classes/fonctions
d'un projet déjà analysé par graphmind (présence d'un dossier `*-graphmind-out`
contenant un `graph.json`), utilise SYSTÉMATIQUEMENT le skill `graphmind` —
c'est-à-dire exécute `python -m graphmind.cli query "<question>" --out <dossier>-graphmind-out`
et renvoie sa réponse, plutôt que de lire directement les fichiers source.

Consulte `.claude/skills/graphmind/SKILL.md` pour les instructions détaillées.
