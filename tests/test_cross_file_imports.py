"""Tests pour la résolution cross-fichier des imports par nom de symbole
(cli.py) — prend le relais quand l'approximation "chemin de fichier ->
module" échoue (cas fréquent pour PHP/Kotlin/Scala, dont les espaces de
noms ne suivent pas forcément le chemin de fichier)."""
from graphmind.cli import _last_import_component, _resolve_cross_file_calls
from graphmind.schema import Confidence, Edge, ExtractionResult, Modality, Node


def test_last_import_component_avec_backslash_php():
    assert _last_import_component("App\\Utils\\Helper") == "Helper"


def test_last_import_component_avec_points():
    assert _last_import_component("com.example.data.Helper") == "Helper"


def test_last_import_component_symbole_seul():
    assert _last_import_component("Helper") == "Helper"


def test_resolution_import_par_nom_de_symbole_php():
    """Cas réel : PHP 'use App\\Utils\\Helper;' alors que le vrai fichier
    est dans src/Utils/Helper.php — chemin de fichier ne correspond pas du
    tout au namespace déclaré, résolu quand même par nom de classe."""
    helper_file = ExtractionResult(nodes=[
        Node("helper_php", "Helper.php", Modality.CODE, "src/Utils/Helper.php"),
        Node("helper_php_helper", "Helper", Modality.CODE, "src/Utils/Helper.php"),
    ])
    account_file = ExtractionResult(nodes=[
        Node("account_php", "Account.php", Modality.CODE, "src/Services/Account.php"),
    ])
    account_file.raw_imports.append({
        "source_id": "account_php", "module": "App\\Utils\\Helper",
        "relation": "imports", "source_file": "src/Services/Account.php", "line": "L2",
    })

    results = [helper_file, account_file]
    _resolve_cross_file_calls(results)

    import_edges = [e for e in account_file.edges if e.relation == "imports"]
    assert len(import_edges) == 1
    assert import_edges[0].target == "helper_php_helper"


def test_resolution_import_reste_non_resolue_si_ambigue():
    """Deux classes 'Helper' dans le projet -> jamais résolu au hasard."""
    file_a = ExtractionResult(nodes=[Node("a_helper", "Helper", Modality.CODE, "a/Helper.php")])
    file_b = ExtractionResult(nodes=[Node("b_helper", "Helper", Modality.CODE, "b/Helper.php")])
    account_file = ExtractionResult(nodes=[Node("account_php", "Account.php", Modality.CODE, "Account.php")])
    account_file.raw_imports.append({
        "source_id": "account_php", "module": "App\\Helper",
        "relation": "imports", "source_file": "Account.php", "line": "L1",
    })

    results = [file_a, file_b, account_file]
    _resolve_cross_file_calls(results)

    assert account_file.edges == []


def test_namespace_entier_sans_declared_namespace_reste_non_resolu():
    """Si AUCUN fichier ne renseigne declared_namespace pour "App.Utils"
    (ex: extraction isolée sans cette info, ou langage qui ne fournit pas
    encore ce mécanisme), l'import de namespace entier reste non résolu —
    cf. test_resolution_import_de_namespace_entier_csharp pour le cas
    corrigé où declared_namespace EST disponible."""
    helper_file = ExtractionResult(nodes=[
        Node("helper_cs_helper", "Helper", Modality.CODE, "Data/Helper.cs"),
    ])  # pas de declared_namespace ici
    account_file = ExtractionResult(nodes=[Node("account_cs", "Account.cs", Modality.CODE, "Logic/Account.cs")])
    account_file.raw_imports.append({
        "source_id": "account_cs", "module": "App.Utils",
        "relation": "imports", "source_file": "Logic/Account.cs", "line": "L1",
    })

    results = [helper_file, account_file]
    _resolve_cross_file_calls(results)

    assert account_file.edges == []  # "Utils" ne correspond à aucun symbole réel, et aucun namespace déclaré


def test_resolution_import_de_namespace_entier_csharp():
    """Bug corrigé : 'using App.Utils;' importe tout un namespace, jamais
    une classe précise — résolu désormais en cherchant quel fichier
    déclare CE namespace (declared_namespace), pas juste par nom de
    symbole (qui ne peut pas fonctionner ici, "Helper" n'apparaît jamais
    dans le texte de l'import)."""
    helper_file = ExtractionResult(
        nodes=[Node("data_helper_cs", "Helper.cs", Modality.CODE, "Data/Helper.cs")],
        declared_namespace="App.Utils",
    )
    account_file = ExtractionResult(nodes=[Node("logic_account_cs", "Account.cs", Modality.CODE, "Logic/Account.cs")])
    account_file.raw_imports.append({
        "source_id": "logic_account_cs", "module": "App.Utils",
        "relation": "imports", "source_file": "Logic/Account.cs", "line": "L1",
    })

    results = [helper_file, account_file]
    _resolve_cross_file_calls(results)

    import_edges = [e for e in account_file.edges if e.relation == "imports"]
    assert len(import_edges) == 1
    assert import_edges[0].target == "data_helper_cs"


def test_namespace_entier_ambigu_reste_non_resolu():
    """Deux fichiers déclarent le MÊME namespace -> jamais résolu au hasard."""
    file_a = ExtractionResult(
        nodes=[Node("a_cs", "A.cs", Modality.CODE, "a/A.cs")], declared_namespace="App.Utils",
    )
    file_b = ExtractionResult(
        nodes=[Node("b_cs", "B.cs", Modality.CODE, "b/B.cs")], declared_namespace="App.Utils",
    )
    account_file = ExtractionResult(nodes=[Node("account_cs", "Account.cs", Modality.CODE, "Account.cs")])
    account_file.raw_imports.append({
        "source_id": "account_cs", "module": "App.Utils",
        "relation": "imports", "source_file": "Account.cs", "line": "L1",
    })

    results = [file_a, file_b, account_file]
    _resolve_cross_file_calls(results)

    assert account_file.edges == []
