"""Interface LLM unifiée — le SEUL point du projet qui appelle un modèle IA.

Principe (confirmé par l'étude de graphify) : le LLM ne doit être appelé
QUE là où l'extraction structurelle (AST, regex) ne suffit pas — documents,
PDF, images, vidéo. Jamais pour le code source.

Ce module ne fait aucun appel réseau lui-même si aucun backend n'est
configuré : il retourne alors un résultat vide et signale la limitation,
exactement comme le fait graphify ("A code-only corpus needs no key").
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass


@dataclass
class LLMBackend:
    name: str  # "ollama", "anthropic", "openai", "none"
    model: str | None = None


def resolve_backend(force_local: bool) -> LLMBackend:
    """Choisit le backend à utiliser pour UN fichier donné.

    force_local=True (décidé par security.py) => on n'utilise JAMAIS
    un backend externe, peu importe ce que l'utilisateur a configuré
    par défaut. C'est la garantie de sécurité centrale du projet.
    """
    if force_local:
        if os.environ.get("GRAPHMIND_OLLAMA_MODEL"):
            return LLMBackend("ollama", os.environ["GRAPHMIND_OLLAMA_MODEL"])
        return LLMBackend("none")  # aucune extraction sémantique possible, en sécurité

    if os.environ.get("ANTHROPIC_API_KEY"):
        return LLMBackend("anthropic", "claude-sonnet-4-5")
    if os.environ.get("OPENAI_API_KEY"):
        return LLMBackend("openai", "gpt-4o-mini")
    if os.environ.get("GROQ_API_KEY"):
        return LLMBackend("groq", "llama-3.3-70b-versatile")
    if os.environ.get("GRAPHMIND_OLLAMA_MODEL"):
        return LLMBackend("ollama", os.environ["GRAPHMIND_OLLAMA_MODEL"])
    return LLMBackend("none")


_EXTRACTION_PROMPT = """Tu analyses un extrait de document pour en tirer un graphe de connaissances.
Réponds UNIQUEMENT en JSON, sans aucun texte autour, au format exact :
{{"entities": [{{"name": "...", "type": "concept|fonction|composant"}}],
  "relations": [{{"source": "...", "target": "...", "relation": "describes|references"}}]}}

