"""Extraction pour vidéo.

Deux sources de contenu, complémentaires et indépendantes :
1. Transcription AUDIO 100% locale via faster-whisper — pour une vidéo avec
   narration. Aucun backend externe nécessaire à cette étape.
2. Extraction VISUELLE via quelques images clés extraites de la vidéo (PyAV,
   déjà une dépendance de faster-whisper) — pour une vidéo SANS narration
   qui montre néanmoins du contenu utile à l'écran (ex: une capture d'écran
   silencieuse montrant du code), en réutilisant exactement le même
   mécanisme de lecture structurée que pour une image fixe (image.py).

Les deux sources sont tentées indépendamment : une vidéo peut n'avoir que
de la parole, que du contenu visuel, les deux, ou ni l'un ni l'autre — dans
ce dernier cas seulement, on considère l'extraction incomplète.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

from .. import llm
from ..ids import make_id
from ..schema import Confidence, Edge, ExtractionResult, Modality, Node


def _transcribe_local(path: Path) -> list[dict] | None:
    """Retourne une liste de segments {"start": float, "end": float, "text": str}.

    Distinction importante entre DEUX cas bien différents :
    - Retourne None si faster-whisper est absent OU si la transcription a
      RÉELLEMENT échoué (exception) — un vrai problème à signaler.
    - Retourne une liste VIDE [] si faster-whisper a fonctionné correctement
      mais n'a trouvé aucune parole dans la vidéo (silencieuse, musique
      seule, ou contenu purement visuel comme du code affiché) — un
      résultat légitime, PAS une erreur.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("[graphmind] avertissement : faster-whisper non installé — transcription vidéo ignorée.", file=sys.stderr)
        return None
    try:
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(path))
        return [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
    except Exception as exc:
        print(f"[graphmind] avertissement : échec de la transcription vidéo ({type(exc).__name__}: {exc}).", file=sys.stderr)
        return None


def _extract_key_frames(path: Path, max_frames: int = 3) -> list[bytes]:
    """Extrait quelques images (PNG) réparties dans la vidéo, pour une
    lecture visuelle de son contenu (ex: du code affiché à l'écran, sans
    narration). Retourne une liste vide si PyAV est absent ou en cas
    d'échec — jamais d'exception remontée à l'appelant."""
    try:
        import av
    except ImportError:
        return []

    frames: list[bytes] = []
    try:
        container = av.open(str(path))
        stream = container.streams.video[0]
        duration = float(stream.duration * stream.time_base) if stream.duration else 0.0
        if duration <= 0:
            return []

        # Répartit les instants choisis sur toute la durée, en évitant le
        # tout début/la toute fin (souvent un écran vide ou une transition).
        timestamps = [duration * (i + 1) / (max_frames + 1) for i in range(max_frames)]
        for ts in timestamps:
            container.seek(int(ts / stream.time_base), stream=stream)
            for frame in container.decode(stream):
                buf = io.BytesIO()
                frame.to_image().save(buf, format="PNG")
                frames.append(buf.getvalue())
                break  # une seule image par instant visé
    except Exception as exc:
        print(f"[graphmind] avertissement : échec de l'extraction d'images de la vidéo ({exc}).", file=sys.stderr)
        return frames  # on garde celles déjà obtenues avant l'échec, s'il y en a

    return frames


def extract_video(
    path: Path, relative_path: str, force_local: bool,
    known_code_symbols: dict[str, str] | None = None,
) -> ExtractionResult:
    known_code_symbols = known_code_symbols or {}
    result = ExtractionResult()
    file_id = make_id(relative_path)
    result.nodes.append(Node(file_id, path.name, Modality.VIDEO, relative_path, None))

    backend = llm.resolve_backend(force_local)
    found_anything = False

    # --- Source 1 : transcription audio ---
    segments = _transcribe_local(path)
    if segments is None:
        result.nodes.append(Node(
            make_id(relative_path, "no_transcript"),
            "[transcription audio non disponible — faster-whisper non installé ou erreur, voir les avertissements]",
            Modality.CONCEPT, relative_path,
        ))
        result.extraction_incomplete = True
    elif segments:
        found_anything = True
        full_text = " ".join(s["text"] for s in segments)
        confidence = Confidence.INFERRED if backend.name != "none" else Confidence.AMBIGUOUS

        for seg in segments:
            ts = f"{int(seg['start'] // 60):02d}:{int(seg['start'] % 60):02d}"
            seg_id = make_id(relative_path, "segment", ts)
            result.nodes.append(Node(seg_id, seg["text"][:80], Modality.VIDEO, relative_path, ts))
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
    else:
        pass  # segments == [] : audio traité avec succès mais aucune parole
              # trouvée — on attend de voir si la source visuelle (frames)
              # trouve quelque chose avant de conclure quoi que ce soit
              # (cf. le bloc final, qui gère le cas où RIEN n'a été trouvé).

    # --- Source 2 : lecture visuelle d'images clés (ex: code affiché) ---
    if backend.name != "none":
        frames = _extract_key_frames(path)
        entity_ids: dict[str, str] = {}
        seen_refs: set[str] = set()
        seen_relations: set[tuple[str, str, str]] = set()
        confidence = Confidence.INFERRED

        for i, frame_bytes in enumerate(frames):
            semantic = llm.extract_semantic_from_image(frame_bytes, "image/png", backend)
            for entity in semantic.get("entities", []):
                name = entity.get("name")
                if not name or name in entity_ids:
                    continue  # déjà vu sur une image précédente de la même vidéo
                found_anything = True
                ent_id = make_id(relative_path, "frame_concept", name)
                entity_ids[name] = ent_id
                result.nodes.append(Node(
                    ent_id, name, Modality.VIDEO, relative_path,
                    metadata={"entity_type": entity.get("type", "concept"), "backend": backend.name, "source": "frame"},
                ))
                result.edges.append(Edge(file_id, ent_id, "illustrates", confidence, relative_path))

                target_id = known_code_symbols.get(name)
                if target_id is not None and target_id not in seen_refs:
                    seen_refs.add(target_id)
                    result.edges.append(Edge(
                        ent_id, target_id, "references", confidence,
                        relative_path, context="video_frame_exact_match",
                    ))

            for rel in semantic.get("relations", []):
                src_name, tgt_name = rel.get("source"), rel.get("target")
                if not src_name or not tgt_name:
                    continue
                src_id = known_code_symbols.get(src_name) or entity_ids.get(src_name)
                tgt_id = known_code_symbols.get(tgt_name) or entity_ids.get(tgt_name)
                relation_name = rel.get("relation", "references")
                rel_key = (src_id, tgt_id, relation_name)
                if src_id and tgt_id and rel_key not in seen_relations:
                    seen_relations.add(rel_key)
                    result.edges.append(Edge(src_id, tgt_id, relation_name, confidence, relative_path))

    if not found_anything and not result.extraction_incomplete:
        result.nodes.append(Node(
            make_id(relative_path, "no_content_found"),
            "[ni parole ni contenu visuel exploitable détecté dans la vidéo]",
            Modality.CONCEPT, relative_path,
        ))

    return result
