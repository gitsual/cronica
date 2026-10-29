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

from . import __version__, cambios, construir, detectar, historia, montaje, recorrido, rotulos
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
        print("  Falta el Chromium de Playwright; lo descargo (una sola vez, ~150 MB)…")
        from playwright._impl._driver import compute_driver_executable, get_driver_env
        driver = compute_driver_executable()
        cmd = [*driver, "install", "chromium"] if isinstance(driver, tuple) else [str(driver), "install", "chromium"]
        subprocess.run(cmd, env=get_driver_env(), check=True)
        return p.chromium.launch()


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="cronica", description="Hace el vídeo de cómo evolucionó la interfaz de un proyecto git, hito a hito.")
    ap.add_argument("carpetas", nargs="*", metavar="carpeta",
                    help="la carpeta del proyecto (un repositorio git); si se mudó a otro repositorio, también esa, "
                         "en orden. «carpeta@rama» elige la rama de cada una")
    ap.add_argument("-o", "--salida", help="el mp4 (por defecto, <carpeta>-evolucion.mp4 al lado del proyecto)")
    ap.add_argument("-n", "--max-hitos", type=int, default=30, help="escenas como mucho (30)")
    ap.add_argument("--rama", help="la rama que se recorre (por defecto, la que está activa)")
    ap.add_argument("--modo", choices=("auto", "storybook", "web", "estatico"), default="auto",
                    help="qué se fotografía; auto = Storybook si lo hay, si no la app, si no un index.html")
    ap.add_argument("--ia", nargs="?", const="", metavar="MODELO",
                    help="rótulos escritos por un modelo local (Ollama en :11434 o CRONICA_LLM=http://…/v1)")
    ap.add_argument("--musica", help="un fichero de audio para el fondo (por defecto se genera una)")
    ap.add_argument("--sin-musica", action="store_true")
    ap.add_argument("--segundos", type=float, default=6.0, help="segundos como mucho de app en uso por hito (6)")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--previa", action="store_true", help="no graba el vídeo: deja fotogramas sueltos para revisar")
    ap.add_argument("--reintentar", action="store_true", help="vuelve a construir los hitos que fallaron")
    ap.add_argument("--regrabar", action="store_true",
                    help="vuelve a grabar la app en uso desde los sitios ya construidos (sin build)")
    ap.add_argument("--desde-cero", action="store_true", help="borra la caché de este proyecto antes de empezar")
    ap.add_argument("--trabajo", help="carpeta de trabajo (por defecto, en la caché del usuario)")
    ap.add_argument("--preparar", action="append", metavar="CMD",
                    help="orden que se ejecuta tras instalar y antes de construir («repo=orden» para uno solo)")
    ap.add_argument("--tambien", action="append", metavar="CARPETA",
                    help="un repositorio que no sale en pantalla pero cuenta en las cifras (carpeta o carpeta@rama)")
    ap.add_argument("--paseo", nargs="?", type=float, const=60.0, metavar="SEGUNDOS",
                    help="al final, un paseo por todos los componentes cambiando los temas de la barra (60 s)")
    ap.add_argument("--ocultar", action="append", default=[], metavar="CIFRA",
                    choices=("componentes", "pantallas", "stories", "ficheros", "lineas", "commits", "autores"),
                    help="una cifra que no sale en el vídeo (se puede repetir): p. ej. --ocultar lineas")
    ap.add_argument("--estetica", default=montaje.ESTETICAS[0], metavar="NOMBRE",
                    help="cómo se ve el vídeo: " + " o ".join(montaje.ESTETICAS) +
                         f" (por defecto, {montaje.ESTETICAS[0]}), o la ruta de un .html propio")
    ap.add_argument("--version", action="version", version=f"cronica {__version__}")
    args = ap.parse_args(argv)
    if args.estetica not in montaje.ESTETICAS and not Path(args.estetica).is_file():
        ap.error(f"--estetica: «{args.estetica}» no es {' ni '.join(montaje.ESTETICAS)} ni un .html que exista")
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
        print("\nInterrumpido. Lo hecho queda en caché: al relanzar sigue donde lo dejó.")
        return 130
    finally:
        if _arrastrado():
            input("\nPulsa Intro para cerrar…")


