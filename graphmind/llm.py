"""Interface LLM unifiée — le SEUL point du projet qui appelle un modèle IA."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

from .logging_config import get_logger

log = get_logger()


@dataclass
class LLMBackend:
    name: str  # "ollama", "anthropic", "openai", "groq", "none"
    model: str | None = None


def resolve_backend(force_local: bool) -> LLMBackend:
    """Choisit le backend à utiliser pour UN fichier donné.

    force_local=True (décidé par security.py) => jamais de backend externe,
    peu importe la configuration de l'utilisateur."""
    if force_local:
        if os.environ.get("GRAPHMIND_OLLAMA_MODEL"):
            return LLMBackend("ollama", os.environ["GRAPHMIND_OLLAMA_MODEL"])
        return LLMBackend("none")

    if os.environ.get("ANTHROPIC_API_KEY"):
        return LLMBackend("anthropic", "claude-sonnet-4-5")
    if os.environ.get("OPENAI_API_KEY"):
        return LLMBackend("openai", "gpt-4o-mini")
    if os.environ.get("GROQ_API_KEY"):
        return LLMBackend("groq", os.environ.get("GRAPHMIND_GROQ_MODEL", "openai/gpt-oss-120b"))
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
    """Retourne {"entities": [...], "relations": [...]} à partir d'un texte."""
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
    except Exception as exc:
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
        # La requête a RÉUSSI mais le modèle n'a pas répondu en JSON valide —
        # diagnostic explicite, jamais un échec totalement silencieux.
        apercu = raw[:200].replace("\n", " ")
        log.warning(f"réponse LLM non-JSON reçue, aperçu : {apercu!r}")
        return {"entities": [], "relations": []}


def _call_anthropic(prompt: str, model: str | None) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model or "claude-sonnet-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    return _parse_json_response(text)


