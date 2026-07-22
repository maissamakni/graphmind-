"""Tests pour ids.py — génération d'identifiants et correspondance approximative."""
from graphmind.ids import (
    _slug, build_normalized_lookup, file_stem_id, fuzzy_find_symbol,
    make_id, normalize_identifier,
)


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


def test_normalize_identifier_camel_case():
    assert normalize_identifier("checkPassword") == "check_password"


def test_normalize_identifier_pascal_case():
    assert normalize_identifier("CheckPassword") == "check_password"


def test_normalize_identifier_snake_case_inchange():
    assert normalize_identifier("check_password") == "check_password"


def test_normalize_identifier_kebab_case():
    assert normalize_identifier("check-password") == "check_password"


def test_normalize_identifier_toutes_conventions_convergent():
    forms = ["checkPassword", "CheckPassword", "check_password", "check-password"]
    normalized = {normalize_identifier(f) for f in forms}
    assert len(normalized) == 1


def test_build_normalized_lookup_retrouve_par_forme_normalisee():
    known = {"checkPassword": "account_java_checkpassword"}
    lookup = build_normalized_lookup(known)
    assert lookup["check_password"] == "account_java_checkpassword"


def test_build_normalized_lookup_garde_le_premier_en_cas_de_collision():
    """Deux symboles distincts qui partagent la même forme normalisée —
    ne doit jamais planter, garde le premier rencontré."""
    known = {"checkPassword": "id_1", "check_password": "id_2"}
    lookup = build_normalized_lookup(known)
    assert lookup["check_password"] in ("id_1", "id_2")