@dataclass
class Capitulo:
    """Un repositorio del vídeo: su historia, dónde trabaja y los hitos que salen."""
    repo: Path
    rama: str
    trabajo: Path
    todos: list[historia.Commit]
    tipo: str
    hechos: list[tuple[historia.Commit, dict]]

    @property
    def nombre(self) -> str:
        return self.repo.name


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
        print("Uso: cronica <carpeta del proyecto> [<carpeta del repositorio al que se mudó> …]\n"
              "     (o arrastra la carpeta sobre cronica.exe)")
        return 2
    pedidas = [_carpeta_y_rama(c) for c in args.carpetas]
    for carpeta, _ in pedidas:
        if not carpeta.is_dir() or not historia.es_repo(carpeta):
            print(f"«{carpeta}» no es una carpeta con un repositorio git.")
            return 2
    ffmpeg = _ffmpeg()
    if not ffmpeg and not args.previa:
        print("Falta ffmpeg. En Windows: winget install Gyan.FFmpeg · en Linux: el paquete ffmpeg.")
        return 2
    repos = [historia.raiz(c) for c, _ in pedidas]
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
    salida = Path(os.path.abspath(args.salida)) if args.salida else repos[0].parent / f"{nombre}-evolucion.mp4"
    t0 = time.time()
    print(f"cronica {__version__}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = _abrir_chromium(p)
        previas: dict[str, Path] = {}   # la última foto enseñada de cada ficha (sigue de un repositorio al siguiente)
        capitulos: list[Capitulo] = []
        for k, (repo, (_, rama)) in enumerate(zip(repos, pedidas)):
            propio = trabajo if len(repos) == 1 else _trabajo_de(repo)
            cap = _capitulo(repo, rama or args.rama, args, navegador, previas, propio, primero_forzado=k > 0)
            if isinstance(cap, int):
                return cap
            capitulos.append(cap)

        if sum(len(c.hechos) for c in capitulos) < 2:
            print("  Hacen falta al menos dos hitos que se puedan fotografiar. Mira los logs de arriba.")
            return 4

        acompanantes = []
        for t in args.tambien or []:
            carpeta, rama = _carpeta_y_rama(t)
            if not historia.es_repo(carpeta):
                print(f"«{carpeta}» no es una carpeta con un repositorio git.")
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
        textos = _textos(trabajo, [c.trabajo for c in capitulos], nombre, escenas, args)
        tipo = capitulos[0].tipo
        video = montaje.preparar(trabajo / "video", nombre, tipo, escenas, textos, tuple(args.ocultar), args.estetica)
        duracion = montaje.duracion_ms(video)

        if args.previa:
            instantes = [1000] + [h["inicio"] + int(h["dur"] * 0.6) for h in video["hitos"]] + [duracion - 2000]
            fotos = montaje.fotogramas(navegador, trabajo / "video", instantes, trabajo / "previa")
            print(f"\n  {len(fotos)} fotogramas en {trabajo / 'previa'}")
            print(f"  rótulos editables: {trabajo / 'rotulos.json'}")
            return 0

        audio = None
        if args.musica:
            audio = Path(args.musica).resolve()
        elif not args.sin_musica:
            from . import musica
            audio = musica.generar(trabajo / "musica.wav", duracion / 1000, [h["inicio"] / 1000 for h in video["hitos"][1:]])
        print(f"  {len(video['hitos'])} escenas, {duracion / 1000:.0f} s de vídeo")
        montaje.renderizar(navegador, trabajo / "video", salida, args.fps, audio, ffmpeg)
        navegador.close()

    minutos = (time.time() - t0) / 60
    print(f"\nHecho en {minutos:.0f} min: {salida}")
    print(f"  Para cambiar los textos, edita {trabajo / 'rotulos.json'} y relanza (todo lo demás sale de la caché).")
    return 0


def _capitulo(repo: Path, rama: str | None, args: argparse.Namespace, navegador, previas: dict[str, Path],
              trabajo: Path, primero_forzado: bool) -> Capitulo | int:
    trabajo.mkdir(parents=True, exist_ok=True)
    rama = rama or historia.rama_actual(repo)
    print(f"\n{repo}")
    todos = historia.commits(repo, rama)
    if not todos:
        print("  La rama no tiene commits.")
        return 2
    print(f"  {len(todos)} commits en {rama} ({todos[0].fecha} → {todos[-1].fecha})")
    final = detectar.detectar(repo, todos[-1].sha, args.modo)
    if not final:
        print("  No encuentro una interfaz que fotografiar: ni Storybook, ni una app web con build o servidor de\n"
              "  desarrollo, ni un index.html. cronica solo hace vídeos de proyectos con interfaz.")
        return 3
    tipo = final.tipo
    cands = historia.candidatos(todos)
    if len(cands) > PRESELECCION:
        paso = len(cands) / PRESELECCION
        cands = [cands[int(i * paso)] for i in range(PRESELECCION - 1)] + [cands[-1]]
    cands = [c for c in cands if (r := detectar.detectar(repo, c.sha, tipo)) and r.tipo == tipo]
    hitos = historia.muestrear(cands, args.max_hitos, todos)
    print(f"  tipo: {tipo}{' en ' + final.dir if final.dir else ''} · {len(hitos)} hitos elegidos de {len(cands)} candidatos")
    clon = construir.preparar_clon(repo, trabajo)
    preparar = _preparar_para(repo, args.preparar or [])

    hechos: list[tuple[historia.Commit, dict]] = []
    max_fotogramas = int(args.segundos * montaje.FPS_CLIP)
    for i, h in enumerate(hitos, 1):
        forzar = primero_forzado and not hechos
        _, titulo = rotulos.pr_y_titulo(h)
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
            print(f"{_resumen(estado)} (regrabado, {time.time() - inicio:.0f} s)")
        elif estado and (estado["ok"] or not args.reintentar):
            print(f"{cab} (caché) {_resumen(estado)}")
        else:
            print(cab, end=" ", flush=True)
            receta = detectar.detectar(repo, h.sha, tipo)
            receta.preparar = preparar
            inicio = time.time()
            estado = construir.procesar(h, receta, clon, trabajo, navegador, previas, max_fotogramas, forzar)
            print(f"{_resumen(estado)} ({time.time() - inicio:.0f} s)")
            for aviso in (estado.get("fotos") or {}).get("avisos", []):
                print(f"        · sin foto: {aviso}")
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
        nombre, sep, _ = e.partition("=")
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
            que = "el Storybook" if cap.tipo == "storybook" else "la interfaz"
            escenas.append({"tipo": "extraccion", "nn": f"{n:02d}", "de": antes.nombre, "a": cap.nombre,
                            "fecha": cap.todos[0].fecha, "chip": f"{antes.nombre} → {cap.nombre}",
                            "titulo": f"Extracción: {que} se muda a {cap.nombre}", "barra": f"git · {cap.nombre}", **ext})
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
    print(f"\n  paseo por {len(fichas)} componentes…", end=" ", flush=True)
    with Servidor(sitio) as s:
        fotogramas = recorrido.paseo(navegador, s.url, [{"id": f["id"], "nombre": f["nombre"]} for f in fichas],
                                     carpeta / "clip", int(args.paseo * montaje.FPS_CLIP))
    print(f"{fotogramas / montaje.FPS_CLIP:.0f} s")
    fotos = {**estado["fotos"], "fotogramas": fotogramas, "nuevas": [], "cambiadas": []}
    ultimo = cap.todos[-1]
    cifras = (historia.cifras_ecosistema(ecosistema, ultimo.fecha) if ecosistema
              else historia.cifras_git(cap.repo, ultimo.sha))
    return {"nn": f"{n:02d}", "sha": h.sha, "fecha": ultimo.fecha, "dir_clip": str(carpeta), "chip": f"{len(fichas)} componentes · {cap.nombre}",
            "titulo": f"Todo junto: {len(fichas)} componentes", "cifras": cifras,
            "fotos": fotos, "dir": str(cap.trabajo), "cap": len(args.carpetas) - 1,
            "barra": f"storybook · {cap.nombre}", "commits": [], "paseo": True}


def _resumen(estado: dict) -> str:
    if not estado["ok"]:
        return f"salta: {estado['motivo']} (log: {estado['log']})"
    f = estado["fotos"]
    if f.get("sin_cambios"):
        return "sin cambios a la vista: no sale"
    partes = []
    if f.get("nuevas"):
        partes.append(f"{len(f['nuevas'])} nuevas")
    if f.get("cambiadas"):
        partes.append(f"{len(f['cambiadas'])} cambian")
    return f"ok, {', '.join(partes) or 'arranque'}; en uso: {', '.join(f.get('focos', []))} ({f.get('fotogramas', 0) / 30:.1f} s)"


def _datos_hitos(repo: Path, todos: list[historia.Commit], hechos: list[tuple[historia.Commit, dict]]) -> list[dict]:
    posicion = {c.sha: i for i, c in enumerate(todos)}
    salida, vistas, anterior = [], set(), -1
    for k, (h, estado) in enumerate(hechos, 1):
        _, titulo = rotulos.pr_y_titulo(h)
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
    return escena["sha"][:7]


def _textos(trabajo: Path, otros: list[Path], nombre: str, escenas: list[dict], args: argparse.Namespace) -> dict:
    """rotulos.json (por sha, para que sobreviva a cambios en los hitos): se crea una vez y luego manda lo editado.

    Lo que falte se toma del rotulos.json de cada repositorio (lo que se escribió en vídeos de uno solo).
    """
    fichero = trabajo / "rotulos.json"
    guardado = json.loads(fichero.read_text(encoding="utf-8")) if fichero.exists() else {}
    por_clave = guardado.get("rotulos", {})
    notas = guardado.get("notas", {})
    titulo, cierre = guardado.get("titulo"), guardado.get("cierre", "")
    for otro in otros:
        f = otro / "rotulos.json"
        if f != fichero and f.exists():
            previo = json.loads(f.read_text(encoding="utf-8"))
            for k, v in previo.get("rotulos", {}).items():
                por_clave.setdefault(k, v)
            for k, v in previo.get("notas", {}).items():
                notas.setdefault(k, v)
            titulo = titulo or previo.get("titulo")
            cierre = cierre or previo.get("cierre", "")
    titulo = titulo or nombre
    hitos = [e for e in escenas if e.get("tipo") != "extraccion" and not e.get("paseo")]
    if args.ia is not None:
        print("  escribiendo los rótulos con el modelo local…", end=" ", flush=True)
        try:
            ia = rotulos.con_ia(nombre, hitos, args.ia or None)
            por_nn = {h["nn"]: _clave(h) for h in hitos}
            por_clave.update({por_nn[nn]: texto for nn, texto in ia["rotulos"].items() if nn in por_nn})
            titulo, cierre = ia["titulo"], ia["cierre"]
            print("ok")
        except Exception as error:
            print(f"no ha podido ({str(error)[:120]}); uso los títulos de los commits")
    for e in escenas:
        por_clave.setdefault(_clave(e), e["titulo"])
    # «notas»: una línea opcional por escena, el porqué del cambio, como subtítulo (mismas claves que «rotulos»).
    fichero.write_text(json.dumps({"titulo": titulo, "cierre": cierre, "rotulos": por_clave, "notas": notas}, indent=1,
                                  ensure_ascii=False), encoding="utf-8")
    return {"titulo": titulo, "cierre": cierre, "rotulos": {e["nn"]: por_clave[_clave(e)] for e in escenas},
            "notas": {e["nn"]: notas[_clave(e)] for e in escenas if notas.get(_clave(e))}}
