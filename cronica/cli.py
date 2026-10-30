"""cronica <carpeta>: el vídeo de cómo evolucionó la interfaz de un proyecto, leyendo su historia git.

También vale arrastrar la carpeta sobre cronica.exe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import __version__, cambios, construir, detectar, historia, i18n, montaje, musica, recorrido, rotulos
from .i18n import _
from .servidor import Servidor

PRESELECCION = 300  # candidatos que se miran como mucho antes de muestrear (detectar cuesta un ls-tree)


def _cache() -> Path:
    if os.environ.get("CRONICA_CACHE"):
        return Path(os.environ["CRONICA_CACHE"])
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "cronica"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "cronica"


def _slug(t: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", t).strip("-") or "proyecto"


def _arrastrado() -> bool:
    """Lanzado arrastrando una carpeta sobre el .exe: la consola se cierra al terminar si no se espera."""
    return getattr(sys, "frozen", False) and sys.platform == "win32" and len(sys.argv) == 2


def _ffmpeg() -> str | None:
    junto = Path(sys.executable).parent / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if getattr(sys, "frozen", False) and junto.exists():
        return str(junto)
    return os.environ.get("CRONICA_FFMPEG") or shutil.which("ffmpeg")


def _abrir_chromium(p):
    try:
        return p.chromium.launch()
    except Exception as error:
        if "Executable doesn't exist" not in str(error) and "playwright install" not in str(error):
            raise
        print(_("  Falta el Chromium de Playwright; lo descargo (una sola vez, ~150 MB)…"))
        from playwright._impl._driver import compute_driver_executable, get_driver_env
        driver = compute_driver_executable()
        cmd = [*driver, "install", "chromium"] if isinstance(driver, tuple) else [str(driver), "install", "chromium"]
        subprocess.run(cmd, env=get_driver_env(), check=True)
        return p.chromium.launch()


# Los nombres en inglés son los de la documentación; los de antes, en español, siguen valiendo.
MUSICAS = {"console": "consola", "newsreel": "noticiario", "ambient": "ambiente"}
LOOKS = {"newspaper": "diario", "classic": "clasica"}
MODOS = {"static": "estatico"}
CIFRAS = {"components": "componentes", "screens": "pantallas", "stories": "stories", "files": "ficheros",
          "lines": "lineas", "commits": "commits", "authors": "autores"}


def _idioma_pedido(argv: list[str]) -> str | None:
    for k, a in enumerate(argv):
        for opcion in ("--lang", "--idioma"):
            if a == opcion and k + 1 < len(argv):
                return argv[k + 1]
            if a.startswith(opcion + "="):
                return a.split("=", 1)[1]
    return None


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    lista = list(sys.argv[1:] if argv is None else argv)
    pedido = _idioma_pedido(lista)
    if pedido in i18n.IDIOMAS:
        i18n.poner(pedido)
    ap = argparse.ArgumentParser(
        prog="cronica", description=_("Hace el vídeo de cómo evolucionó la interfaz de un proyecto git, hito a hito."))
    ap.add_argument("carpetas", nargs="*", metavar="folder",
                    help=_("la carpeta del proyecto (un repositorio git); si se mudó a otro repositorio, también esa, "
                           "en orden. «carpeta@rama» elige la rama de cada una"))
    ap.add_argument("--lang", "--idioma", dest="idioma", choices=i18n.IDIOMAS, default=i18n.idioma,
                    help=_("idioma de la consola y del vídeo: en (por defecto) o es"))
    ap.add_argument("-o", "--output", "--salida", dest="salida",
                    help=_("el mp4 (por defecto, <carpeta>-evolucion.mp4 al lado del proyecto)"))
    ap.add_argument("-n", "--max-milestones", "--max-hitos", dest="max_hitos", type=int, default=30,
                    help=_("escenas como mucho (30)"))
    ap.add_argument("--branch", "--rama", dest="rama", help=_("la rama que se recorre (por defecto, la que está activa)"))
    ap.add_argument("--mode", "--modo", dest="modo", choices=("auto", "storybook", "web", "static", "estatico"),
                    default="auto", help=_("qué se fotografía; auto = Storybook si lo hay, si no la app, si no un index.html"))
    ap.add_argument("--ai", "--ia", dest="ia", nargs="?", const="", metavar="MODEL",
                    help=_("rótulos escritos por un modelo local (Ollama en :11434 o CRONICA_LLM=http://…/v1)"))
    ap.add_argument("--music", "--musica", dest="musica", metavar="STYLE|FILE", default="console",
                    help=_("la música: un estilo generado (console, por defecto; newsreel; ambient) o un fichero de audio propio"))
    ap.add_argument("--no-music", "--sin-musica", dest="sin_musica", action="store_true", help=_("sin música"))
    ap.add_argument("--seconds", "--segundos", dest="segundos", type=float, default=6.0,
                    help=_("segundos como mucho de app en uso por hito (6)"))
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--preview", "--previa", dest="previa", action="store_true",
                    help=_("no graba el vídeo: deja fotogramas sueltos para revisar"))
    ap.add_argument("--retry", "--reintentar", dest="reintentar", action="store_true",
                    help=_("vuelve a construir los hitos que fallaron"))
    ap.add_argument("--rerecord", "--regrabar", dest="regrabar", action="store_true",
                    help=_("vuelve a grabar la app en uso desde los sitios ya construidos (sin build)"))
    ap.add_argument("--from-scratch", "--desde-cero", dest="desde_cero", action="store_true",
                    help=_("borra la caché de este proyecto antes de empezar"))
    ap.add_argument("--workdir", "--trabajo", dest="trabajo", help=_("carpeta de trabajo (por defecto, en la caché del usuario)"))
    ap.add_argument("--prepare", "--preparar", dest="preparar", action="append", metavar="CMD",
                    help=_("orden que se ejecuta tras instalar y antes de construir («repo=orden» para uno solo)"))
    ap.add_argument("--also", "--tambien", dest="tambien", action="append", metavar="FOLDER",
                    help=_("un repositorio que no sale en pantalla pero cuenta en las cifras (carpeta o carpeta@rama)"))
    ap.add_argument("--walk", "--paseo", dest="paseo", nargs="?", type=float, const=60.0, metavar="SECONDS",
                    help=_("al final, un paseo por todos los componentes cambiando los temas de la barra (60 s)"))
    ap.add_argument("--demo", metavar="FILE.json",
                    help=_("al final, una demo guiada de Storybook: paradas, acciones y segundos de cada una"))
    ap.add_argument("--name", "--nombre", dest="nombre", action="append", default=[], metavar="FOLDER=NAME",
                    help=_("el nombre con el que sale un repositorio en el vídeo (p. ej. si se ha renombrado)"))
    ap.add_argument("--hide", "--ocultar", dest="ocultar", action="append", default=[], metavar="FIGURE",
                    help=_("una cifra que no sale en el vídeo (se puede repetir): p. ej. --hide lines"))
    ap.add_argument("--look", "--estetica", dest="estetica", default="newspaper", metavar="NAME",
                    help=_("cómo se ve el vídeo: newspaper (por defecto) o classic, o la ruta de un .html propio"))
    ap.add_argument("--version", action="version", version=f"cronica {__version__}")
    args = ap.parse_args(lista)
    i18n.poner(args.idioma)
    args.modo = MODOS.get(args.modo, args.modo)
    args.musica = MUSICAS.get(args.musica, args.musica)
    args.estetica = LOOKS.get(args.estetica, args.estetica)
    if args.estetica not in montaje.ESTETICAS and not Path(args.estetica).is_file():
        ap.error(_("--look: «{e}» no es newspaper ni classic ni un .html que exista", e=args.estetica))
    if args.musica not in musica.ESTILOS and not Path(args.musica).is_file():
        ap.error(_("--music: «{e}» no es console, newsreel ni ambient ni un fichero que exista", e=args.musica))
    validas = set(CIFRAS) | set(CIFRAS.values())
    for c in args.ocultar:
        if c not in validas:
            ap.error(_("--hide: «{e}» no es una cifra ({c})", e=c, c=", ".join(CIFRAS)))
    args.ocultar = [CIFRAS.get(c, c) for c in args.ocultar]
    return args


def main(argv: list[str] | None = None) -> int:
    if getattr(sys, "frozen", False) and "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        # Empaquetado, Playwright buscaría el navegador dentro del .exe: se usa la caché normal del usuario,
        # que comparte con tramoya y con cualquier Playwright instalado.
        base = os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else os.environ.get("XDG_CACHE_HOME")
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(Path(base or Path.home() / ".cache") / "ms-playwright")
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = _argumentos(argv)
    try:
        return _ejecutar(args)
    except KeyboardInterrupt:
        print(_("\nInterrumpido. Lo hecho queda en caché: al relanzar sigue donde lo dejó."))
        return 130
    finally:
        if _arrastrado():
            input(_("\nPulsa Intro para cerrar…"))


@dataclass
class Capitulo:
    """Un repositorio del vídeo: su historia, dónde trabaja y los hitos que salen."""
    repo: Path
    rama: str
    trabajo: Path
    todos: list[historia.Commit]
    tipo: str
    hechos: list[tuple[historia.Commit, dict]]
    alias: str = ""

    @property
    def nombre(self) -> str:
        return self.alias or self.repo.name


def _trabajo_de(repo: Path) -> Path:
    return _cache() / f"{_slug(repo.name)}-{hashlib.sha1(str(repo).lower().encode()).hexdigest()[:8]}"


def _carpeta_y_rama(texto: str) -> tuple[Path, str | None]:
    """«ruta@rama» o solo «ruta». La rama puede llevar barras (feat/x); la @ que cuenta es la que deja
    a su izquierda una carpeta que existe."""
    if Path(texto).expanduser().is_dir():
        return Path(texto).expanduser().resolve(), None
    for i in [i for i, ch in enumerate(texto) if ch == "@"]:
        carpeta = Path(texto[:i]).expanduser()
        if i and carpeta.is_dir():
            return carpeta.resolve(), texto[i + 1:] or None
    return Path(texto).expanduser().resolve(), None


def _ejecutar(args: argparse.Namespace) -> int:
    if not args.carpetas:
        print(_("Uso: cronica <carpeta del proyecto> [<carpeta del repositorio al que se mudó> …]\n"
                "     (o arrastra la carpeta sobre cronica.exe)"))
        return 2
    pedidas = [_carpeta_y_rama(c) for c in args.carpetas]
    for carpeta, _rama in pedidas:
        if not carpeta.is_dir() or not historia.es_repo(carpeta):
            print(_("«{c}» no es una carpeta con un repositorio git.", c=carpeta))
            return 2
    ffmpeg = _ffmpeg()
    if not ffmpeg and not args.previa:
        print(_("Falta ffmpeg. En Windows: winget install Gyan.FFmpeg · en Linux: el paquete ffmpeg."))
        return 2
    repos = [historia.raiz(c) for c, _rama in pedidas]
    if args.trabajo:
        trabajo = Path(args.trabajo)
    elif len(repos) == 1:
        trabajo = _trabajo_de(repos[0])
    else:
        trabajo = _cache() / ("+".join(_slug(r.name) for r in repos) + "-" +
                              hashlib.sha1("|".join(str(r).lower() for r in repos).encode()).hexdigest()[:8])
    if args.desde_cero and trabajo.exists():
        shutil.rmtree(trabajo, ignore_errors=True)
    trabajo.mkdir(parents=True, exist_ok=True)
    nombre = repos[0].name
    salida = Path(os.path.abspath(args.salida)) if args.salida else repos[0].parent / f"{nombre}-{'evolucion' if i18n.idioma == 'es' else 'evolution'}.mp4"
    t0 = time.time()
    print(f"cronica {__version__}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = _abrir_chromium(p)
        previas: dict[str, Path] = {}   # la última foto enseñada de cada ficha (sigue de un repositorio al siguiente)
        capitulos: list[Capitulo] = []
        for k, (repo, (_carpeta, rama)) in enumerate(zip(repos, pedidas)):
            propio = trabajo if len(repos) == 1 else _trabajo_de(repo)
            cap = _capitulo(repo, rama or args.rama, args, navegador, previas, propio, primero_forzado=k > 0)
            if isinstance(cap, int):
                return cap
            cap.alias = dict(n.partition("=")[::2] for n in args.nombre).get(repo.name, "")
            capitulos.append(cap)

        if sum(len(c.hechos) for c in capitulos) < 2:
            print(_("  Hacen falta al menos dos hitos que se puedan fotografiar. Mira los logs de arriba."))
            return 4

        acompanantes = []
        for t in args.tambien or []:
            carpeta, rama = _carpeta_y_rama(t)
            if not historia.es_repo(carpeta):
                print(_("«{c}» no es una carpeta con un repositorio git.", c=carpeta))
                return 2
            raiz = historia.raiz(carpeta)
            acompanantes.append((raiz, rama or historia.rama_actual(raiz)))
        escenas = _escenas(capitulos, acompanantes)
        if args.paseo:
            ecosistema = [(c.repo, c.rama) for c in capitulos] + acompanantes
            paseo = _paseo(capitulos[-1], trabajo, navegador, args, len(escenas) + 1,
                           ecosistema if len(ecosistema) > 1 else None)
            if paseo:
                escenas.append(paseo)
        if args.demo:
            ecosistema = [(c.repo, c.rama) for c in capitulos] + acompanantes
            escenas += _demo(capitulos[-1], trabajo, navegador, args, len(escenas) + 1,
                             ecosistema if len(ecosistema) > 1 else None)
        textos = _textos(trabajo, [c.trabajo for c in capitulos], nombre, escenas, args)
        tipo = capitulos[0].tipo
        video = montaje.preparar(trabajo / "video", nombre, tipo, escenas, textos, tuple(args.ocultar), args.estetica)
        duracion = montaje.duracion_ms(video)

        if args.previa:
            instantes = [1000] + [h["inicio"] + int(h["dur"] * 0.6) for h in video["hitos"]] + [duracion - 2000]
            fotos = montaje.fotogramas(navegador, trabajo / "video", instantes, trabajo / "previa")
            print(_("\n  {n} fotogramas en {d}", n=len(fotos), d=trabajo / "previa"))
            print(_("  rótulos editables: {f}", f=trabajo / "rotulos.json"))
            return 0

        audio = None
        if args.sin_musica:
            pass
        elif args.musica not in musica.ESTILOS:
            audio = Path(args.musica).resolve()
        else:
            audio = musica.generar(trabajo / "musica.wav", duracion / 1000, [h["inicio"] / 1000 for h in video["hitos"][1:]],
                                   args.musica)
        print(_("  {n} escenas, {s} s de vídeo", n=len(video["hitos"]), s=f"{duracion / 1000:.0f}"))
        montaje.renderizar(navegador, trabajo / "video", salida, args.fps, audio, ffmpeg)
        navegador.close()

    minutos = (time.time() - t0) / 60
    print(_("\nHecho en {m} min: {f}", m=f"{minutos:.0f}", f=salida))
    print(_("  Para cambiar los textos, edita {f} y relanza (todo lo demás sale de la caché).", f=trabajo / "rotulos.json"))
    return 0


def _capitulo(repo: Path, rama: str | None, args: argparse.Namespace, navegador, previas: dict[str, Path],
              trabajo: Path, primero_forzado: bool) -> Capitulo | int:
    trabajo.mkdir(parents=True, exist_ok=True)
    rama = rama or historia.rama_actual(repo)
    print(f"\n{repo}")
    todos = historia.commits(repo, rama)
    if not todos:
        print(_("  La rama no tiene commits."))
        return 2
    print(_("  {n} commits en {r} ({a} → {b})", n=len(todos), r=rama, a=todos[0].fecha, b=todos[-1].fecha))
    final = detectar.detectar(repo, todos[-1].sha, args.modo)
    if not final:
        print(_("  No encuentro una interfaz que fotografiar: ni Storybook, ni una app web con build o servidor de\n"
                "  desarrollo, ni un index.html. cronica solo hace vídeos de proyectos con interfaz."))
        return 3
    tipo = final.tipo
    cands = historia.candidatos(todos)
    if len(cands) > PRESELECCION:
        paso = len(cands) / PRESELECCION
        cands = [cands[int(i * paso)] for i in range(PRESELECCION - 1)] + [cands[-1]]
    cands = [c for c in cands if (r := detectar.detectar(repo, c.sha, tipo)) and r.tipo == tipo]
    hitos = historia.muestrear(cands, args.max_hitos, todos)
    print(_("  tipo: {t}{d} · {n} hitos elegidos de {c} candidatos", t=_(tipo),
            d=_(" en ") + final.dir if final.dir else "", n=len(hitos), c=len(cands)))
    clon = construir.preparar_clon(repo, trabajo)
    preparar = _preparar_para(repo, args.preparar or [])

    hechos: list[tuple[historia.Commit, dict]] = []
    max_fotogramas = int(args.segundos * montaje.FPS_CLIP)
    for i, h in enumerate(hitos, 1):
        forzar = primero_forzado and not hechos
        _pr, titulo = rotulos.pr_y_titulo(h)
        cab = f"  [{i:2d}/{len(hitos)}] {h.fecha} {h.sha[:7]}  {rotulos.limpiar(titulo)[:48]:<48}"
        fichero = trabajo / "hitos" / h.sha[:12] / "estado.json"
        estado = json.loads(fichero.read_text(encoding="utf-8")) if fichero.exists() else None
        if estado and estado.get("esquema") != construir.ESQUEMA:
            estado = None
        sitio = trabajo / "hitos" / h.sha[:12] / "sitio"
        regrabar = args.regrabar or (forzar and estado and estado["ok"] and estado["fotos"].get("sin_cambios"))
        if estado and estado["ok"] and regrabar and sitio.is_dir():
            print(cab, end=" ", flush=True)
            inicio = time.time()
            estado = construir.regrabar(estado, trabajo, navegador, previas, max_fotogramas, forzar)
            print(f"{_resumen(estado)} " + _("(regrabado, {s} s)", s=f"{time.time() - inicio:.0f}"))
        elif estado and (estado["ok"] or not args.reintentar):
            print(f"{cab} {_('(caché)')} {_resumen(estado)}")
        else:
            print(cab, end=" ", flush=True)
            receta = detectar.detectar(repo, h.sha, tipo)
            receta.preparar = preparar
            inicio = time.time()
            estado = construir.procesar(h, receta, clon, trabajo, navegador, previas, max_fotogramas, forzar)
            print(f"{_resumen(estado)} ({time.time() - inicio:.0f} s)")
            for aviso in (estado.get("fotos") or {}).get("avisos", []):
                print(_("        · sin foto: {a}", a=aviso))
        if estado["ok"] and not estado["fotos"].get("sin_cambios"):
            hechos.append((h, estado))
            carpeta = trabajo / "hitos" / h.sha[:12]
            previas.update({f["key"]: carpeta / f["light"]["file"] for f in estado["fotos"]["fichas"]})
            if (carpeta / "marco.png").exists():
                previas[cambios.MARCO] = carpeta / "marco.png"
    return Capitulo(repo, rama, trabajo, todos, tipo, hechos)


def _preparar_para(repo: Path, entradas: list[str]) -> list[str] | None:
    """--preparar «cmd» vale para todos los repositorios; «nombre-del-repo=cmd», solo para ese."""
    for e in entradas:
        nombre, sep, cmd = e.partition("=")
        if sep and nombre == repo.name:
            return shlex.split(cmd)
    for e in entradas:
        nombre, sep, _cmd = e.partition("=")
        if not sep or " " in nombre:
            return shlex.split(e)
    return None


def _escenas(capitulos: list[Capitulo], acompanantes: list[tuple[Path, str]] | None = None) -> list[dict]:
    """Los hitos de cada repositorio, numerados seguidos, con una escena de extracción entre uno y otro.

    Con varios repositorios (o con --tambien), las cifras de cada escena son las de todos juntos ese día: al
    extraer una parte, el proyecto no encoge.
    """
    escenas, n = [], 0
    ecosistema = [(c.repo, c.rama) for c in capitulos] + list(acompanantes or [])
    for k, cap in enumerate(capitulos):
        if k:
            antes = capitulos[k - 1]
            ext = historia.extraccion(antes.repo, antes.todos[-1].sha, cap.repo, cap.todos[0].sha)
            n += 1
            que = _("el Storybook") if cap.tipo == "storybook" else _("la interfaz")
            escenas.append({"tipo": "extraccion", "nn": f"{n:02d}", "de": antes.nombre, "a": cap.nombre,
                            "fecha": cap.todos[0].fecha, "chip": f"{antes.nombre} → {cap.nombre}",
                            "titulo": _("Extracción: {que} se muda a {a}", que=que, a=cap.nombre), "barra": f"git · {cap.nombre}", **ext})
        for h in _datos_hitos(cap.repo, cap.todos, cap.hechos):
            n += 1
            if len(ecosistema) > 1:
                h["cifras"] = historia.cifras_ecosistema(ecosistema, h["fecha"])
            escenas.append({**h, "nn": f"{n:02d}", "dir": str(cap.trabajo), "cap": k,
                            "barra": f"{'storybook' if cap.tipo == 'storybook' else 'localhost'} · {cap.nombre}"})
    return escenas


def _paseo(cap: Capitulo, trabajo: Path, navegador, args: argparse.Namespace, n: int,
           ecosistema: list[tuple[Path, str]] | None = None) -> dict | None:
    """Una última escena por todo lo que hay al final, cambiando los temas desde la barra de Storybook.
    Lleva la fecha y las cifras del último commit (de todos los repositorios juntos, si hay varios)."""
    if cap.tipo != "storybook" or not cap.hechos:
        return None
    h, estado = cap.hechos[-1]
    sitio = cap.trabajo / "hitos" / h.sha[:12] / "sitio"
    if not sitio.is_dir():
        return None
    carpeta = trabajo / "paseo"
    fichas = [f for f in estado["fotos"]["fichas"] if not any(d in f["key"].lower() for d in montaje.DOCS)]
    print(_("\n  paseo por {n} componentes…", n=len(fichas)), end=" ", flush=True)
    with Servidor(sitio) as s:
        fotogramas = recorrido.paseo(navegador, s.url, [{"id": f["id"], "nombre": f["nombre"]} for f in fichas],
                                     carpeta / "clip", int(args.paseo * montaje.FPS_CLIP))
    print(f"{fotogramas / montaje.FPS_CLIP:.0f} s")
    fotos = {**estado["fotos"], "fotogramas": fotogramas, "nuevas": [], "cambiadas": []}
    ultimo = cap.todos[-1]
    cifras = (historia.cifras_ecosistema(ecosistema, ultimo.fecha) if ecosistema
              else historia.cifras_git(cap.repo, ultimo.sha))
    return {"nn": f"{n:02d}", "sha": h.sha, "fecha": ultimo.fecha, "dir_clip": str(carpeta), "chip": _("{n} componentes · {p}", n=len(fichas), p=cap.nombre),
            "titulo": _("Todo junto: {n} componentes", n=len(fichas)), "cifras": cifras,
            "fotos": fotos, "dir": str(cap.trabajo), "cap": len(args.carpetas) - 1,
            "barra": f"storybook · {cap.nombre}", "commits": [], "paseo": True}


def _demo(cap: Capitulo, trabajo: Path, navegador, args: argparse.Namespace, n: int,
          ecosistema: list[tuple[Path, str]] | None = None) -> list[dict]:
    """--demo: una escena por parada, grabada sobre el último build (o sobre el «sitio» del fichero, p. ej. un
    build con código que aún no está en la rama). Cada parada lleva su rótulo; se editan en rotulos.json
    («demo:1», «demo:2»…)."""
    guion = _guion(json.loads(Path(args.demo).read_text(encoding="utf-8")))
    if cap.tipo != "storybook" or not cap.hechos:
        return []
    h, estado = cap.hechos[-1]
    sitio = Path(guion["sitio"]).expanduser() if guion.get("sitio") else cap.trabajo / "hitos" / h.sha[:12] / "sitio"
    if not sitio.is_dir():
        print(_("  --demo: no encuentro el build «{s}»", s=sitio))
        return []
    pasos = guion["pasos"]
    carpetas = [trabajo / "demo" / f"{k:02d}" for k in range(1, len(pasos) + 1)]
    print(_("\n  demo de {n} paradas…", n=len(pasos)), end=" ", flush=True)
    with Servidor(sitio) as s:
        fotogramas = recorrido.demo(navegador, s.url, pasos, [c / "clip" for c in carpetas])
    print(f"{sum(fotogramas) / montaje.FPS_CLIP:.0f} s")
    fecha = guion.get("fecha") or cap.todos[-1].fecha
    cifras = (historia.cifras_ecosistema(ecosistema, fecha) if ecosistema
              else historia.cifras_git(cap.repo, cap.todos[-1].sha))
    escenas = []
    for k, (paso, carpeta, total) in enumerate(zip(pasos, carpetas, fotogramas), 1):
        escenas.append({"nn": f"{n + k - 1:02d}", "sha": h.sha, "fecha": paso.get("fecha", fecha), "dir_clip": str(carpeta),
                        "chip": paso.get("chip", cap.nombre), "titulo": paso.get("rotulo", paso["story"]),
                        "cifras": cifras, "fotos": {**estado["fotos"], "fotogramas": total, "nuevas": [], "cambiadas": []},
                        "dir": str(cap.trabajo), "cap": len(args.carpetas) - 1,
                        "barra": f"storybook · {cap.nombre}", "commits": [], "demo": k})
    return escenas


MESA = {"title": "titulo", "closing": "cierre", "footer": "pie", "headlines": "rotulos", "notes": "notas",
        "acts": "actos"}
ACTO = {"from": "desde", "title": "titulo", "line": "frase"}
GUION = {"site": "sitio", "steps": "pasos", "date": "fecha"}
PASO = {"seconds": "segundos", "headline": "rotulo", "actions": "acciones", "date": "fecha"}
ACCION = {"click": "clic", "use": "usar", "read": "leer", "scroll": "rueda", "drift": "deriva", "in": "en",
          "wait": "espera", "frames": "fotos"}


def _traducir(d: dict, tabla: dict) -> dict:
    return {tabla.get(k, k): v for k, v in d.items()}


def _mesa(d: dict, al_ingles: bool = False) -> dict:
    """rotulos.json en inglés (title, headlines, acts…) o en español (titulo, rotulos, actos…): por dentro, en español."""
    if al_ingles:
        inv, acto = {v: k for k, v in MESA.items()}, {v: k for k, v in ACTO.items()}
        return {inv.get(k, k): ([_traducir(a, acto) for a in v] if k == "actos" else v) for k, v in d.items()}
    d = _traducir(d, MESA)
    d["actos"] = [_traducir(a, ACTO) for a in d.get("actos", [])]
    return d


def _guion(d: dict) -> dict:
    """demo.json con claves en inglés o en español; «"in": "toolbar"» es «"en": "barra"»."""
    d = _traducir(d, GUION)
    pasos = []
    for paso in d.get("pasos", []):
        paso = _traducir(paso, PASO)
        acciones = []
        for a in paso.get("acciones", []):
            a = _traducir(a, ACCION)
            if a.get("en") == "toolbar":
                a["en"] = "barra"
            acciones.append(a)
        pasos.append({**paso, "acciones": acciones})
    return {**d, "pasos": pasos}


def _resumen(estado: dict) -> str:
    if not estado["ok"]:
        return _("salta: {m} (log: {l})", m=_(estado["motivo"]), l=estado["log"])
    f = estado["fotos"]
    if f.get("sin_cambios"):
        return _("sin cambios a la vista: no sale")
    partes = []
    if f.get("nuevas"):
        partes.append(_("{n} nuevas", n=len(f["nuevas"])))
    if f.get("cambiadas"):
        partes.append(_("{n} cambian", n=len(f["cambiadas"])))
    return _("ok, {p}; en uso: {f} ({s} s)", p=", ".join(partes) or _("arranque"),
             f=", ".join(_(x) for x in f.get("focos", [])), s=f"{f.get('fotogramas', 0) / 30:.1f}")


def _datos_hitos(repo: Path, todos: list[historia.Commit], hechos: list[tuple[historia.Commit, dict]]) -> list[dict]:
    posicion = {c.sha: i for i, c in enumerate(todos)}
    salida, vistas, anterior = [], set(), -1
    for k, (h, estado) in enumerate(hechos, 1):
        _pr, titulo = rotulos.pr_y_titulo(h)
        claves = [f["key"] for f in estado["fotos"]["fichas"]]
        entre = todos[anterior + 1: posicion[h.sha] + 1]
        anterior = posicion[h.sha]
        salida.append({
            "nn": f"{k:02d}", "sha": h.sha, "fecha": h.fecha, "chip": rotulos.chip(h), "titulo": rotulos.limpiar(titulo),
            "cifras": historia.cifras_git(repo, h.sha), "fotos": estado["fotos"],
            "nuevas": [f["nombre"] for f in estado["fotos"]["fichas"] if f["key"] in estado["fotos"].get("nuevas", [])],
            "commits": [c.asunto for c in entre if not c.merge] or [c.asunto for c in entre],
        })
        vistas |= set(claves)
    return salida


def _clave(escena: dict) -> str:
    """La clave de una escena en rotulos.json: el sha del hito, o qué escena especial es."""
    if escena.get("tipo") == "extraccion":
        return f"extraccion:{escena['de']}>{escena['a']}"
    if escena.get("paseo"):
        return "paseo"
    if escena.get("demo"):
        return f"demo:{escena['demo']}"
    return escena["sha"][:7]


def _textos(trabajo: Path, otros: list[Path], nombre: str, escenas: list[dict], args: argparse.Namespace) -> dict:
    """rotulos.json (por sha, para que sobreviva a cambios en los hitos): se crea una vez y luego manda lo editado.

    Lo que falte se toma del rotulos.json de cada repositorio (lo que se escribió en vídeos de uno solo).
    """
    fichero = trabajo / "rotulos.json"
    guardado = _mesa(json.loads(fichero.read_text(encoding="utf-8"))) if fichero.exists() else {}
    por_clave = guardado.get("rotulos", {})
    notas = guardado.get("notas", {})
    titulo, cierre = guardado.get("titulo"), guardado.get("cierre", "")
    for otro in otros:
        f = otro / "rotulos.json"
        if f != fichero and f.exists():
            previo = _mesa(json.loads(f.read_text(encoding="utf-8")))
            for k, v in previo.get("rotulos", {}).items():
                por_clave.setdefault(k, v)
            for k, v in previo.get("notas", {}).items():
                notas.setdefault(k, v)
            titulo = titulo or previo.get("titulo")
            cierre = cierre or previo.get("cierre", "")
    titulo = titulo or nombre
    hitos = [e for e in escenas if e.get("tipo") != "extraccion" and not e.get("paseo")]
    if args.ia is not None:
        print(_("  escribiendo los rótulos con el modelo local…"), end=" ", flush=True)
        try:
            ia = rotulos.con_ia(nombre, hitos, args.ia or None, i18n.idioma)
            por_nn = {h["nn"]: _clave(h) for h in hitos}
            por_clave.update({por_nn[nn]: texto for nn, texto in ia["rotulos"].items() if nn in por_nn})
            titulo, cierre = ia["titulo"], ia["cierre"]
            print("ok")
        except Exception as error:
            print(_("no ha podido ({e}); uso los títulos de los commits", e=str(error)[:120]))
    for e in escenas:
        por_clave.setdefault(_clave(e), e["titulo"])
    # «notas»: una línea opcional por escena, el porqué del cambio, como subtítulo (mismas claves que «rotulos»).
    # «actos»: [{desde: clave, titulo, frase}]: un cartel que abre cada parte del vídeo, antes de esa escena.
    # «pie»: una línea pequeña bajo el cierre.
    actos, pie = guardado.get("actos", []), guardado.get("pie", "")
    mesa = {"titulo": titulo, "cierre": cierre, "pie": pie, "rotulos": por_clave, "notas": notas, "actos": actos}
    fichero.write_text(json.dumps(mesa if i18n.idioma == "es" else _mesa(mesa, al_ingles=True), indent=1,
                                  ensure_ascii=False), encoding="utf-8")
    por_nn = {_clave(e): e["nn"] for e in escenas}
    return {"titulo": titulo, "cierre": cierre, "pie": pie, "rotulos": {e["nn"]: por_clave[_clave(e)] for e in escenas},
            "notas": {e["nn"]: notas[_clave(e)] for e in escenas if notas.get(_clave(e))},
            "actos": {por_nn[a["desde"]]: {"titulo": a.get("titulo", ""), "frase": a.get("frase", "")}
                      for a in actos if a.get("desde") in por_nn}}
