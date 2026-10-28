"""Qué tipo de proyecto con interfaz hay en un commit y cómo se construye.

Se decide leyendo el árbol del commit (sin checkout). Tipos:
  storybook  un Storybook que se construye a estático; se fotografía componente a componente
  web        una app con script de build (Vite, Angular, React, Vue…); si el build no deja un
             index.html se arranca su servidor de desarrollo
  estatico   un index.html servido tal cual (raíz, docs/, public/, site/, src/)
"""
from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import historia

MARCOS = (
    "vite", "react-scripts", "@angular/cli", "@angular-devkit/build-angular", "@vue/cli-service", "next",
    "nuxt", "astro", "@sveltejs/kit", "svelte", "parcel", "webpack", "webpack-cli", "gatsby", "@remix-run/dev",
    "solid-start", "vuepress", "vitepress", "@docusaurus/core", "@11ty/eleventy", "preact-cli", "ember-cli",
)
SALIDAS_WEB = ("dist", "build", "out", "www", "public", "_site", "docs/.vitepress/dist", ".output/public")
SALIDAS_ESTATICO = ("", "docs", "public", "site", "src", "web", "www", "html")


@dataclass
class Receta:
    tipo: str                       # storybook | web | estatico
    dir: str = ""                   # carpeta del paquete (relativa a la raíz, posix)
    gestor: str | None = None       # npm | pnpm | yarn
    lock: str | None = None         # fichero de lock en la raíz
    construir: list[list[str]] = field(default_factory=list)   # intentos, en orden
    salidas: list[str] = field(default_factory=list)            # dónde buscar el resultado (relativas a la raíz)
    dev: list[str] | None = None    # servidor de desarrollo, para web sin build estático

    def a_dict(self) -> dict:
        return self.__dict__.copy()


def _json(repo: Path, sha: str, ruta: str) -> dict | None:
    texto = historia.leer(repo, sha, ruta)
    if texto is None:
        return None
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return None


def _gestor(nombres: set[str], d: str = "") -> tuple[str, str | None]:
    """El gestor por el lock de la carpeta del paquete o, si no tiene, el de la raíz (workspaces)."""
    for base in dict.fromkeys((d, "")):
        for lock, gestor in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("package-lock.json", "npm"),
                             ("npm-shrinkwrap.json", "npm")):
            ruta = posixpath.join(base, lock) if base else lock
            if ruta in nombres:
                return gestor, ruta
    return "npm", None


def _paquetes(lista: list[str]) -> list[str]:
    """Las carpetas con package.json (hasta tres niveles), la raíz primero."""
    dirs = []
    for f in lista:
        if posixpath.basename(f) == "package.json" and "node_modules/" not in f and f.count("/") <= 3:
            dirs.append(posixpath.dirname(f))
    return sorted(dirs, key=lambda d: (d.count("/") if d else -1, d))


def _correr(gestor: str, script: str) -> list[str]:
    return [gestor, "run", script] if gestor != "yarn" else ["yarn", script]


def _deps(pkg: dict) -> set[str]:
    return set(pkg.get("dependencies", {})) | set(pkg.get("devDependencies", {}))


def _salida_storybook(comando: str, base: str) -> list[str]:
    m = re.search(r"(?:-o|--output-dir)[ =]+(['\"]?)([^\s'\"]+)\1", comando)
    rel = m.group(2) if m else "storybook-static"
    return [posixpath.normpath(posixpath.join(base, rel))]


def detectar(repo: Path, sha: str, modo: str = "auto") -> Receta | None:
    lista = historia.ficheros(repo, sha)
    nombres = set(lista)
    paquetes = {d: _json(repo, sha, posixpath.join(d, "package.json")) for d in _paquetes(lista)}
    paquetes = {d: p for d, p in paquetes.items() if isinstance(p, dict)}

    if modo in ("auto", "storybook"):
        r = _storybook(paquetes, nombres)
        if r or modo == "storybook":
            return r
    if modo in ("auto", "web"):
        r = _web(paquetes, nombres)
        if r or modo == "web":
            return r
    return _estatico(nombres)


def _storybook(paquetes: dict[str, dict], nombres: set[str]) -> Receta | None:
    # 1. Un script que construye el Storybook, paquete a paquete y con la raíz primero: en un monorepo la raíz
    #    suele orquestar los pasos previos (tokens, librerías) antes de llamar al Storybook del workspace.
    #    Dentro de un paquete manda el nombre del script (storybook:build, build-storybook) sobre el comando.
    for d, pkg in paquetes.items():
        scripts = {k: v for k, v in (pkg.get("scripts") or {}).items() if isinstance(v, str)}
        por_nombre = sorted((k for k in scripts if re.fullmatch(r"(build[:-]storybook|storybook[:-]build)(:.*)?", k)),
                            key=lambda k: (k.count(":") + k.count("-"), k))
        por_comando = [k for k, v in scripts.items() if "build-storybook" in v or re.search(r"storybook\s+build", v)]
        elegido = (por_nombre or por_comando or [None])[0]
        if elegido:
            gestor, lock = _gestor(nombres, d)
            salidas = _salida_storybook(scripts[elegido], d)
            salidas += [posixpath.join(x, "storybook-static") if x else "storybook-static" for x in paquetes]
            return Receta("storybook", d, gestor, lock, [_correr(gestor, elegido)], list(dict.fromkeys(salidas)))
    # 3. Una carpeta .storybook sin script: se llama al CLI directamente.
    for d, pkg in paquetes.items():
        main = [n for n in nombres if n.startswith(posixpath.join(d, ".storybook/main.") if d else ".storybook/main.")]
        if main and any(dep.startswith("@storybook/") or dep == "storybook" for dep in _deps(pkg)):
            gestor, lock = _gestor(nombres, d)
            return Receta("storybook", d, gestor, lock,
                          [["npx", "storybook", "build", "-o", "storybook-static"],
                           ["npx", "build-storybook", "-o", "storybook-static"]],
                          [posixpath.join(d, "storybook-static") if d else "storybook-static"])
    return None


def _web(paquetes: dict[str, dict], nombres: set[str]) -> Receta | None:
    for d, pkg in paquetes.items():
        scripts = pkg.get("scripts") or {}
        if not (_deps(pkg) & set(MARCOS)) and not any(k in scripts for k in ("dev", "start", "serve")):
            continue
        gestor, lock = _gestor(nombres, d)
        construir = [_correr(gestor, "build")] if "build" in scripts else []
        salidas = [posixpath.join(d, s) if d else s for s in SALIDAS_WEB]
        dev = next((_correr(gestor, s) for s in ("dev", "start", "serve") if s in scripts), None)
        if construir or dev:
            return Receta("web", d, gestor, lock, construir, salidas, dev)
    return None


def _estatico(nombres: set[str]) -> Receta | None:
    for d in SALIDAS_ESTATICO:
        if (posixpath.join(d, "index.html") if d else "index.html") in nombres:
            return Receta("estatico", d, salidas=[d])
    return None