Texte à analyser :
---
{text}
---
"""


def extract_semantic(text: str, backend: LLMBackend) -> dict:
    """Retourne {"entities": [...], "relations": [...]} à partir d'un texte,
    en utilisant le backend fourni. Ne lève jamais d'exception vers l'appelant :
    en cas d'échec ou d'absence de backend, retourne un résultat vide.
    """
    if backend.name == "none":
        return {"entities": [], "relations": [], "_skipped": "no backend configured"}

    prompt = _EXTRACTION_PROMPT.format(text=text[:6000])

    try:
        if backend.name == "anthropic":
            return _call_anthropic(prompt, backend.model)
        if backend.name == "openai":
            return _call_openai(prompt, backend.model)
        if backend.name == "groq":
            return _parse_json_response(_call_groq(prompt, backend.model))
        if backend.name == "ollama":
            return _call_ollama(prompt, backend.model)
    except Exception as exc:  # défensif : jamais bloquant pour le pipeline
        return {"entities": [], "relations": [], "_error": str(exc)}
    return {"entities": [], "relations": []}


def _parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[-1] if "\n" in raw else raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"entities": [], "relations": []}


def _call_anthropic(prompt: str, model: str | None) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model or "claude-sonnet-4-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    return _parse_json_response(text)


def _call_openai(prompt: str, model: str | None) -> dict:
    import openai
    client = openai.OpenAI()
    resp = client.chat.completions.create(
        model=model or "gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json_response(resp.choices[0].message.content or "")


def _call_ollama(prompt: str, model: str | None) -> dict:
    import urllib.request
    payload = json.dumps({
        "model": model or "llama3",
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/generate", data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return _parse_json_response(data.get("response", ""))


def _call_groq(prompt: str, model: str | None) -> str:
    """Groq expose une API compatible avec le format OpenAI — pas besoin du
    paquet `openai`, une simple requête HTTP suffit.

    Note : Cloudflare (devant l'API Groq) bloque les requêtes sans en-tête
    User-Agent avec une erreur 403 trompeuse (qui ressemble à un problème de
    clé, mais n'en est pas un) — d'où l'en-tête explicite ci-dessous.
    """
    import urllib.request
    payload = json.dumps({
        "model": model or "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions", data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}",
            "User-Agent": "graphmind/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


_ANSWER_PROMPT = """Tu es un assistant qui explique le fonctionnement d'un projet
à partir d'un extrait de son graphe de connaissances (nœuds et relations).

Question posée : {question}

Faits disponibles (issus du graphe, extraits du code réel) :
{context}

Réponds en français, en 3-5 phrases claires, en te basant UNIQUEMENT sur les faits
ci-dessus — n'invente aucune information absente de cette liste.
"""


def answer_question(question: str, context: str, backend: LLMBackend) -> str:
    """Génère une réponse en langage naturel à partir du sous-graphe trouvé.

    Si aucun backend n'est configuré, retourne un résumé déterministe
    construit directement à partir des faits (pas de JSON brut affiché
    à l'utilisateur, mais pas non plus d'invention de contenu)."""
    if backend.name == "none":
        return _fallback_answer(context)

    prompt = _ANSWER_PROMPT.format(question=question, context=context)
    try:
        if backend.name == "anthropic":
            import anthropic
            client = anthropic.Anthropic()
            resp = client.messages.create(
                model=backend.model or "claude-sonnet-4-5", max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
        if backend.name == "openai":
            import openai
            client = openai.OpenAI()
            resp = client.chat.completions.create(
                model=backend.model or "gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
            )
            return (resp.choices[0].message.content or "").strip()
        if backend.name == "groq":
            return _call_groq(prompt, backend.model).strip()
        if backend.name == "ollama":
            import urllib.request
            payload = json.dumps({"model": backend.model or "llama3", "prompt": prompt, "stream": False}).encode("utf-8")
            req = urllib.request.Request("http://localhost:11434/api/generate", data=payload,
                                          headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8")).get("response", "").strip()
    except Exception as exc:
        print(f"[graphmind] avertissement : échec de l'appel au backend '{backend.name}' ({exc}) — repli sur le résumé sans IA.", file=sys.stderr)
        return _fallback_answer(context, reason=f"le backend '{backend.name}' a échoué")
    return _fallback_answer(context)


def _fallback_answer(context: str, reason: str = "aucun backend LLM configuré") -> str:
    """Résumé simple et déterministe (sans LLM) — toujours une phrase en
    français, jamais du JSON brut, même sans backend configuré."""
    lines = [l for l in context.splitlines() if l.strip()]
    if not lines:
        return "Aucune information pertinente trouvée dans le graphe pour cette question."
    resume = " ; ".join(lines[:6])
    return f"D'après le graphe ({reason}, résumé direct des relations extraites du code) : {resume}."


_IMAGE_DESCRIBE_PROMPT = (
    "Décris cette image en 2-3 phrases en français, en te concentrant sur ce "
    "qu'elle représente pour un projet logiciel (schéma d'architecture, "
    "capture d'écran d'interface, diagramme...). Si l'image contient des noms "
    "de fonctions, classes ou fichiers visibles, cite-les explicitement."
)

# Modèles capables de "voir" une image, un par backend — les modèles textuels
# classiques (ex: llama-3.3-70b-versatile) ne peuvent pas traiter d'image.
_VISION_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.2-11b-vision-preview",
    "ollama": "llava",
}


def describe_image(image_bytes: bytes, media_type: str, backend: LLMBackend) -> str:
    """Envoie une image à un modèle de vision et retourne sa description en
    texte. Retourne une chaîne vide (jamais d'exception) si aucun backend
    n'est configuré ou si l'appel échoue — cohérent avec le reste du module :
    l'absence de légende ne doit jamais bloquer le reste du pipeline.
    """
    if backend.name == "none":
        return ""

    import base64
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    model = _VISION_MODELS.get(backend.name, backend.model)

    try:
        if backend.name == "anthropic":
            import anthropic
            client = anthropic.Anthropic()
            resp = client.messages.create(
                model=model, max_tokens=300,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_image}},
                    {"type": "text", "text": _IMAGE_DESCRIBE_PROMPT},
                ]}],
            )
            return "".join(b.text for b in resp.content if hasattr(b, "text")).strip()

        if backend.name in ("openai", "groq"):
            # Les deux exposent une API compatible avec le format "vision" d'OpenAI
            # (content = liste de blocs image_url / text) — seule l'URL de base change.
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64_image}"}},
                    {"type": "text", "text": _IMAGE_DESCRIBE_PROMPT},
                ]}],
            }
            if backend.name == "openai":
                import openai
                client = openai.OpenAI()
                resp = client.chat.completions.create(**payload)
                return (resp.choices[0].message.content or "").strip()
            else:  # groq
                import urllib.request
                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}",
                        "User-Agent": "graphmind/1.0",
                    },
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()

        if backend.name == "ollama":
            import urllib.request
            payload = json.dumps({
                "model": model, "prompt": _IMAGE_DESCRIBE_PROMPT,
                "images": [b64_image], "stream": False,
            }).encode("utf-8")
            req = urllib.request.Request("http://localhost:11434/api/generate", data=payload,
                                          headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8")).get("response", "").strip()
    except Exception as exc:
        print(f"[graphmind] avertissement : échec de la description d'image via '{backend.name}' ({exc}).", file=sys.stderr)
        return ""
    return ""
