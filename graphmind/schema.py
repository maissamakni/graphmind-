"""Schéma de données commun à toutes les modalités (code, doc, PDF, image, vidéo).

Principe central (repris de la recherche) : peu importe la source, chaque
extracteur retourne toujours le même format {"nodes": [...], "edges": [...]},
ce qui permet à build.py de tout fusionner sans connaître le détail de chaque
modalité.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Confidence(str, Enum):
    """Niveau de confiance d'une relation.

    EXTRACTED : lecture directe et certaine (AST pour le code, OCR fidèle, etc.)
    INFERRED  : déduction raisonnable (LLM, heuristique de correspondance)
    AMBIGUOUS : incertain, à signaler pour revue humaine dans le rapport
    """
    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"


class Modality(str, Enum):
    """La modalité d'origine d'un nœud — sert à choisir l'extracteur et,
    plus tard, à décider si un fichier doit être traité localement (sécurité)."""
    CODE = "code"
    DOCUMENT = "document"
    PDF = "pdf"
    IMAGE = "image"
    VIDEO = "video"
    CONCEPT = "concept"  # nœud abstrait (ex: une entité mentionnée mais non définie ici)


@dataclass
class Node:
    id: str
    label: str
    modality: Modality
    source_file: str
    source_location: str | None = None  # ex: "L42" pour du code, "00:12:30" pour vidéo
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "modality": self.modality.value,
            "source_file": self.source_file,
            "source_location": self.source_location,
            "metadata": self.metadata,
        }


@dataclass
class Edge:
    source: str
    target: str
    relation: str  # "calls", "imports", "describes", "illustrates", "references", ...
    confidence: Confidence
    source_file: str
    source_location: str | None = None
    context: str | None = None
    weight: float = 1.0

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "confidence": self.confidence.value,
            "source_file": self.source_file,
            "source_location": self.source_location,
            "context": self.context,
            "weight": self.weight,
        }


@dataclass
class ExtractionResult:
    """Ce que chaque extracteur, quelle que soit la modalité, doit retourner."""
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    # Appels dont la cible n'a pas été trouvée DANS LE MÊME FICHIER — à résoudre
    # dans un second temps (cli.py), une fois que tous les fichiers sont extraits.
    # Chaque entrée : {"caller_id": str, "callee_name": str, "source_file": str, "line": str}
    raw_calls: list[dict] = field(default_factory=list)
    # True si l'extraction sémantique (LLM) a échoué ou n'a rien produit —
    # cache.py NE DOIT JAMAIS mettre ce résultat en cache dans ce cas, sinon
    # un échec ponctuel (clé invalide, modèle temporairement indisponible...)
    # resterait bloqué indéfiniment même après correction du problème.
    extraction_incomplete: bool = False

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    def merge(self, other: "ExtractionResult") -> None:
        self.nodes.extend(other.nodes)
        self.edges.extend(other.edges)
        self.raw_calls.extend(other.raw_calls)
        self.extraction_incomplete = self.extraction_incomplete or other.extraction_incomplete
