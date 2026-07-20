"""Tests pour semantic_link / semantic_link_batch — liaison cross-modale
par le sens, en dernier recours après échec des correspondances exacte et
approximative."""
from unittest.mock import patch

from graphmind.llm import LLMBackend, semantic_link, semantic_link_batch


def test_semantic_link_trouve_une_correspondance_par_le_sens():
    backend = LLMBackend("groq", "fake-model")
    with patch("graphmind.llm._call_groq", return_value="billing"):
        result = semantic_link("paiement", ["billing", "login", "send_email"], backend)
    assert result == "billing"


def test_semantic_link_retourne_none_si_aucune_correspondance():
    backend = LLMBackend("groq", "fake-model")
    with patch("graphmind.llm._call_groq", return_value="aucun"):
        result = semantic_link("concept_hors_sujet", ["billing", "login"], backend)
    assert result is None


def test_semantic_link_rejette_un_nom_hallucine():
    backend = LLMBackend("groq", "fake-model")
    with patch("graphmind.llm._call_groq", return_value="nom_qui_nexiste_pas"):
        result = semantic_link("paiement", ["billing"], backend)
    assert result is None


def test_semantic_link_sans_backend_retourne_none():
    backend = LLMBackend("none")
    result = semantic_link("paiement", ["billing"], backend)
    assert result is None


def test_semantic_link_sans_candidats_retourne_none():
    backend = LLMBackend("groq", "fake-model")
    result = semantic_link("paiement", [], backend)
    assert result is None


def test_semantic_link_batch_resout_plusieurs_concepts_en_un_appel():
    import json
    backend = LLMBackend("groq", "fake-model")
    fake_response = json.dumps({"paiement": "billing", "notif": "send_email", "hors_sujet": None})
    with patch("graphmind.llm._call_groq", return_value=fake_response) as mock_call:
        result = semantic_link_batch(["paiement", "notif", "hors_sujet"], ["billing", "send_email", "login"], backend)
    assert result == {"paiement": "billing", "notif": "send_email", "hors_sujet": None}
    assert mock_call.call_count == 1  # UN SEUL appel pour les 3 concepts


def test_semantic_link_batch_rejette_les_hallucinations():
    import json
    backend = LLMBackend("groq", "fake-model")
    fake_response = json.dumps({"paiement": "nom_invente"})
    with patch("graphmind.llm._call_groq", return_value=fake_response):
        result = semantic_link_batch(["paiement"], ["billing"], backend)
    assert result == {"paiement": None}


def test_semantic_link_batch_reponse_malformee_ne_plante_pas():
    backend = LLMBackend("groq", "fake-model")
    with patch("graphmind.llm._call_groq", return_value="pas du JSON valide"):
        result = semantic_link_batch(["paiement"], ["billing"], backend)
    assert result == {"paiement": None}


def test_semantic_link_batch_liste_vide():
    backend = LLMBackend("groq", "fake-model")
    assert semantic_link_batch([], ["billing"], backend) == {}
