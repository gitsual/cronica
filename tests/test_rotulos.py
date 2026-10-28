import pytest

from cronica.historia import Commit
from cronica.rotulos import chip, clave, limpiar, pr_y_titulo


def c(asunto: str, cuerpo: str = "", tags=()) -> Commit:
    return Commit("a" * 40, "2026-01-01", "Ana", ["p"], asunto, cuerpo, tags=list(tags))


@pytest.mark.parametrize("asunto, cuerpo, esperado", [
    ("Merge pull request #12 from ana/login", "Pantalla de login\n\nmás texto", (12, "Pantalla de login")),
    ("Merge pull request #12 from ana/login", "", (12, "Merge pull request #12 from ana/login")),
    ("Merged PR 345: Añade la tabla", "", (345, "Añade la tabla")),
    ("Pull request #38: TIENDA-482 | WEB-D02 | Navbar y Select", "", (38, "TIENDA-482 | WEB-D02 | Navbar y Select")),
    ("Merge branch 'feat/menu' into 'main'", "Menú lateral\n\nSee merge request grupo/app!7", (7, "Menú lateral")),
    ("Añade el modo oscuro (#41)", "", (41, "Añade el modo oscuro")),
    ("feat(ui): botón primario", "", (None, "feat(ui): botón primario")),
])
def test_pr_y_titulo(asunto, cuerpo, esperado):
    assert pr_y_titulo(c(asunto, cuerpo)) == esperado


@pytest.mark.parametrize("entrada, salida", [
    ("feat(ui): botón primario", "Botón primario"),
    ("TIENDA-482 | WEB-D02 | Navbar y Select", "Navbar y Select"),
    ("Feature/TIENDA-317 plugin de Figma", "Plugin de Figma"),
    ("add-login-page", "Add login page"),
    ("ana/add_dark_mode", "Add dark mode"),
    ("x" * 30 + " " + "y" * 30 + " " + "z" * 30, "X" + "x" * 29 + " " + "y" * 30 + "…"),
    ("", "Sin título"),
])
def test_limpiar(entrada, salida):
    assert limpiar(entrada) == salida


def test_chip_y_clave():
    commit = c("Pull request #38: TIENDA-482 | Navbar", tags=["v1.0"])
    assert clave(commit) == "TIENDA-482"
    assert chip(commit) == "#38 · TIENDA-482 · v1.0 · aaaaaaa"
