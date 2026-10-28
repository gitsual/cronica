"""Lo que se lee del git del proyecto: commits de la rama, hitos y cifras.

Nunca escribe en el repositorio original: solo git log / show / ls-tree / diff.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ARBOL_VACIO = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
# Ficheros que no cuentan como «cambio» ni como líneas del proyecto.
NO_CUENTAN = (
    ":(exclude,glob)**/package-lock.json", ":(exclude,glob)**/pnpm-lock.yaml", ":(exclude,glob)**/yarn.lock",
    ":(exclude,glob)**/*.min.js", ":(exclude,glob)**/*.map", ":(exclude,glob)**/*.svg",
)


class ErrorGit(RuntimeError):
    pass


def git(repo: Path, *args: str, entrada: str | None = None) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, input=entrada,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise ErrorGit(f"git {' '.join(args[:3])}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


@dataclass
class Commit:
    sha: str
    fecha: str          # AAAA-MM-DD
    autor: str
    padres: list[str]
    asunto: str
    cuerpo: str
    churn: int = 0      # líneas tocadas respecto al primer padre
    tags: list[str] = field(default_factory=list)

    @property
    def merge(self) -> bool:
        return len(self.padres) > 1


def es_repo(carpeta: Path) -> bool:
    try:
        return git(carpeta, "rev-parse", "--is-inside-work-tree").strip() == "true"
    except (ErrorGit, OSError):
        return False


def raiz(carpeta: Path) -> Path:
    return Path(git(carpeta, "rev-parse", "--show-toplevel").strip())


def rama_actual(repo: Path) -> str:
    try:
        return git(repo, "symbolic-ref", "--short", "-q", "HEAD").strip() or "HEAD"
    except ErrorGit:
        return "HEAD"


def commits(repo: Path, rama: str) -> list[Commit]:
    """La historia de la rama por su primer padre, del más viejo al más nuevo, con lo que cambia cada uno."""
    salida = git(repo, "log", "--first-parent", "--reverse", "--date=short",
                 "--format=%x1e%H%x1f%ad%x1f%an%x1f%P%x1f%s%x1f%b%x1f", rama)
    lista: list[Commit] = []
    for bloque in salida.split("\x1e"):
        if not bloque.strip():
            continue
        sha, fecha, autor, padres, asunto, cuerpo, _ = bloque.split("\x1f")
        lista.append(Commit(sha.strip(), fecha, autor, padres.split(), asunto.strip(), cuerpo.strip()))
    _churn(repo, rama, {c.sha: c for c in lista})
    _tags(repo, {c.sha: c for c in lista})
    return lista


def _churn(repo: Path, rama: str, por_sha: dict[str, Commit]) -> None:
    salida = git(repo, "log", "--first-parent", "--diff-merges=first-parent", "--numstat",
                 "--format=%x1e%H", rama, "--", ".", *NO_CUENTAN)
    for bloque in salida.split("\x1e"):
        lineas = bloque.strip().splitlines()
        if not lineas or lineas[0] not in por_sha:
            continue
        total = 0
        for l in lineas[1:]:
            partes = l.split("\t")
            if len(partes) == 3 and partes[0].isdigit():
                total += int(partes[0]) + int(partes[1])
        por_sha[lineas[0]].churn = total


def _tags(repo: Path, por_sha: dict[str, Commit]) -> None:
    salida = git(repo, "for-each-ref", "refs/tags", "--format=%(objectname) %(*objectname) %(refname:short)")
    for linea in salida.splitlines():
        partes = linea.split()
        nombre = partes[-1]
        for sha in partes[:-1]:
            if sha in por_sha:
                por_sha[sha].tags.append(nombre)


def candidatos(lista: list[Commit]) -> list[Commit]:
    """Si la rama se hizo con merges (PR), los hitos son los merges y los tags; si no, todos los commits."""
    merges = [c for c in lista if c.merge or c.tags]
    if len(merges) >= 3:
        elegidos = {c.sha for c in merges} | {lista[0].sha, lista[-1].sha}
        return [c for c in lista if c.sha in elegidos]
    return list(lista)


def muestrear(cands: list[Commit], maximo: int, todos: list[Commit] | None = None) -> list[Commit]:
    """Deja como mucho `maximo` hitos, repartidos por cantidad de cambio y no por fecha.

    El peso de un candidato es lo que cambió desde el candidato anterior (sumando los commits intermedios
    de `todos`). Siempre se quedan el primero y el último.
    """
    if len(cands) <= maximo:
        return list(cands)
    peso = _pesos(cands, todos or cands)
    acumulado, total = [], 0
    for c in cands:
        total += max(peso[c.sha], 1)
        acumulado.append(total)
    elegidos = {0, len(cands) - 1}
    for k in range(1, maximo - 1):
        objetivo = total * k / (maximo - 1)
        j = min(range(len(cands)), key=lambda i: (abs(acumulado[i] - objetivo), i))
        while j in elegidos and j + 1 < len(cands) - 1:
            j += 1
        elegidos.add(j)
    return [cands[i] for i in sorted(elegidos)][:maximo]


def _pesos(cands: list[Commit], todos: list[Commit]) -> dict[str, int]:
    marcas = {c.sha for c in cands}
    peso, acumulado = {}, 0
    for c in todos:
        acumulado += c.churn
        if c.sha in marcas:
            peso[c.sha] = acumulado
            acumulado = 0
    return peso


def ficheros(repo: Path, sha: str) -> list[str]:
    return git(repo, "ls-tree", "-r", "--name-only", sha).splitlines()


def leer(repo: Path, sha: str, ruta: str) -> str | None:
    try:
        return git(repo, "show", f"{sha}:{ruta}")
    except ErrorGit:
        return None


def cifras_git(repo: Path, sha: str) -> dict[str, int]:
    """Ficheros, líneas, commits y autores hasta ese commit, sin hacer checkout."""
    nfich = len(ficheros(repo, sha))
    stat = git(repo, "diff", "--shortstat", ARBOL_VACIO, sha, "--", ".", *NO_CUENTAN)
    m = re.search(r"(\d+) insertion", stat)
    autores = git(repo, "shortlog", "-sn", "--no-merges", sha, entrada="").splitlines()
    return {
        "ficheros": nfich,
        "lineas": int(m.group(1)) if m else 0,
        "commits": int(git(repo, "rev-list", "--count", sha).strip()),
        "autores": len([a for a in autores if a.strip()]),
    }
