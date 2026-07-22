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


def test_build_context_groupe_le_contexte_documentaire_par_fichier_source():
    """Nouveau : plusieurs documents distincts doivent apparaître dans des
    sous-sections séparées, chacune explicitement nommée par son fichier
    source — pas une liste plate mélangeant plusieurs documents."""
    subgraph = {
        "nodes": [
            {"id": "a", "label": "login()", "modality": "code"},
            {"id": "c", "label": "README.md", "modality": "document"},
            {"id": "e", "label": "payment_service.png", "modality": "image"},
            {"id": "f", "label": "charge", "modality": "image"},
        ],
        "edges": [
            {"source": "c", "target": "a", "relation": "describes", "source_file": "README.md"},
            {"source": "e", "target": "f", "relation": "illustrates", "source_file": "payment_service.png"},
        ],
    }
    context = _build_context(subgraph)
    assert "D'après README.md :" in context
    assert "D'après payment_service.png :" in context
    # Les deux sources ne doivent jamais être mélangées dans le même bloc :
    readme_section = context.split("D'après README.md :")[1].split("D'après payment_service.png")[0]
    assert "payment_service.png —illustrates" not in readme_section