def _call_openai(prompt: str, model: str | None) -> dict:
    import openai
    client = openai.OpenAI()
    resp = client.chat.completions.create(
        model=model or "gpt-4o-mini",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json_response(resp.choices[0].message.content or "")


def _call_groq(prompt: str, model: str | None, max_retries: int = 2) -> str:
    """Groq expose une API compatible OpenAI — requête HTTP directe.

    En-tête User-Agent nécessaire (sinon Cloudflare bloque avec un 403
    trompeur). Gestion du 429 (rate limit du niveau gratuit) : nouvelle
    tentative en respectant Retry-After, jusqu'à max_retries fois."""
    import time
    import urllib.error
    import urllib.request

    payload = json.dumps({
        "model": model or "llama-3.3-70b-versatile",
        "max_tokens": 1500,
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

    data = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < max_retries:
                wait_s = float(exc.headers.get("Retry-After", 5))
                log.warning(f"limite de requêtes Groq atteinte (429) — "
                            f"nouvelle tentative dans {wait_s:.0f}s ({attempt + 1}/{max_retries}).")
                time.sleep(wait_s)
                continue
            raise
    return data["choices"][0]["message"]["content"]


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


# --- Vision (image / frames vidéo) ---

_VISION_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
    "groq": "meta-llama/llama-4-scout-17b-16e-instruct",
    "ollama": "llava",
}


def _resolve_vision_model(backend: LLMBackend) -> str | None:
    if backend.name == "groq" and os.environ.get("GRAPHMIND_GROQ_VISION_MODEL"):
        return os.environ["GRAPHMIND_GROQ_VISION_MODEL"]
    return _VISION_MODELS.get(backend.name, backend.model)


_IMAGE_DESCRIBE_PROMPT = (
    "Décris cette image en 2-3 phrases en français, en te concentrant sur ce "
    "qu'elle représente pour un projet logiciel (schéma d'architecture, "
    "capture d'écran d'interface, diagramme...). Si l'image contient des noms "
    "de fonctions, classes ou fichiers visibles, cite-les explicitement."
)


def describe_image(image_bytes: bytes, media_type: str, backend: LLMBackend) -> str:
    """Légende en prose (2-3 phrases) — complémentaire à l'extraction
    structurée ci-dessous, moins utilisée."""
    if backend.name == "none":
        return ""

    import base64
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    model = _resolve_vision_model(backend)

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
            payload = {
                "model": model,
                "max_tokens": 300,
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
            else:
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
        log.warning(f"échec de la description d'image via '{backend.name}' ({exc}).")
        return ""
    return ""


_IMAGE_EXTRACT_PROMPT = """Tu analyses une image issue d'un projet logiciel (schéma
d'architecture, capture d'écran de code, diagramme...) pour en tirer un graphe de
connaissances. Si l'image contient du CODE SOURCE visible (ex: une capture d'écran),
LIS-LE ATTENTIVEMENT et extrais les vraies fonctions/classes qu'il définit ainsi que
leurs appels réels — pas une paraphrase, la structure exacte du code affiché.

Réponds UNIQUEMENT en JSON, sans aucun texte autour, au format exact :
{{"entities": [{{"name": "...", "type": "fonction|classe|composant|concept"}}],
  "relations": [{{"source": "...", "target": "...", "relation": "calls|imports|describes"}}]}}
"""


def extract_semantic_from_image(image_bytes: bytes, media_type: str, backend: LLMBackend) -> dict:
    """Équivalent de extract_semantic(), mais pour une IMAGE — demande
    explicitement au modèle de LIRE le code s'il en voit."""
    if backend.name == "none":
        return {"entities": [], "relations": [], "_skipped": "no backend configured"}

    import base64
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    model = _resolve_vision_model(backend)

    try:
        if backend.name == "anthropic":
            import anthropic
            client = anthropic.Anthropic()
            resp = client.messages.create(
                model=model, max_tokens=800,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_image}},
                    {"type": "text", "text": _IMAGE_EXTRACT_PROMPT},
                ]}],
            )
            text = "".join(b.text for b in resp.content if hasattr(b, "text"))
            return _parse_json_response(text)

        if backend.name in ("openai", "groq"):
            payload = {
                "model": model,
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64_image}"}},
                    {"type": "text", "text": _IMAGE_EXTRACT_PROMPT},
                ]}],
            }
            if backend.name == "openai":
                import openai
                client = openai.OpenAI()
                resp = client.chat.completions.create(**payload)
                return _parse_json_response(resp.choices[0].message.content or "")
            else:
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
                return _parse_json_response(data["choices"][0]["message"]["content"])

        if backend.name == "ollama":
            import urllib.request
            payload = json.dumps({
                "model": model, "prompt": _IMAGE_EXTRACT_PROMPT,
                "images": [b64_image], "stream": False,
            }).encode("utf-8")
            req = urllib.request.Request("http://localhost:11434/api/generate", data=payload,
                                          headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return _parse_json_response(json.loads(resp.read().decode("utf-8")).get("response", ""))
    except Exception as exc:
        log.warning(f"échec de l'extraction structurée d'image via '{backend.name}' ({exc}).")
        return {"entities": [], "relations": [], "_error": str(exc)}
    return {"entities": [], "relations": []}


# --- Nommage sémantique des communautés ---

_COMMUNITY_NAME_PROMPT = """Voici les noms des éléments (fonctions, classes, fichiers) qui
composent une communauté d'un graphe de connaissances de projet logiciel :

{labels}

Donne un nom court et descriptif pour cette communauté (2 à 5 mots, comme
"Account Auth Flow" ou "Payments & Transactions"). Réponds UNIQUEMENT avec
ce nom, sans ponctuation finale, sans guillemets, rien d'autre autour.
"""


def name_community(labels: list[str], backend: LLMBackend) -> str | None:
    """Un seul appel LLM PAR COMMUNAUTÉ (pas par fichier). Retourne None si
    aucun backend ou en cas d'échec — l'appelant garde alors son nom de
    repli mécanique (le nœud le plus connecté)."""
    if backend.name == "none" or not labels:
        return None

    prompt = _COMMUNITY_NAME_PROMPT.format(labels=", ".join(labels[:12]))
    try:
        if backend.name == "anthropic":
            import anthropic
            client = anthropic.Anthropic()
            resp = client.messages.create(
                model=backend.model or "claude-sonnet-4-5", max_tokens=20,
                messages=[{"role": "user", "content": prompt}],
            )
            name = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
        elif backend.name == "openai":
            import openai
            client = openai.OpenAI()
            resp = client.chat.completions.create(
                model=backend.model or "gpt-4o-mini", max_tokens=20,
                messages=[{"role": "user", "content": prompt}],
            )
            name = (resp.choices[0].message.content or "").strip()
        elif backend.name == "groq":
            name = _call_groq(prompt, backend.model).strip()
        elif backend.name == "ollama":
            import urllib.request
            payload = json.dumps({"model": backend.model or "llama3", "prompt": prompt, "stream": False}).encode("utf-8")
            req = urllib.request.Request("http://localhost:11434/api/generate", data=payload,
                                          headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                name = json.loads(resp.read().decode("utf-8")).get("response", "").strip()
        else:
            return None
        return name.strip('"\'.') or None
    except Exception as exc:
        log.warning(f"nommage de communauté échoué via '{backend.name}' ({exc}).")
        return None


# --- Liaison sémantique cross-modale (3e niveau, après exact + fuzzy) ---

_SEMANTIC_LINK_PROMPT = """Voici un concept mentionné dans un document/image d'un projet
logiciel : "{name}"

Voici la liste des symboles de code RÉELLEMENT présents dans ce projet :
{candidates}

Ce concept correspond-il, PAR LE SENS (pas juste l'orthographe), à L'UN de ces
symboles ? Par exemple "paiement" correspond au symbole "billing" ou
"payment_service" par le sens, même si l'orthographe est différente.

Réponds UNIQUEMENT avec le nom EXACT d'un symbole de la liste s'il y a une
correspondance claire, ou UNIQUEMENT le mot "aucun" si aucun ne correspond
vraiment. Rien d'autre autour de ta réponse.
"""


def semantic_link(name: str, candidates: list[str], backend: LLMBackend) -> str | None:
    """Dernier recours pour la liaison cross-modale, un appel LLM CIBLÉ par
    concept non résolu. Retourne None si aucun backend, aucune
    correspondance, ou échec — jamais un lien halluciné (le nom retourné
    doit correspondre EXACTEMENT à un candidat fourni)."""
    if backend.name == "none" or not candidates:
        return None

    prompt = _SEMANTIC_LINK_PROMPT.format(name=name, candidates=", ".join(sorted(candidates)[:30]))
    try:
        if backend.name == "anthropic":
            import anthropic
            client = anthropic.Anthropic()
            resp = client.messages.create(
                model=backend.model or "claude-sonnet-4-5", max_tokens=30,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
        elif backend.name == "openai":
            import openai
            client = openai.OpenAI()
            resp = client.chat.completions.create(
                model=backend.model or "gpt-4o-mini", max_tokens=30,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = (resp.choices[0].message.content or "").strip()
        elif backend.name == "groq":
            answer = _call_groq(prompt, backend.model).strip()
        elif backend.name == "ollama":
            import urllib.request
            payload = json.dumps({"model": backend.model or "llama3", "prompt": prompt, "stream": False}).encode("utf-8")
            req = urllib.request.Request("http://localhost:11434/api/generate", data=payload,
                                          headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                answer = json.loads(resp.read().decode("utf-8")).get("response", "").strip()
        else:
            return None
    except Exception as exc:
        log.warning(f"liaison sémantique échouée via '{backend.name}' ({exc}).")
        return None

    answer = answer.strip('"\'.')
    if answer.lower() == "aucun" or answer not in candidates:
        return None
    return answer


_SEMANTIC_LINK_BATCH_PROMPT = """Voici plusieurs concepts mentionnés dans un document/image
d'un projet logiciel, chacun à faire correspondre PAR LE SENS (pas
l'orthographe) à un symbole de code RÉELLEMENT présent dans ce projet, si
un lien clair existe.

Concepts à résoudre :
{names}

Symboles de code réels disponibles :
{candidates}

Réponds UNIQUEMENT en JSON, au format exact :
{{"concept_1": "nom_du_symbole_ou_null", "concept_2": "nom_du_symbole_ou_null", ...}}
Utilise `null` (pas la chaîne "aucun") si aucun symbole ne correspond vraiment.
"""


def semantic_link_batch(names: list[str], candidates: list[str], backend: LLMBackend) -> dict[str, str | None]:
    """Version GROUPÉE de semantic_link() : résout PLUSIEURS concepts en UN
    SEUL appel LLM au lieu d'un appel par concept — réduit le coût de N
    appels à 1 appel par fichier. Ne retourne JAMAIS un nom qui ne
    correspond pas EXACTEMENT à un candidat fourni."""
    if backend.name == "none" or not names or not candidates:
        return {name: None for name in names}

    prompt = _SEMANTIC_LINK_BATCH_PROMPT.format(
        names="\n".join(f"- {n}" for n in names),
        candidates=", ".join(sorted(candidates)[:50]),
    )
    try:
        if backend.name == "anthropic":
            import anthropic
            client = anthropic.Anthropic()
            resp = client.messages.create(
                model=backend.model or "claude-sonnet-4-5", max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = "".join(b.text for b in resp.content if hasattr(b, "text"))
        elif backend.name == "openai":
            import openai
            client = openai.OpenAI()
            resp = client.chat.completions.create(
                model=backend.model or "gpt-4o-mini", max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.choices[0].message.content or ""
        elif backend.name == "groq":
            raw = _call_groq(prompt, backend.model)
        elif backend.name == "ollama":
            import urllib.request
            payload = json.dumps({"model": backend.model or "llama3", "prompt": prompt, "stream": False}).encode("utf-8")
            req = urllib.request.Request("http://localhost:11434/api/generate", data=payload,
                                          headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = json.loads(resp.read().decode("utf-8")).get("response", "")
        else:
            return {name: None for name in names}
    except Exception as exc:
        log.warning(f"liaison sémantique groupée échouée via '{backend.name}' ({exc}).")
        return {name: None for name in names}

    parsed = _parse_json_response(raw)
    result: dict[str, str | None] = {}
    for name in names:
        candidate = parsed.get(name)
        result[name] = candidate if candidate in candidates else None
    return result


# --- Réponse finale à une requête ---

_ANSWER_PROMPT = """Tu es un assistant qui explique le fonctionnement d'un projet
à partir d'un extrait de son graphe de connaissances (nœuds et relations).

Question posée : {question}

Faits disponibles (issus du graphe, extraits du code réel) :
{context}

Réponds en français, en 3-5 phrases claires, en te basant UNIQUEMENT sur les faits
ci-dessus — n'invente aucune information absente de cette liste.
"""


def answer_question(question: str, context: str, backend: LLMBackend) -> str:
    """Génère la réponse finale en langage naturel à partir du sous-graphe."""
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
                model=backend.model or "gpt-4o-mini", max_tokens=500,
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
        log.warning(f"échec de l'appel au backend '{backend.name}' ({exc}) — repli sur le résumé sans IA.")
        return _fallback_answer(context, reason=f"le backend '{backend.name}' a échoué")
    return _fallback_answer(context)


def _fallback_answer(context: str, reason: str = "aucun backend LLM configuré") -> str:
    """Résumé déterministe (sans LLM) — jamais de JSON brut, même sans
    backend. Préserve la structure hiérarchique (sections "faits de code"
    / "contexte documentaire") produite par _build_context() plutôt que de
    tout aplatir en une seule ligne séparée par des points-virgules."""
    context = context.strip()
    if not context:
        return "Aucune information pertinente trouvée dans le graphe pour cette question."
    # Limite raisonnable pour ne pas afficher un résumé trop long, tout en
    # gardant les sauts de ligne (donc la structure) intacts.
    if len(context) > 800:
        context = context[:800].rsplit("\n", 1)[0] + "\n[...]"
    return f"D'après le graphe ({reason}) :\n\n{context}"
