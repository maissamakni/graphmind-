"""Tests pour les 12 langages ajoutés lors de l'extension multi-langages
(JS/TS/TSX, C/C++, Go, Rust, Kotlin, Swift, Dart, SQL, Scala, PowerShell).
Chaque test utilise du code réel représentatif, avec les mêmes principes
que les tests historiques : classe/struct -> fonction/méthode -> appel."""
from graphmind.extractors.code import extract_code_file


def test_javascript_classe_methode_appel_et_import(tmp_path):
    fichier = tmp_path / "account.js"
    fichier.write_text(
        "import { Helper } from './helper';\n"
        "class Account {\n"
        "    checkPassword(password) {\n"
        "        return Helper.verify(password);\n"
        "    }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "account.js", "javascript")
    labels = {n.label for n in result.nodes}
    assert "Account" in labels
    assert "checkPassword()" in labels
    assert result.raw_calls[0]["callee_name"] == "verify"


def test_jsx_est_gere_par_la_grammaire_javascript_standard(tmp_path):
    fichier = tmp_path / "component.jsx"
    fichier.write_text(
        "class Account {\n"
        "    render() {\n"
        "        return <div>{this.checkPassword()}</div>;\n"
        "    }\n"
        "    checkPassword() { return true; }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "component.jsx", "javascript")
    assert not result.extraction_incomplete
    labels = {n.label for n in result.nodes}
    assert "render()" in labels
    assert "checkPassword()" in labels


def test_typescript_classe_et_methode(tmp_path):
    fichier = tmp_path / "account.ts"
    fichier.write_text(
        "class Account {\n"
        "    checkPassword(password: string): boolean {\n"
        "        return true;\n"
        "    }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "account.ts", "typescript")
    labels = {n.label for n in result.nodes}
    assert "Account" in labels
    assert "checkPassword()" in labels


def test_tsx_gere_jsx_et_typescript_ensemble(tmp_path):
    fichier = tmp_path / "component.tsx"
    fichier.write_text(
        "class Account {\n"
        "    render(): JSX.Element {\n"
        "        return <div>{this.checkPassword()}</div>;\n"
        "    }\n"
        "    checkPassword(): boolean { return true; }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "component.tsx", "tsx")
    assert not result.extraction_incomplete
    labels = {n.label for n in result.nodes}
    assert "checkPassword()" in labels


def test_c_fonction_et_appel(tmp_path):
    fichier = tmp_path / "account.c"
    fichier.write_text(
        "#include <helper.h>\n"
        "int check_password(char *password) {\n"
        "    return verify(password);\n"
        "}\n"
    )
    result = extract_code_file(fichier, "account.c", "c")
    labels = {n.label for n in result.nodes}
    assert "check_password()" in labels
    assert result.raw_calls[0]["callee_name"] == "verify"
    assert any(r["module"] == "helper.h" for r in result.raw_imports)


def test_cpp_classe_methode_et_appel(tmp_path):
    fichier = tmp_path / "account.cpp"
    fichier.write_text(
        "class Account {\n"
        "public:\n"
        "    bool checkPassword(std::string password) {\n"
        "        return verify(password);\n"
        "    }\n"
        "};\n"
    )
    result = extract_code_file(fichier, "account.cpp", "cpp")
    labels = {n.label for n in result.nodes}
    assert "Account" in labels
    assert "checkPassword()" in labels
    assert result.raw_calls[0]["callee_name"] == "verify"


def test_go_struct_methode_avec_recepteur_et_fonction(tmp_path):
    fichier = tmp_path / "account.go"
    fichier.write_text(
        "package main\n"
        "import \"fmt\"\n"
        "type Account struct { Password string }\n"
        "func (a *Account) CheckPassword(password string) bool {\n"
        "    return fmt.Sprintf(password) == a.Password\n"
        "}\n"
    )
    result = extract_code_file(fichier, "account.go", "go")
    labels = {n.label for n in result.nodes}
    assert "Account" in labels
    assert "CheckPassword()" in labels
    # "fmt" est une bibliothèque standard externe, jamais un fichier local
    # du projet — reste donc non résolue, ce qui est le comportement correct.
    assert any(r["module"] == "fmt" for r in result.raw_imports)


def test_go_methode_a_recepteur_rattachee_au_struct(tmp_path):
    """Bug corrigé : une méthode à récepteur `func (a *Account) M()` est
    déclarée EN DEHORS du struct en Go — désormais rattachée au struct
    lui-même, pas au fichier."""
    fichier = tmp_path / "account.go"
    fichier.write_text(
        "package main\n"
        "type Account struct { Password string }\n"
        "func (a *Account) CheckPassword() bool { return true }\n"
        "func StandaloneFunc() bool { return true }\n"
    )
    result = extract_code_file(fichier, "account.go", "go")
    account_id = next(n.id for n in result.nodes if n.label == "Account")
    method_id = next(n.id for n in result.nodes if n.label == "CheckPassword()")
    standalone_id = next(n.id for n in result.nodes if n.label == "StandaloneFunc()")
    contains_edges = {(e.source, e.target) for e in result.edges if e.relation == "contains"}
    assert (account_id, method_id) in contains_edges
    assert (account_id, standalone_id) not in contains_edges


def test_rust_impl_reouvre_le_struct_sans_dupliquer(tmp_path):
    """Test central pour Rust : impl Account { ... } doit rattacher ses
    méthodes au MÊME nœud que le struct Account, pas en créer un second."""
    fichier = tmp_path / "account.rs"
    fichier.write_text(
        "struct Account { password: String }\n"
        "impl Account {\n"
        "    fn check_password(&self, password: &str) -> bool {\n"
        "        verify(password)\n"
        "    }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "account.rs", "rust")
    account_nodes = [n for n in result.nodes if n.label == "Account"]
    assert len(account_nodes) == 1, "impl ne doit jamais dupliquer le nœud struct"
    contains_edges = [e for e in result.edges if e.relation == "contains"]
    assert any(e.source == account_nodes[0].id for e in contains_edges)


def test_kotlin_classe_methode_et_appel(tmp_path):
    fichier = tmp_path / "Account.kt"
    fichier.write_text(
        "class Account {\n"
        "    fun checkPassword(password: String): Boolean {\n"
        "        return Helper.verify(password)\n"
        "    }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "Account.kt", "kotlin")
    labels = {n.label for n in result.nodes}
    assert "checkPassword()" in labels
    assert result.raw_calls[0]["callee_name"] == "verify"


def test_swift_classe_methode_et_appel(tmp_path):
    fichier = tmp_path / "Account.swift"
    fichier.write_text(
        "class Account {\n"
        "    func checkPassword(password: String) -> Bool {\n"
        "        return Helper.verify(password)\n"
        "    }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "Account.swift", "swift")
    labels = {n.label for n in result.nodes}
    assert "checkPassword()" in labels
    assert result.raw_calls[0]["callee_name"] == "verify"


def test_dart_classe_et_methode_sans_doublon(tmp_path):
    """Test central pour Dart : signature/corps en nœuds frères ne doit
    jamais produire un nœud dupliqué de la méthode."""
    fichier = tmp_path / "account.dart"
    fichier.write_text(
        "class Account {\n"
        "    bool checkPassword(String password) {\n"
        "        return true;\n"
        "    }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "account.dart", "dart")
    method_nodes = [n for n in result.nodes if n.label == "checkPassword()"]
    assert len(method_nodes) == 1, "la méthode ne doit apparaître qu'une seule fois"


def test_dart_resout_les_appels_simples_et_qualifies(tmp_path):
    """Bug réel corrigé : le corps d'une fonction (nœud frère suivant en
    Dart) était marqué 'consommé' AVANT même d'être exploré, empêchant
    toute détection d'appel à l'intérieur."""
    fichier = tmp_path / "account.dart"
    fichier.write_text(
        "class Account {\n"
        "    bool checkPassword(String password) {\n"
        "        return Helper.verify(password);\n"
        "    }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "account.dart", "dart")
    assert len(result.raw_calls) == 1
    assert result.raw_calls[0]["callee_name"] == "verify"


def test_sql_fonction_stockee_et_appel(tmp_path):
    fichier = tmp_path / "account.sql"
    fichier.write_text(
        "CREATE FUNCTION check_password(pw TEXT) RETURNS BOOLEAN AS $$\n"
        "BEGIN\n"
        "    RETURN verify(pw);\n"
        "END;\n"
        "$$ LANGUAGE plpgsql;\n"
    )
    result = extract_code_file(fichier, "account.sql", "sql")
    labels = {n.label for n in result.nodes}
    assert "check_password()" in labels
    assert result.raw_calls[0]["callee_name"] == "verify"


def test_scala_classe_methode_et_appel(tmp_path):
    fichier = tmp_path / "Account.scala"
    fichier.write_text(
        "class Account {\n"
        "    def checkPassword(password: String): Boolean = {\n"
        "        Helper.verify(password)\n"
        "    }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "Account.scala", "scala")
    labels = {n.label for n in result.nodes}
    assert "checkPassword()" in labels
    assert result.raw_calls[0]["callee_name"] == "verify"


def test_powershell_fonction_appel_et_import_module(tmp_path):
    fichier = tmp_path / "Account.ps1"
    fichier.write_text(
        "Import-Module Helper\n"
        "function CheckPassword {\n"
        "    param($password)\n"
        "    Verify $password\n"
        "}\n"
    )
    result = extract_code_file(fichier, "Account.ps1", "powershell")
    labels = {n.label for n in result.nodes}
    assert "CheckPassword()" in labels
    assert any(r["module"] == "Helper" for r in result.raw_imports)
    assert result.raw_calls[0]["callee_name"] == "Verify"


def test_powershell_import_module_nest_jamais_traite_comme_un_appel(tmp_path):
    fichier = tmp_path / "Account.ps1"
    fichier.write_text("Import-Module Helper\n")
    result = extract_code_file(fichier, "Account.ps1", "powershell")
    assert result.raw_calls == []  # Import-Module ne doit jamais finir en raw_call


def test_powershell_classe_ps5_et_methode(tmp_path):
    """PowerShell 5+ supporte les classes — vérifié empiriquement que
    class_statement/class_method_definition sont bien couverts."""
    fichier = tmp_path / "Account.ps1"
    fichier.write_text(
        "class Account {\n"
        "    [bool] CheckPassword([string]$password) {\n"
        "        return $true\n"
        "    }\n"
        "}\n"
    )
    result = extract_code_file(fichier, "Account.ps1", "powershell")
    labels = {n.label for n in result.nodes}
    assert "Account" in labels
    assert "CheckPassword()" in labels
    contains_edges = {(e.source, e.target) for e in result.edges if e.relation == "contains"}
    account_id = next(n.id for n in result.nodes if n.label == "Account")
    method_id = next(n.id for n in result.nodes if n.label == "CheckPassword()")
    assert (account_id, method_id) in contains_edges
