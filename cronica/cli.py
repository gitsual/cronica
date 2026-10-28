"""cronica <carpeta>: el vídeo de cómo evolucionó la interfaz de un proyecto, leyendo su historia git.

También vale arrastrar la carpeta sobre cronica.exe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import __version__, cambios, construir, detectar, historia, montaje, rotulos

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
    ap.add_argument("carpeta", nargs="?", help="la carpeta del proyecto (un repositorio git)")
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
    ap.add_argument("--version", action="version", version=f"cronica {__version__}")
    return ap.parse_args(argv)


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


def _ejecutar(args: argparse.Namespace) -> int:
    if not args.carpeta:
        print("Uso: cronica <carpeta del proyecto>   (o arrastra la carpeta sobre cronica.exe)")
        return 2
    carpeta = Path(args.carpeta).expanduser().resolve()
    if not carpeta.is_dir() or not historia.es_repo(carpeta):
        print(f"«{carpeta}» no es una carpeta con un repositorio git.")
        return 2
    ffmpeg = _ffmpeg()
    if not ffmpeg and not args.previa:
        print("Falta ffmpeg. En Windows: winget install Gyan.FFmpeg · en Linux: el paquete ffmpeg.")
        return 2

    repo = historia.raiz(carpeta)
    nombre = repo.name
    trabajo = Path(args.trabajo) if args.trabajo else _cache() / f"{_slug(nombre)}-{hashlib.sha1(str(repo).lower().encode()).hexdigest()[:8]}"
    if args.desde_cero and trabajo.exists():
        shutil.rmtree(trabajo, ignore_errors=True)
    trabajo.mkdir(parents=True, exist_ok=True)
    salida = Path(os.path.abspath(args.salida)) if args.salida else repo.parent / f"{nombre}-evolucion.mp4"
    t0 = time.time()

    print(f"cronica {__version__} · {repo}")
    rama = args.rama or historia.rama_actual(repo)
    todos = historia.commits(repo, rama)
    if not todos:
        print("La rama no tiene commits.")
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
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = _abrir_chromium(p)
        previas: dict[str, Path] = {}   # la última foto enseñada de cada ficha
        hechos: list[tuple[historia.Commit, dict]] = []
        max_fotogramas = int(args.segundos * montaje.FPS_CLIP)
        for i, h in enumerate(hitos, 1):
            _, titulo = rotulos.pr_y_titulo(h)
            cab = f"  [{i:2d}/{len(hitos)}] {h.fecha} {h.sha[:7]}  {rotulos.limpiar(titulo)[:48]:<48}"
            fichero = trabajo / "hitos" / h.sha[:12] / "estado.json"
            estado = json.loads(fichero.read_text(encoding="utf-8")) if fichero.exists() else None
            if estado and estado.get("esquema") != construir.ESQUEMA:
                estado = None
            sitio = trabajo / "hitos" / h.sha[:12] / "sitio"
            if estado and estado["ok"] and args.regrabar and sitio.is_dir():
                print(cab, end=" ", flush=True)
                inicio = time.time()
                estado = construir.regrabar(estado, trabajo, navegador, previas, max_fotogramas)
                print(f"{_resumen(estado)} (regrabado, {time.time() - inicio:.0f} s)")
            elif estado and (estado["ok"] or not args.reintentar):
                print(f"{cab} (caché) {_resumen(estado)}")
            else:
                print(cab, end=" ", flush=True)
                receta = detectar.detectar(repo, h.sha, tipo)
                inicio = time.time()
                estado = construir.procesar(h, receta, clon, trabajo, navegador, previas, max_fotogramas)
                print(f"{_resumen(estado)} ({time.time() - inicio:.0f} s)")
                for aviso in (estado.get("fotos") or {}).get("avisos", []):
                    print(f"        · sin foto: {aviso}")
            if estado["ok"] and not estado["fotos"].get("sin_cambios"):
                hechos.append((h, estado))
                carpeta = trabajo / "hitos" / h.sha[:12]
                previas.update({f["key"]: carpeta / f["light"]["file"] for f in estado["fotos"]["fichas"]})
                if (carpeta / "marco.png").exists():
                    previas[cambios.MARCO] = carpeta / "marco.png"

        if len(hechos) < 2:
            print("  Hacen falta al menos dos hitos que se puedan fotografiar. Mira los logs de arriba.")
            return 4

        datos_hitos = _datos_hitos(repo, todos, hechos)
        textos = _textos(trabajo, nombre, datos_hitos, args)
        video = montaje.preparar(trabajo / "video", trabajo, nombre, tipo, datos_hitos, textos)
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
        print(f"  {len(datos_hitos)} escenas, {duracion / 1000:.0f} s de vídeo")
        montaje.renderizar(navegador, trabajo / "video", salida, args.fps, audio, ffmpeg)
        navegador.close()

    minutos = (time.time() - t0) / 60
    print(f"\nHecho en {minutos:.0f} min: {salida}")
    print(f"  Para cambiar los textos, edita {trabajo / 'rotulos.json'} y relanza (todo lo demás sale de la caché).")
    return 0


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


def _textos(trabajo: Path, nombre: str, hitos: list[dict], args: argparse.Namespace) -> dict:
    """rotulos.json (por sha, para que sobreviva a cambios en los hitos): se crea una vez y luego manda lo editado."""
    fichero = trabajo / "rotulos.json"
    guardado = json.loads(fichero.read_text(encoding="utf-8")) if fichero.exists() else {}
    por_sha = guardado.get("rotulos", {})
    titulo, cierre = guardado.get("titulo", nombre), guardado.get("cierre", "")
    if args.ia is not None:
        print("  escribiendo los rótulos con el modelo local…", end=" ", flush=True)
        try:
            ia = rotulos.con_ia(nombre, hitos, args.ia or None)
            por_nn = {h["nn"]: h["sha"][:7] for h in hitos}
            por_sha.update({por_nn[nn]: texto for nn, texto in ia["rotulos"].items() if nn in por_nn})
            titulo, cierre = ia["titulo"], ia["cierre"]
            print("ok")
        except Exception as error:
            print(f"no ha podido ({str(error)[:120]}); uso los títulos de los commits")
    for h in hitos:
        por_sha.setdefault(h["sha"][:7], h["titulo"])
    fichero.write_text(json.dumps({"titulo": titulo, "cierre": cierre, "rotulos": por_sha}, indent=1,
                                  ensure_ascii=False), encoding="utf-8")
    return {"titulo": titulo, "cierre": cierre, "rotulos": {h["nn"]: por_sha[h["sha"][:7]] for h in hitos}}
