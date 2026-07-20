"""Tests pour ids.py — génération d'identifiants et correspondance approximative."""
from graphmind.ids import _slug, file_stem_id, fuzzy_find_symbol, make_id


def test_slug_basique():
    assert _slug("Account.py") == "account_py"


def test_slug_chaine_vide_donne_x():
    assert _slug("") == "x"


def test_make_id_assemble_plusieurs_parties():
    assert make_id("account/account.py", "Account", "find_by_email") == "account_account_py_account_find_by_email"


def test_make_id_ignore_les_parties_vides():
    assert make_id("login.py", "") == make_id("login.py")


def test_file_stem_id_equivaut_a_make_id_un_seul_argument():
    assert file_stem_id("services/payment_service.py") == make_id("services/payment_service.py")


def test_slug_collision_connue():
    assert make_id("auth/login.py") == make_id("auth_login.py")


def test_fuzzy_find_symbol_rattrape_une_faute_de_frappe():
    known = {"email_sercice": "notifications_email_sercice_py"}
    assert fuzzy_find_symbol("email_service", known) == "notifications_email_sercice_py"


def test_fuzzy_find_symbol_ne_devine_jamais_sur_un_nom_different():
    known = {"email_sercice": "notifications_email_sercice_py"}
    assert fuzzy_find_symbol("totally_different_name", known) is None


def test_fuzzy_find_symbol_fonctionne_aussi_sur_une_correspondance_exacte():
    known = {"charge": "payments_stripe_adapter_py_charge"}
    assert fuzzy_find_symbol("charge", known) == "payments_stripe_adapter_py_charge"


def test_fuzzy_find_symbol_liste_vide_retourne_none():
    assert fuzzy_find_symbol("anything", {}) is None


def test_fuzzy_find_symbol_respecte_le_seuil():
    known = {"email_sercice": "id_1"}
    assert fuzzy_find_symbol("email_service", known, threshold=0.99) is None
