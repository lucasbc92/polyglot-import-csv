"""Every text the window shows is in English (advisor's review of report v2.3).

Scans the string constants of the GUI modules, docstrings left out, for the accented
letters of Portuguese and for Portuguese words the window used to show.
"""

import ast
import re
from pathlib import Path

GUI = Path(__file__).resolve().parents[1] / "src" / "polyglotimportcsv" / "gui"

_PORTUGUESE = re.compile(
    r"[áéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ]|\b(?:de|da|para|não|nenhum|Selecione|Arquivo|linhas|"
    r"Fonte|fonte|Pronto|Executar|Copiar|Salvar|Verificar|Editar|Opções|Escolher|Remover|"
    r"Adicionar|Procurar|Todos|Amostra|Concluído|Falhou|Interromper|Ajuda|Bloco|Lote)\b"
)


def _docstrings(tree):
    nodes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, nodes) and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }


def test_gui_shows_no_portuguese_text():
    found = []
    for path in sorted(GUI.rglob("*.py")):
        if path.name == "style.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstrings(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in skip and _PORTUGUESE.search(node.value)):
                found.append(f"{path.relative_to(GUI)}:{node.lineno}: {node.value[:70]!r}")
    assert not found, "Portuguese text in the GUI:\n" + "\n".join(found)
