"""Tests pour config.py — chargement de graphmind.toml."""
from graphmind.config import GraphmindConfig, load_config, write_example_config


def test_sans_fichier_de_config_retourne_les_valeurs_par_defaut(tmp_path):
    config = load_config(tmp_path)
    assert config == GraphmindConfig()


def test_charge_les_valeurs_du_fichier_toml(tmp_path):
    (tmp_path / "graphmind.toml").write_text("""
[security]
extra_sensitive_dirs = ["brevet"]

[cluster]
fine_resolution = 0.9
""")
    config = load_config(tmp_path)
    assert config.extra_sensitive_dirs == ["brevet"]
    assert config.fine_resolution == 0.9
    assert config.coarse_resolution == 0.15


def test_fichier_toml_corrompu_ne_plante_pas(tmp_path):
    (tmp_path / "graphmind.toml").write_text("ceci n'est pas du TOML valide {{{")
    config = load_config(tmp_path)
    assert config == GraphmindConfig()


def test_write_example_config_produit_un_fichier_lisible(tmp_path):
    destination = tmp_path / "graphmind.toml"
    write_example_config(destination)
    assert destination.is_file()
    content = destination.read_text(encoding="utf-8")
    assert "[security]" in content
    assert "[cluster]" in content
