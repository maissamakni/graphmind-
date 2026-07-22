"""Tests pour extractors/image.py — en particulier la résolution
cross-modale par convention de nommage normalisée (nouveau)."""
from pathlib import Path
from unittest.mock import patch

from graphmind.extractors.image import extract_image
from graphmind.llm import LLMBackend


def _make_test_png(path: Path) -> None:
    from PIL import Image
    img = Image.new("RGB", (10, 10), color="white")
    img.save(path, format="PNG")


def test_image_resolution_normalisee_convention_differente(tmp_path):
    """Cas réel : le modèle de vision lit 'check_password' affiché à
    l'écran (capture de code en snake_case), mais le vrai symbole du
    projet est 'checkPassword' (camelCase, Java) — doit être résolu par
    convention normalisée, pas seulement par exact match ou fuzzy."""
    image_path = tmp_path / "screenshot.png"
    _make_test_png(image_path)

    fake_backend = LLMBackend("groq", "fake-model")

    def fake_extract_semantic_from_image(image_bytes, media_type, backend):
        return {"entities": [{"name": "check_password", "type": "fonction"}], "relations": []}

    known_code_symbols = {"checkPassword": "account_java_checkpassword"}

    with patch("graphmind.llm.resolve_backend", return_value=fake_backend), \
         patch("graphmind.llm.extract_semantic_from_image", side_effect=fake_extract_semantic_from_image):
        result = extract_image(image_path, "screenshot.png", False, known_code_symbols)

    normalized_edges = [e for e in result.edges if e.context == "vision_normalized_match"]
    assert len(normalized_edges) == 1
    assert normalized_edges[0].target == "account_java_checkpassword"
    # Confiance : aussi fiable qu'un exact match, PAS dégradée à AMBIGUOUS.
    assert normalized_edges[0].confidence.value == "INFERRED"


def test_image_exact_match_prioritaire_sur_normalise(tmp_path):
    """Si une correspondance EXACTE existe déjà, la résolution normalisée
    ne doit jamais s'appliquer en plus (pas de doublon)."""
    image_path = tmp_path / "screenshot.png"
    _make_test_png(image_path)

    fake_backend = LLMBackend("groq", "fake-model")

    def fake_extract_semantic_from_image(image_bytes, media_type, backend):
        return {"entities": [{"name": "checkPassword", "type": "fonction"}], "relations": []}

    known_code_symbols = {"checkPassword": "account_java_checkpassword"}

    with patch("graphmind.llm.resolve_backend", return_value=fake_backend), \
         patch("graphmind.llm.extract_semantic_from_image", side_effect=fake_extract_semantic_from_image):
        result = extract_image(image_path, "screenshot.png", False, known_code_symbols)

    reference_edges = [e for e in result.edges if e.relation == "references"]
    assert len(reference_edges) == 1
    assert reference_edges[0].context == "vision_exact_match"
