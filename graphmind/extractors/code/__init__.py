"""Point d'entrée public de l'extraction de code multi-langages.

Ajouter un nouveau langage : écrire un <langage>_spec.py sur le modèle
des fichiers existants (node types VÉRIFIÉS empiriquement, pas devinés),
puis l'ajouter à SPECS_BY_LANGUAGE ci-dessous — aucune autre modification
nécessaire, ni ici, ni dans base.py, ni dans cli.py.
"""
from __future__ import annotations

from pathlib import Path

from .base import LanguageSpec, extract_code
from .c_spec import C_SPEC
from .cpp_spec import CPP_SPEC
from .csharp_spec import CSHARP_SPEC
from .dart_spec import DART_SPEC
from .go_spec import GO_SPEC
from .java_spec import JAVA_SPEC
from .javascript_spec import JAVASCRIPT_SPEC
from .kotlin_spec import KOTLIN_SPEC
from .php_spec import PHP_SPEC
from .powershell_spec import POWERSHELL_SPEC
from .python_spec import PYTHON_SPEC
from .rust_spec import RUST_SPEC
from .scala_spec import SCALA_SPEC
from .sql_spec import SQL_SPEC
from .swift_spec import SWIFT_SPEC
from .typescript_spec import TYPESCRIPT_SPEC
from .tsx_spec import TSX_SPEC
from ...schema import ExtractionResult

SPECS_BY_LANGUAGE: dict[str, LanguageSpec] = {
    "python": PYTHON_SPEC,
    "javascript": JAVASCRIPT_SPEC,
    "typescript": TYPESCRIPT_SPEC,
    "tsx": TSX_SPEC,
    "java": JAVA_SPEC,
    "c": C_SPEC,
    "cpp": CPP_SPEC,
    "csharp": CSHARP_SPEC,
    "go": GO_SPEC,
    "rust": RUST_SPEC,
    "php": PHP_SPEC,
    "kotlin": KOTLIN_SPEC,
    "swift": SWIFT_SPEC,
    "dart": DART_SPEC,
    "sql": SQL_SPEC,
    "scala": SCALA_SPEC,
    "powershell": POWERSHELL_SPEC,
}


def extract_code_file(
    path: Path, relative_path: str, language: str,
    known_modules: dict[str, str] | None = None,
) -> ExtractionResult:
    """Point d'entrée unique pour extraire un fichier de code, quel que
    soit le langage — dispatché via SPECS_BY_LANGUAGE. Retourne un
    ExtractionResult avec extraction_incomplete=True si le langage n'est
    pas (encore) supporté, plutôt que de planter."""
    spec = SPECS_BY_LANGUAGE.get(language)
    if spec is None:
        result = ExtractionResult()
        result.extraction_incomplete = True
        return result
    return extract_code(path, relative_path, spec, known_modules)
