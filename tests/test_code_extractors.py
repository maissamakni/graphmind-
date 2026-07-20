"""Tests pour extractors/code/ — extraction multi-langages (Python, Java,
PHP, C#) via un walker AST commun paramétré par langage (LanguageSpec).

Chaque test utilise un extrait de code réel représentatif, avec les
mêmes assertions structurelles que l'ancien test Python historique
(classe -> méthode -> appel), pour garantir un comportement équivalent
entre langages."""
from graphmind.extractors.code import SPECS_BY_LANGUAGE, extract_code_file


def test_tous_les_langages_annonces_sont_enregistres():
    assert set(SPECS_BY_LANGUAGE.keys()) == {
        "python", "javascript", "typescript", "tsx", "java", "c", "cpp",
        "csharp", "go", "rust", "php", "kotlin", "swift", "dart", "sql",
        "scala", "powershell",
    }


def test_langage_non_supporte_ne_plante_pas(tmp_path):
    fichier = tmp_path / "script.rb"
    fichier.write_text("def foo; end")
    result = extract_code_file(fichier, "script.rb", "ruby")
    assert result.extraction_incomplete is True
    assert result.nodes == []


# --- Python (garantit l'équivalence avec l'ancien extracteur dédié) ---

def test_python_classe_methode_et_appel(tmp_path):
    fichier = tmp_path / "account.py"
    fichier.write_text(
        "class Account:\n"
        "    def check_password(self, password):\n"
        "        return verify(password)\n"
    )
    result = extract_code_file(fichier, "account.py", "python")
    labels = {n.label for n in result.nodes}
    assert "Account" in labels
    assert "check_password()" in labels
    assert result.raw_calls[0]["callee_name"] == "verify"


# --- Java ---

def test_java_classe_methode_appel_et_import(tmp_path):
    fichier = tmp_path / "Account.java"
    fichier.write_text(
        "package com.example;\n"
        "import com.example.util.Helper;\n"
        "public class Account {\n"
        "    public boolean checkPassword(String password) {\n"
        "        return Helper.verify(password);\n"
        "    }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "Account.java", "java")
    labels = {n.label for n in result.nodes}
    assert "Account" in labels
    assert "checkPassword()" in labels
    assert result.raw_calls[0]["callee_name"] == "verify"
    # Sans known_modules complet (extraction isolée), l'import reste en
    # attente de résolution cross-fichier (cli.py) plutôt qu'un lien mort.
    assert any(r["module"] == "com.example.util.Helper" for r in result.raw_imports)


def test_java_interface_est_reconnue(tmp_path):
    fichier = tmp_path / "Payable.java"
    fichier.write_text("public interface Payable {\n    void pay();\n}\n")
    result = extract_code_file(fichier, "Payable.java", "java")
    labels = {n.label for n in result.nodes}
    assert "Payable" in labels
    assert "pay()" in labels


# --- PHP ---

def test_php_classe_methode_et_fonction_globale(tmp_path):
    fichier = tmp_path / "account.php"
    fichier.write_text(
        "<?php\n"
        "class Account {\n"
        "    public function checkPassword($password) {\n"
        "        return Helper::verify($password);\n"
        "    }\n"
        "}\n"
        "function findByEmail($email) {\n"
        "    return new Account();\n"
        "}\n"
    )
    result = extract_code_file(fichier, "account.php", "php")
    labels = {n.label for n in result.nodes}
    assert "Account" in labels
    assert "checkPassword()" in labels
    assert "findByEmail()" in labels
    # scoped_call_expression (appel statique Classe::methode())
    assert result.raw_calls[0]["callee_name"] == "verify"


def test_php_appel_de_methode_sur_instance_est_resolu(tmp_path):
    fichier = tmp_path / "account.php"
    fichier.write_text(
        "<?php\n"
        "class Account {\n"
        "    public function checkPassword($p) { return true; }\n"
        "    public function login($p) {\n"
        "        $this->checkPassword($p);\n"
        "        return true;\n"
        "    }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "account.php", "php")
    calls = {(e.source, e.target) for e in result.edges if e.relation == "calls"}
    login_id = next(n.id for n in result.nodes if n.label == "login()")
    check_id = next(n.id for n in result.nodes if n.label == "checkPassword()")
    assert (login_id, check_id) in calls


# --- C# ---

def test_csharp_classe_methode_appel_et_using(tmp_path):
    fichier = tmp_path / "Account.cs"
    fichier.write_text(
        "using App.Utils;\n"
        "public class Account {\n"
        "    public bool CheckPassword(string password) {\n"
        "        return Helper.Verify(password);\n"
        "    }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "Account.cs", "csharp")
    labels = {n.label for n in result.nodes}
    assert "Account" in labels
    assert "CheckPassword()" in labels
    assert result.raw_calls[0]["callee_name"] == "Verify"
    assert any(r["module"] == "App.Utils" for r in result.raw_imports)


def test_csharp_struct_est_reconnue(tmp_path):
    fichier = tmp_path / "Point.cs"
    fichier.write_text("public struct Point {\n    public int GetX() { return 0; }\n}\n")
    result = extract_code_file(fichier, "Point.cs", "csharp")
    labels = {n.label for n in result.nodes}
    assert "Point" in labels
    assert "GetX()" in labels


# --- Collision d'id au sein d'un même fichier (bug réel rencontré) ---

def test_classe_et_methode_de_meme_nom_insensible_a_la_casse_ne_collisionnent_pas(tmp_path):
    """Cas réel : une classe 'Login' et une méthode 'login()' produisent le
    même id via make_id() (slug insensible à la casse) — doivent être
    différenciées, sinon la méthode se retrouve comme 'contenant
    elle-même' (bug observé concrètement)."""
    fichier = tmp_path / "Login.java"
    fichier.write_text(
        "public class Login {\n"
        "    public boolean login(String password) {\n"
        "        return true;\n"
        "    }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "Login.java", "java")
    ids = [n.id for n in result.nodes]
    assert len(ids) == len(set(ids)), "deux nœuds distincts ne doivent jamais partager le même id"
    # Aucune relation d'un nœud vers lui-même :
    assert all(e.source != e.target for e in result.edges)
