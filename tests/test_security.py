"""Tests pour security.py — arbitrage local/externe par fichier."""
from graphmind.security import SecurityPolicy


def test_dossier_sensible_force_le_local(tmp_path):
    sensitive_dir = tmp_path / "secrets"
    sensitive_dir.mkdir()
    fichier = sensitive_dir / "config.py"
    fichier.write_text("API_KEY = 'x'")

    policy = SecurityPolicy()
    decision = policy.decide(fichier)

    assert decision.force_local is True
    assert "sensible" in decision.reason


def test_dossier_normal_ne_force_pas_le_local(tmp_path):
    fichier = tmp_path / "login.py"
    fichier.write_text("def login(): pass")

    policy = SecurityPolicy()
    decision = policy.decide(fichier)

    assert decision.force_local is False


def test_contenu_avec_cle_api_force_le_local(tmp_path):
    fichier = tmp_path / "settings.py"
    fichier.write_text('api_key = "sk-1234567890abcdef1234"')

    policy = SecurityPolicy()
    decision = policy.decide(fichier)

    assert decision.force_local is True
    assert "contenu" in decision.reason


def test_mot_cle_sensible_supplementaire_configurable(tmp_path):
    custom_dir = tmp_path / "brevet"
    custom_dir.mkdir()
    fichier = custom_dir / "innovation.py"
    fichier.write_text("def x(): pass")

    policy = SecurityPolicy(extra_sensitive_dirs=["brevet"])
    decision = policy.decide(fichier)

    assert decision.force_local is True


def test_fichier_illisible_ne_plante_jamais(tmp_path):
    policy = SecurityPolicy()
    fichier_inexistant = tmp_path / "nexiste_pas.py"
    decision = policy.decide(fichier_inexistant)
    assert decision.force_local is False
