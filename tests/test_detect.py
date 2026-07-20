"""Tests pour detect.py — détection et classification par modalité."""
from graphmind.detect import collect_files
from graphmind.schema import Modality


def test_detecte_un_fichier_python(tmp_path):
    (tmp_path / "login.py").write_text("def login(): pass")
    files = collect_files(tmp_path)
    assert len(files) == 1
    assert files[0].modality == Modality.CODE
    assert files[0].language == "python"


def test_ignore_les_dossiers_bruit_par_defaut(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git stuff")
    (tmp_path / "login.py").write_text("def login(): pass")
    files = collect_files(tmp_path)
    assert len(files) == 1
    assert files[0].path.name == "login.py"


def test_extra_ignore_dirs_configurable(tmp_path):
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "lib.py").write_text("def x(): pass")
    (tmp_path / "login.py").write_text("def login(): pass")

    files_sans_config = collect_files(tmp_path)
    assert len(files_sans_config) == 2

    files_avec_config = collect_files(tmp_path, extra_ignore_dirs=["vendor"])
    assert len(files_avec_config) == 1
    assert files_avec_config[0].path.name == "login.py"


def test_fichier_extension_inconnue_est_ignore(tmp_path):
    (tmp_path / "inconnu.xyz").write_text("contenu")
    files = collect_files(tmp_path)
    assert files == []
