import os
import subprocess
from pathlib import Path

import pytest


class Repo:
    """Un repositorio git de prueba con fechas fijas, para construir historias a mano."""

    def __init__(self, raiz: Path):
        self.raiz = raiz
        raiz.mkdir(parents=True)
        self.dia = 0
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Ana")
        self.git("config", "user.email", "ana@example.com")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args: str, autor: str | None = None) -> str:
        env = {**os.environ}
        fecha = f"2026-01-{1 + self.dia:02d}T12:00:00"
        env.update(GIT_AUTHOR_DATE=fecha, GIT_COMMITTER_DATE=fecha)
        if autor:
            env.update(GIT_AUTHOR_NAME=autor, GIT_AUTHOR_EMAIL=f"{autor.lower()}@example.com")
        r = subprocess.run(["git", "-C", str(self.raiz), *args], capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    def escribir(self, ficheros: dict[str, str]) -> None:
        for ruta, texto in ficheros.items():
            p = self.raiz / ruta
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(texto, encoding="utf-8")

    def commit(self, mensaje: str, ficheros: dict[str, str] | None = None, autor: str | None = None) -> str:
        self.dia += 1
        if ficheros:
            self.escribir(ficheros)
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", mensaje, autor=autor)
        return self.git("rev-parse", "HEAD")

    def pr(self, numero: int, rama: str, titulo: str, ficheros: dict[str, str]) -> str:
        self.git("switch", "-q", "-c", rama)
        self.commit(f"wip {titulo}", ficheros)
        self.git("switch", "-q", "main")
        self.dia += 1
        self.git("merge", "-q", "--no-ff", rama, "-m", f"Merge pull request #{numero} from ana/{rama}\n\n{titulo}")
        return self.git("rev-parse", "HEAD")


@pytest.fixture(autouse=True)
def _ajustes_aislados(tmp_path_factory, monkeypatch):
    """Ningún test lee ni escribe los ajustes de verdad del usuario."""
    monkeypatch.setenv("CRONICA_CONFIG", str(tmp_path_factory.mktemp("conf") / "settings.json"))


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path / "proyecto")


def pagina(titulo: str, enlaces: list[str] = (), cuerpo: str = "") -> str:
    links = "".join(f'<a href="{e}">{e}</a> ' for e in enlaces)
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{titulo}</title>"
            "<style>body{font:20px sans-serif;margin:40px} nav a{margin-right:12px}"
            "@media (prefers-color-scheme: dark){body{background:#111;color:#eee}}</style></head>"
            f"<body><nav>{links}</nav><h1>{titulo}</h1><p>{cuerpo or 'Contenido de ' + titulo}</p>"
            "<button>Aceptar</button></body></html>")
