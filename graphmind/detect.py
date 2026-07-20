"""Étape 1 du pipeline : parcourir le dossier et classer chaque fichier
par modalité (code / document / pdf / image / vidéo)."""
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
    ".java": "java",
    ".php": "php",
    ".cs": "csharp",
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".go": "go",
    ".rs": "rust",
    ".kt": "kotlin", ".kts": "kotlin",
    ".swift": "swift",
    ".dart": "dart",
    ".sql": "sql",
    ".scala": "scala",
    ".ps1": "powershell", ".psm1": "powershell",
}

DOC_EXTENSIONS = {".md", ".mdx", ".txt", ".rst"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


@dataclass
class DetectedFile:
    path: Path
    modality: Modality
    language: str | None = None


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


def collect_files(root: Path, extra_ignore_dirs: list[str] | None = None) -> list[DetectedFile]:
    """extra_ignore_dirs : dossiers supplémentaires à ignorer, typiquement
    chargés depuis graphmind.toml (config.py)."""
    root = Path(root)
    ignore_dirs = NOISE_DIRS | set(extra_ignore_dirs or [])
    results: list[DetectedFile] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in ignore_dirs for part in path.parts):
            continue
        detected = _classify(path)
        if detected is not None:
            results.append(detected)
    return results
