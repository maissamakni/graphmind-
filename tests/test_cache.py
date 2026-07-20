"""Tests pour cache.py — cache d'extraction incrémental."""
from graphmind.cache import get_cached_result, store_result
from graphmind.schema import Confidence, Edge, ExtractionResult, Modality, Node


def _make_result(incomplete: bool = False) -> ExtractionResult:
    node = Node("id_1", "login", Modality.CODE, "auth/login.py", "L1")
    edge = Edge("id_1", "id_1", "contains", Confidence.EXTRACTED, "auth/login.py")
    return ExtractionResult(nodes=[node], edges=[edge], extraction_incomplete=incomplete)


def test_un_resultat_reussi_est_mis_en_cache(tmp_path):
    fichier = tmp_path / "login.py"
    fichier.write_text("def login(): pass")

    cache: dict = {}
    store_result(cache, fichier, "auth/login.py", _make_result(incomplete=False))

    assert "auth/login.py" in cache


def test_un_echec_n_est_jamais_mis_en_cache(tmp_path):
    fichier = tmp_path / "payment_service.png"
    fichier.write_bytes(b"fake image bytes")

    cache: dict = {}
    store_result(cache, fichier, "payments/payment_service.png", _make_result(incomplete=True))

    assert "payments/payment_service.png" not in cache


def test_un_echec_retire_une_ancienne_entree_reussie(tmp_path):
    fichier = tmp_path / "image.png"
    fichier.write_bytes(b"version 1")

    cache: dict = {}
    store_result(cache, fichier, "image.png", _make_result(incomplete=False))
    assert "image.png" in cache

    fichier.write_bytes(b"version 2 qui echoue")
    store_result(cache, fichier, "image.png", _make_result(incomplete=True))
    assert "image.png" not in cache


def test_get_cached_result_retourne_none_si_contenu_modifie(tmp_path):
    fichier = tmp_path / "login.py"
    fichier.write_text("version originale")

    cache: dict = {}
    store_result(cache, fichier, "login.py", _make_result())

    fichier.write_text("version modifiee")
    assert get_cached_result(cache, fichier, "login.py") is None


def test_get_cached_result_reconstruit_les_enums_correctement(tmp_path):
    fichier = tmp_path / "login.py"
    fichier.write_text("def login(): pass")

    cache: dict = {}
    store_result(cache, fichier, "login.py", _make_result())

    result = get_cached_result(cache, fichier, "login.py")
    assert result is not None
    assert result.nodes[0].modality == Modality.CODE
    assert result.edges[0].confidence == Confidence.EXTRACTED
