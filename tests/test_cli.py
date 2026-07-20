"""Tests pour cli.py — notamment le contexte hiérarchique de _build_context."""
from graphmind.cli import _build_context


def test_build_context_separe_code_et_documentaire():
    subgraph = {
        "nodes": [
            {"id": "a", "label": "login()", "modality": "code"},
            {"id": "b", "label": "find_by_email()", "modality": "code"},
            {"id": "c", "label": "README.md", "modality": "document"},
            {"id": "d", "label": "Authentification", "modality": "document"},
        ],
        "edges": [
            {"source": "a", "target": "b", "relation": "calls"},
            {"source": "c", "target": "d", "relation": "contains"},
            {"source": "c", "target": "a", "relation": "describes"},
        ],
    }
    context = _build_context(subgraph)
    assert "Faits extraits directement du code" in context
    assert "Contexte documentaire" in context
    assert "login() —calls—> find_by_email()" in context
    assert "README.md —describes—> login()" in context


def test_build_context_sans_documentation_naffiche_pas_la_section():
    subgraph = {
        "nodes": [
            {"id": "a", "label": "login()", "modality": "code"},
            {"id": "b", "label": "find_by_email()", "modality": "code"},
        ],
        "edges": [{"source": "a", "target": "b", "relation": "calls"}],
    }
    context = _build_context(subgraph)
    assert "Faits extraits directement du code" in context
    assert "Contexte documentaire" not in context
