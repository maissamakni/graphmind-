"""Politique de sécurité : décide, fichier par fichier, si l'extraction
sémantique doit rester 100% locale ou peut passer par un LLM externe.

C'est le point central qui justifie de ne pas réutiliser une solution
existante telle quelle (cf. rapport de recherche, section 2) : au lieu
d'un choix de backend global et figé, chaque fichier est arbitré
individuellement selon sa sensibilité.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SecurityDecision:
    path: Path
    force_local: bool
    reason: str


class SecurityPolicy:
    """Règles simples et explicites, faciles à auditer par un humain.

    - Un dossier dont le nom contient un mot sensible (config, secret,
      confidentiel, private, credentials...) force le traitement local.
    - Un fichier contenant un motif ressemblant à un secret (clé API,
      mot de passe en clair) force aussi le traitement local.
    - Sinon, le backend par défaut choisi par l'utilisateur s'applique.
    """

    SENSITIVE_DIR_KEYWORDS = (
        "secret", "secrets", "confidentiel", "confidential", "private",
        "credentials", "credential", "internal", "interne", "rh", "hr",
    )

    # Motifs volontairement simples ; à enrichir selon les besoins réels
    # de l'entreprise (numéros de contrat, identifiants clients, etc.).
    SECRET_PATTERNS = (
        re.compile(r"-----BEGIN (RSA )?PRIVATE KEY-----"),
        re.compile(r"api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}"),
        re.compile(r"password\s*[:=]\s*['\"][^'\"]{4,}"),
    )

    def __init__(self, extra_sensitive_dirs: list[str] | None = None):
        # Permet à l'utilisateur d'ajouter SES PROPRES mots-clés sensibles
        # (spécifiques à son entreprise, ex: "brevet", "acquisition") en plus
        # de la liste par défaut ci-dessus — sans avoir à modifier ce fichier.
        self.extra_sensitive_dirs = [d.lower() for d in (extra_sensitive_dirs or [])]

    # Vérifie si un des DOSSIERS PARENTS du fichier (pas le fichier lui-même)
    # correspond à un mot-clé sensible. Ex : "projet/secrets/config.py" est
    # détecté ici via le dossier "secrets", même si "config.py" seul ne
    # contient rien de suspect. Combine la liste par défaut ET celle
    # fournie par l'utilisateur à l'instanciation.
    def _dir_is_sensitive(self, path: Path) -> bool:
        parts = [p.lower() for p in path.parts]
        keywords = set(self.SENSITIVE_DIR_KEYWORDS) | set(self.extra_sensitive_dirs)
        return any(part in keywords for part in parts)

    # Lit le DÉBUT du contenu du fichier (200 Ko max, pour ne jamais ralentir
    # le scan sur un gros fichier) et vérifie s'il contient un motif qui
    # RESSEMBLE à un secret (clé API, mot de passe, clé privée RSA...).
    # Retourne False (jamais d'exception) si le fichier est illisible —
    # la sécurité ne doit jamais faire planter tout le pipeline.
    def _content_looks_sensitive(self, path: Path, max_bytes: int = 200_000) -> bool:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:max_bytes]
        except OSError:
            return False
        return any(pattern.search(text) for pattern in self.SECRET_PATTERNS)

    # Le POINT D'ENTRÉE de toute la classe — c'est la seule méthode appelée
    # depuis l'extérieur (cli.py). Applique les deux vérifications dans
    # l'ordre (dossier d'abord, car moins coûteux à vérifier ; contenu
    # ensuite, uniquement sur les extensions de fichiers texte pertinentes)
    # et retourne toujours une décision claire avec sa justification —
    # jamais un simple booléen sans explication, pour rester auditable.
    def decide(self, path: Path) -> SecurityDecision:
        if self._dir_is_sensitive(path):
            return SecurityDecision(path, True, "dossier marqué sensible")
        if path.suffix in (".md", ".txt", ".py", ".js", ".ts", ".json", ".yaml", ".yml"):
            if self._content_looks_sensitive(path):
                return SecurityDecision(path, True, "motif de secret détecté dans le contenu")
        return SecurityDecision(path, False, "aucun signal de sensibilité")
