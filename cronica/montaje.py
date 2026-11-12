"""Junta los hitos en datos.json, graba el reproductor fotograma a fotograma y le pone la música."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.parse
from importlib import resources
from pathlib import Path

from . import i18n
from .i18n import _

INTRO_MS, OUTRO_MS, EXTRACCION_MS, ACTO_MS = 2200, 5200, 7500, 3400
# Cómo se ve el vídeo: la primera es la de por defecto (reproductor/esteticas/<nombre>.html).
ESTETICAS = ("diario", "clasica")
FPS_CLIP = 30  # los clips se graban a pasos; cada fotograma vale 1/30 s
# El lienzo del vídeo: horizontal (16:9, la pantalla) o vertical (9:16, el móvil). Solo el diario sabe ser vertical.
FORMATOS = {"horizontal": (1920, 1080), "vertical": (1080, 1920)}
VERTICALES = ("diario",)
# Al encajar el vídeo en una duración: cuánto puede acelerarse un clip y lo menos que dura una escena.
VEL_MAX, ESCENA_MIN_MS = 2.0, 2400

CIFRAS = {
    "storybook": [("componentes", "Componentes"), ("stories", "Stories"), ("ficheros", "Ficheros"),
                  ("lineas", "Líneas"), ("commits", "Commits")],
    "web": [("pantallas", "Pantallas"), ("ficheros", "Ficheros"), ("lineas", "Líneas"), ("commits", "Commits"),
            ("autores", "Autores")],
}
CIFRAS["estatico"] = CIFRAS["web"]
DOCS = ("foundation", "intro", "welcome")


def _rel(destino: Path, desde: Path) -> str:
    return os.path.relpath(destino, desde).replace(os.sep, "/")


def preparar(video: Path, proyecto: str, tipo: str, escenas: list[dict], textos: dict,
             ocultar: tuple[str, ...] = (), estetica: str = ESTETICAS[0], formato: str = "horizontal",
             duracion_s: float = 0) -> dict:
    """escenas: hitos ya grabados ({nn, sha, fecha, chip, titulo, cifras, fotos, dir, cap, barra}) y escenas
    especiales ({tipo: "extraccion", ...}), en orden. `ocultar`: cifras que no salen (p. ej. «lineas»).
    `estetica`: una de ESTETICAS o la ruta de un .html propio que lea datos.json y exponga seek() como ellas.
    `formato`: una clave de FORMATOS. `duracion_s`: si es más de 0, el vídeo dura como mucho eso (ver encajar()).

    El reproductor vive en video/ y lee fotos y clips de la carpeta de trabajo de cada repositorio (no se copia
    nada): las rutas son relativas a video/ y el servidor sirve el antepasado común.
    """
    video.mkdir(parents=True, exist_ok=True)
    salida, t, cifras_previas = [], INTRO_MS, {}
    for h in escenas:
        if h.get("tipo") == "extraccion":
            dur = h.get("dur", EXTRACCION_MS)
            salida.append({**h, "rotulo": textos["rotulos"].get(h["nn"], h["titulo"]),
                           "nota": textos.get("notas", {}).get(h["nn"], ""), "cifras": cifras_previas,
                           "inicio": t, "dur": dur, "fichas": [], "nuevas": [], "cambiadas": [], "fotogramas": 0})
            t += dur
            continue
        rel = _rel(Path(h["dir"]) / "hitos" / h["sha"][:12], video) if h.get("sha") else _rel(Path(h["dir"]), video)
        f = h["fotos"]
        nombres = {x["key"]: _(x["nombre"]) for x in f["fichas"]} | {"__marco__": "Storybook" if tipo == "storybook" else _("Marco")}
        fichas = []
        for ficha in f["fichas"]:
            item = {"key": f"{h['cap']}:{ficha['key']}", "nombre": _(ficha["nombre"]), "w": ficha["light"]["w"],
                    "h": ficha["light"]["h"], "cubre": tipo != "storybook"}
            for tema in ("light", "dark"):
                if ficha.get(tema):
                    item[tema] = f"{rel}/{ficha[tema]['file']}"
            fichas.append(item)
        visibles = [x for x in fichas if not any(p in x["key"].lower() for p in DOCS)]
        cifras = {**h["cifras"], "componentes": len(visibles), "pantallas": len(fichas), "stories": f.get("stories", 0)}
        cifras_previas = cifras
        dur = round(f["fotogramas"] * 1000 / FPS_CLIP)
        salida.append({"nn": h["nn"], "sha": (h.get("sha") or "")[:7], "fecha": h["fecha"], "chip": h["chip"],
                       "rotulo": textos["rotulos"].get(h["nn"], h["titulo"]), "nota": textos.get("notas", {}).get(h["nn"], ""),
                       "cifras": cifras, "cap": h["cap"], "demo": h.get("demo", 0),
                       "barra": h["barra"],
                       "clip": f"{_rel(Path(h['dir_clip']), video)}/clip/" if h.get("dir_clip") else f"{rel}/clip/", "fotogramas": f["fotogramas"], "inicio": t, "dur": dur,
                       "nuevas": [nombres[k] for k in f.get("nuevas", []) if k in nombres],
                       "cambiadas": [nombres[k] for k in f.get("cambiadas", []) if k in nombres],
                       "fichas": fichas})
        t += dur
    actos = textos.get("actos", {})
    ajuste = encajar(salida, actos, duracion_s * 1000) if duracion_s > 0 else None
    # Un acto abre con un cartel antes de su primera escena: la escena empieza ACTO_MS más tarde («pre»).
    t = INTRO_MS
    for e in salida:
        if e["nn"] in actos:
            e["acto"], e["pre"], e["dur"] = actos[e["nn"]], ACTO_MS, e["dur"] + ACTO_MS
        e["inicio"] = t
        t += e["dur"]
    ultimo = next((e["cifras"] for e in reversed(salida) if e["cifras"]), {})
    definicion = [[k, _(l)] for k, l in CIFRAS[tipo] if ultimo.get(k) and k not in ocultar]
    for e in salida:
        e["fecha_larga"], e["fecha_corta"] = i18n.fecha_larga(e["fecha"]), i18n.fecha_corta(e["fecha"])
    fechas = {}
    if salida:
        a, z = salida[0]["fecha"], salida[-1]["fecha"]
        fechas = {"rango": i18n.rango(a, z), "lapso": i18n.lapso(a, z), "final": i18n.fecha_sin_dia(z)}
    datos = {
        **i18n.reproductor(), **fechas,
        "proyecto": proyecto, "titulo": textos.get("titulo") or proyecto, "cierre": textos.get("cierre") or "",
        "pie": textos.get("pie") or "",
        "barra": f"{'storybook' if tipo == 'storybook' else 'localhost'} · {proyecto}", "cifras": definicion,
        "ocultar": list(ocultar), "fps_clip": FPS_CLIP, "intro": INTRO_MS, "outro": OUTRO_MS, "hitos": salida,
        "formato": formato, "ancho": FORMATOS[formato][0], "alto": FORMATOS[formato][1],
    }
    if ajuste:
        datos["ajuste"] = ajuste
    (video / "datos.json").write_text(json.dumps(datos, indent=1, ensure_ascii=False), encoding="utf-8")
    reproductor = resources.files("cronica").joinpath("reproductor")
    html = (reproductor.joinpath("esteticas", f"{estetica}.html") if estetica in ESTETICAS else Path(estetica))
    (video / "reproductor.html").write_text(html.read_text(encoding="utf-8"), encoding="utf-8")
    # Las letras van con el reproductor: el vídeo se graba igual sin red.
    (video / "fonts").mkdir(exist_ok=True)
    for f in reproductor.joinpath("fonts").iterdir():
        (video / "fonts" / f.name).write_bytes(f.read_bytes())
    return datos


def encajar(salida: list[dict], actos: dict, objetivo_ms: float) -> dict | None:
    """Deja el vídeo en `objetivo_ms` como mucho. Lo fijo (entrada, cierre, carteles de acto y extracciones) no se
    toca; los clips se reparten lo que queda. Primero se aceleran (hasta VEL_MAX: cada escena guarda su «vel»)
    y, si aun así no caben, se cortan por el final. Si a cada escena le tocaría menos de ESCENA_MIN_MS, se quitan
    hitos del medio (nunca el primero ni el último; un cartel de acto pasa al siguiente hito que se queda).

    Cambia `salida` (y `actos`) en su sitio. Devuelve lo que hizo, o None si el vídeo ya cabía."""
    def clips():
        return [e for e in salida if e.get("fotogramas")]

    def fijo():
        return (INTRO_MS + OUTRO_MS + ACTO_MS * sum(e["nn"] in actos for e in salida)
                + sum(e["dur"] for e in salida if not e.get("fotogramas")))

    natural = fijo() + sum(e["dur"] for e in clips())
    if natural <= objetivo_ms:
        return None
    quitados = 0
    # Los hitos que se pueden quitar: los de la historia (la demo y el paseo del final se quedan enteros).
    while True:
        hitos = [e for e in clips() if not e.get("demo") and not e.get("paseo")]
        if len(hitos) <= 2 or (objetivo_ms - fijo()) / len(clips()) >= ESCENA_MIN_MS:
            break
        # Fuera el hito del medio con menos novedades: el que menos cuenta.
        medio = hitos[1:-1]
        fuera = min(medio, key=lambda e: (len(e["nuevas"]) + len(e["cambiadas"]), -abs(hitos.index(e) - len(hitos) / 2)))
        i = salida.index(fuera)
        if fuera["nn"] in actos:
            sigue = next((e for e in salida[i + 1:] if e.get("fotogramas")), None)
            acto = actos.pop(fuera["nn"])
            if sigue and sigue["nn"] not in actos:
                actos[sigue["nn"]] = acto
        # Lo que el hito quitado traía de nuevo lo cuenta el siguiente (y sus fotos, si ese no las trae).
        sig = next((e for e in salida[i + 1:] if e.get("fotogramas")), None)
        if sig:
            sig["nuevas"] = list(dict.fromkeys(fuera["nuevas"] + sig["nuevas"]))
            tiene = {f["key"] for f in sig["fichas"]}
            sig["fichas"] = [f for f in fuera["fichas"] if f["key"] not in tiene] + sig["fichas"]
        del salida[i]
        quitados += 1
    disponible = max(objetivo_ms - fijo(), ESCENA_MIN_MS * len(clips()))
    total = sum(e["dur"] for e in clips())
    factor = total / disponible
    for e in clips():
        if factor > 1:
            e["dur"] = int(e["dur"] / factor)
            e["vel"] = round(min(factor, VEL_MAX), 3)
    return {"objetivo_s": round(objetivo_ms / 1000, 1), "natural_s": round(natural / 1000, 1), "quitados": quitados,
            "vel": round(min(factor, VEL_MAX), 2) if factor > 1 else 1.0, "corta": factor > VEL_MAX}


def duracion_ms(datos: dict) -> int:
    return datos["intro"] + sum(h["dur"] for h in datos["hitos"]) + datos["outro"]


ORIGEN = "http://cronica.local"


class _Disco:
    """Sirve al reproductor los ficheros de `raiz` directamente desde el disco, sin socket: un servidor HTTP
    local se atasca con decenas de fotos a la vez cuando un antivirus inspecciona el tráfico (Avast en Windows)."""

    def __init__(self, page, raiz: Path):
        self.url = ORIGEN
        raiz = raiz.resolve()

        def servir(route):
            ruta = urllib.parse.unquote(urllib.parse.urlsplit(route.request.url).path).lstrip("/")
            fichero = (raiz / ruta).resolve()
            if fichero.is_file() and fichero.is_relative_to(raiz):
                route.fulfill(path=str(fichero))
            else:
                route.fulfill(status=404, body="")

        page.route(f"{ORIGEN}/**", servir)

    def __exit__(self, *exc) -> None:
        pass


def _abrir(navegador, video: Path):
    datos = json.loads((video / "datos.json").read_text(encoding="utf-8"))
    rutas = [video] + [(video / h["clip"]).resolve() for h in datos["hitos"] if h.get("clip")]
    raiz = Path(os.path.commonpath([str(r.resolve()) for r in rutas]))
    ancho, alto = datos.get("ancho", 1920), datos.get("alto", 1080)
    page = navegador.new_page(viewport={"width": ancho, "height": alto})
    srv = _Disco(page, raiz)
    page.goto(f"{srv.url}/{_rel(video.resolve(), raiz)}/reproductor.html")
    page.wait_for_function("window.ready === true", timeout=180_000)
    return srv, page


def fotogramas(navegador, video: Path, instantes_ms: list[int], destino: Path) -> list[Path]:
    """Fotos sueltas del vídeo, para revisarlo sin renderizarlo entero."""
    destino.mkdir(parents=True, exist_ok=True)
    srv, page = _abrir(navegador, video)
    rutas = []
    try:
        for ms in instantes_ms:
            page.evaluate(f"seek({ms})")  # devuelve una promesa: espera a que el fotograma del clip esté pintado
            ruta = destino / f"{ms:07d}.png"
            page.screenshot(path=str(ruta))
            rutas.append(ruta)
    finally:
        page.close()
        srv.__exit__()
    return rutas


def renderizar(navegador, video: Path, salida: Path, fps: int, audio: Path | None, ffmpeg: str = "ffmpeg") -> Path:
    srv, page = _abrir(navegador, video)
    mudo = video / "mudo.mp4"
    try:
        total = int(page.evaluate("window.duration") / 1000 * fps)
        ff = subprocess.Popen([ffmpeg, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-i", "-",
                               "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                               "-movflags", "+faststart", str(mudo)], stdin=subprocess.PIPE)
        for f in range(total):
            page.evaluate(f"seek({f * 1000 / fps})")
            ff.stdin.write(page.screenshot(type="jpeg", quality=92))
            if f % (fps * 10) == 0:
                print(_("\r  grabando {p} %", p=f"{f * 100 // total:3d}"), end="", flush=True)
        ff.stdin.close()
        if ff.wait():
            raise RuntimeError(_("ffmpeg falló al codificar el vídeo"))
        print(_("\r  grabando 100 %"))
    finally:
        page.close()
        srv.__exit__()
    salida.parent.mkdir(parents=True, exist_ok=True)
    if audio:
        r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(mudo), "-stream_loop", "-1", "-i", str(audio),
                            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                            "-af", f"afade=t=out:st={max(0, total / fps - 3):.2f}:d=3", "-shortest",
                            "-movflags", "+faststart", str(salida)], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(_("ffmpeg falló al poner la música: {e}", e=r.stderr.strip()[-400:]))
        mudo.unlink()
    else:
        shutil.move(str(mudo), str(salida))
    return salida
