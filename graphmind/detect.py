"""Étape 1 du pipeline : parcourir le dossier et classer chaque fichier
par modalité (code / document / pdf / image / vidéo).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schema import Modality

NOISE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".graphmind-out", ".idea", ".vscode",
}

CODE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
}

DOC_EXTENSIONS = {".md", ".mdx", ".txt", ".rst"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


@dataclass
class DetectedFile:
    path: Path
    modality: Modality
    language: str | None = None  # utile seulement pour le code


def _classify(path: Path) -> DetectedFile | None:
    suffix = path.suffix.lower()
    if suffix in CODE_EXTENSIONS:
        return DetectedFile(path, Modality.CODE, CODE_EXTENSIONS[suffix])
    if suffix in DOC_EXTENSIONS:
        return DetectedFile(path, Modality.DOCUMENT)
    if suffix in PDF_EXTENSIONS:
        return DetectedFile(path, Modality.PDF)
    if suffix in IMAGE_EXTENSIONS:
        return DetectedFile(path, Modality.IMAGE)
    if suffix in VIDEO_EXTENSIONS:
        return DetectedFile(path, Modality.VIDEO)
    return None


def collect_files(root: Path) -> list[DetectedFile]:
    """Parcourt récursivement `root` et retourne la liste des fichiers
    reconnus, avec leur modalité déjà déterminée."""
    root = Path(root)
    results: list[DetectedFile] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in NOISE_DIRS for part in path.parts):
            continue
        detected = _classify(path)
        if detected is not None:
            results.append(detected)
    return results
