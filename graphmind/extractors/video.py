"""Extraction pour vidéo.

Transcription 100% locale via faster-whisper (comme dans graphify) —
c'est la seule étape qui ne nécessite AUCUN backend externe, donc AUCUN
arbitrage de sécurité n'est nécessaire ici : la transcription reste
toujours locale, seule l'éventuelle extraction sémantique du texte
transcrit (identique à pdf_doc.py) suit la politique de sécurité.
"""
from __future__ import annotations

from pathlib import Path

from .. import llm
from ..ids import make_id
from ..schema import Confidence, Edge, ExtractionResult, Modality, Node


def _transcribe_local(path: Path) -> list[dict]:
    """Retourne une liste de segments {"start": float, "end": float, "text": str}.
    Nécessite faster-whisper (poids ~150 Mo pour le modèle "small") ; si absent,
    retourne une liste vide sans jamais faire d'appel réseau."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return []
    try:
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(path))
        return [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
    except Exception:
        return []


def extract_video(path: Path, relative_path: str, force_local: bool) -> ExtractionResult:
    result = ExtractionResult()
    file_id = make_id(relative_path)
    result.nodes.append(Node(file_id, path.name, Modality.VIDEO, relative_path, None))

    segments = _transcribe_local(path)
    if not segments:
        result.nodes.append(Node(
            make_id(relative_path, "no_transcript"),
            "[transcription non disponible — faster-whisper non installé]",
            Modality.CONCEPT, relative_path,
        ))
        return result

    full_text = " ".join(s["text"] for s in segments)
    backend = llm.resolve_backend(force_local)
    confidence = Confidence.INFERRED if backend.name != "none" else Confidence.AMBIGUOUS

    for seg in segments:
        ts = f"{int(seg['start'] // 60):02d}:{int(seg['start'] % 60):02d}"
        seg_id = make_id(relative_path, "segment", ts)
        result.nodes.append(Node(
            seg_id, seg["text"][:80], Modality.VIDEO, relative_path, ts,
        ))
        result.edges.append(Edge(file_id, seg_id, "contains", Confidence.EXTRACTED, relative_path, ts))

    if backend.name != "none":
        semantic = llm.extract_semantic(full_text, backend)
        for entity in semantic.get("entities", []):
            name = entity.get("name")
            if not name:
                continue
            ent_id = make_id(relative_path, name)
            result.nodes.append(Node(ent_id, name, Modality.VIDEO, relative_path))
            result.edges.append(Edge(file_id, ent_id, "contains", confidence, relative_path))

    return result
