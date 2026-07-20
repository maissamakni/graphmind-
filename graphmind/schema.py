"""Schéma de données commun à toutes les modalités (code, doc, PDF, image,
vidéo). Principe central : peu importe la source, chaque extracteur
retourne toujours le même format ExtractionResult, ce qui permet à
build.py de tout fusionner sans connaître le détail de chaque modalité.
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
    """La modalité d'origine d'un nœud."""
    CODE = "code"
    DOCUMENT = "document"
    PDF = "pdf"
    IMAGE = "image"
    VIDEO = "video"
    CONCEPT = "concept"


@dataclass
class Node:
    id: str
    label: str
    modality: Modality
    source_file: str
    source_location: str | None = None
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
    relation: str
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
    raw_calls: list[dict] = field(default_factory=list)
    # Imports qui n'ont pas pu être résolus par l'approximation "chemin de
    # fichier -> module" (known_modules) — mis de côté pour une résolution
    # cross-fichier globale (cli.py), par correspondance de nom simple sur
    # le dernier segment du chemin importé (ex: "App\Helper" -> "Helper"),
    # exactement le même principe que raw_calls pour les appels non résolus.
    raw_imports: list[dict] = field(default_factory=list)
    # Namespace/package déclaré par CE fichier (ex: "App.Utils" en C#),
    # utilisé en dernier recours pour résoudre un import qui nomme un
    # namespace ENTIER (`using App.Utils;`) plutôt qu'un symbole précis —
    # None si le langage n'a pas cette notion, ou si l'extracteur du
    # langage ne la fournit pas.
    declared_namespace: str | None = None
    # True si l'extraction sémantique (LLM) a échoué ou n'a rien produit —
    # cache.py NE DOIT JAMAIS mettre ce résultat en cache dans ce cas.
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
        self.raw_imports.extend(other.raw_imports)
        self.extraction_incomplete = self.extraction_incomplete or other.extraction_incomplete
