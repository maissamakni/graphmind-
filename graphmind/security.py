"""Politique de sécurité : décide, fichier par fichier, si l'extraction
sémantique doit rester 100% locale ou peut passer par un LLM externe."""
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
    """Règles simples et explicites, faciles à auditer par un humain."""

    SENSITIVE_DIR_KEYWORDS = (
        "secret", "secrets", "confidentiel", "confidential", "private",
        "credentials", "credential", "internal", "interne", "rh", "hr",
    )

    SECRET_PATTERNS = (
        re.compile(r"-----BEGIN (RSA )?PRIVATE KEY-----"),
        re.compile(r"api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}"),
        re.compile(r"password\s*[:=]\s*['\"][^'\"]{4,}"),
    )

    def __init__(self, extra_sensitive_dirs: list[str] | None = None):
        self.extra_sensitive_dirs = [d.lower() for d in (extra_sensitive_dirs or [])]

    def _dir_is_sensitive(self, path: Path) -> bool:
        parts = [p.lower() for p in path.parts]
        keywords = set(self.SENSITIVE_DIR_KEYWORDS) | set(self.extra_sensitive_dirs)
        return any(part in keywords for part in parts)

    def _content_looks_sensitive(self, path: Path, max_bytes: int = 200_000) -> bool:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:max_bytes]
        except OSError:
            return False
        return any(pattern.search(text) for pattern in self.SECRET_PATTERNS)

    def decide(self, path: Path) -> SecurityDecision:
        if self._dir_is_sensitive(path):
            return SecurityDecision(path, True, "dossier marqué sensible")
        if path.suffix in (".md", ".txt", ".py", ".js", ".ts", ".json", ".yaml", ".yml"):
            if self._content_looks_sensitive(path):
                return SecurityDecision(path, True, "motif de secret détecté dans le contenu")
        return SecurityDecision(path, False, "aucun signal de sensibilité")
