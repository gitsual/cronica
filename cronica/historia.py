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


def _blobs(repo: Path, sha: str) -> dict[str, str]:
    """{ruta: blob} del árbol de un commit."""
    salida = {}
    for linea in git(repo, "ls-tree", "-r", sha).splitlines():
        meta, ruta = linea.split("	", 1)
        partes = meta.split()
        if len(partes) == 3 and partes[1] == "blob":
            salida[ruta] = partes[2]
    return salida


def _lineas_blobs(repo: Path, blobs: list[str]) -> int:
    """Líneas de texto de una lista de blobs (los binarios no cuentan), con un solo git cat-file."""
    if not blobs:
        return 0
    r = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], input=("\n".join(blobs) + "\n").encode(),
                       capture_output=True)
    total, datos, i = 0, r.stdout, 0
    while i < len(datos):
        fin = datos.index(b"\n", i)
        cab = datos[i:fin].split()
        if len(cab) < 3:
            break
        n = int(cab[2])
        cuerpo = datos[fin + 1: fin + 1 + n]
        if b"\0" not in cuerpo[:8000]:
            total += cuerpo.count(b"\n")
        i = fin + 1 + n + 1
    return total


def extraccion(repo_a: Path, sha_a: str, repo_b: Path, sha_b: str) -> dict:
    """Qué se muda de A a B: los ficheros del primer commit de B que ya estaban, idénticos, en A.

    Se comparan por contenido (blob), así que da igual que cambien de carpeta al mudarse.
    """
    a, b = _blobs(repo_a, sha_a), _blobs(repo_b, sha_b)
    en_a = {}
    for ruta, blob in a.items():
        en_a.setdefault(blob, ruta)
    mudan = [(en_a[blob], ruta) for ruta, blob in b.items() if blob in en_a]
    origen = [o for o, _ in mudan]
    carpetas: dict[str, int] = {}
    for o in origen:
        partes = o.split("/")
        clave = "/".join(partes[:2]) if len(partes) > 2 else (partes[0] if len(partes) > 1 else "(raíz)")
        carpetas[clave] = carpetas.get(clave, 0) + 1
    paso = max(1, len(origen) // 36)
    return {
        "ficheros": len(mudan), "ficheros_a": len(a), "ficheros_b": len(b),
        "lineas_mudan": _lineas_blobs(repo_b, [b[d] for _, d in mudan]),
        "lineas_a": cifras_git(repo_a, sha_a)["lineas"], "lineas_b": cifras_git(repo_b, sha_b)["lineas"],
        "carpetas": sorted(carpetas.items(), key=lambda x: -x[1])[:6],
        "muestra": sorted(origen)[::paso][:36],
    }


def en_fecha(repo: Path, rama: str, fecha: str) -> str | None:
    """El último commit de la rama (por su primer padre) hecho ese día o antes; None si aún no existía."""
    sha = git(repo, "rev-list", "-1", "--first-parent", f"--before={fecha} 23:59:59", rama).strip()
    return sha or None


def autores(repo: Path, sha: str) -> set[str]:
    return {l.split("\t", 1)[1].strip() for l in git(repo, "shortlog", "-sn", "--no-merges", sha, entrada="").splitlines()
            if "\t" in l}


def cifras_ecosistema(repos: list[tuple[Path, str]], fecha: str, _cache: dict = {}) -> dict[str, int]:
    """Las cifras de varios repositorios juntos tal como estaban ese día: ficheros, líneas y commits sumados,
    autores sin repetir. Es lo que mide el alcance real cuando un proyecto se reparte en varios repositorios."""
    total = {"ficheros": 0, "lineas": 0, "commits": 0}
    gente: set[str] = set()
    for repo, rama in repos:
        sha = en_fecha(repo, rama, fecha)
        if not sha:
            continue
        clave = (str(repo), sha)
        if clave not in _cache:
            _cache[clave] = (cifras_git(repo, sha), autores(repo, sha))
        c, a = _cache[clave]
        for k in total:
            total[k] += c[k]
        gente |= a
    return {**total, "autores": len(gente)}
