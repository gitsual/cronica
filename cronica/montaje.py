"""Junta los hitos en datos.json, graba el reproductor fotograma a fotograma y le pone la música."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from importlib import resources
from pathlib import Path

from .servidor import Servidor

INTRO_MS, OUTRO_MS, EXTRACCION_MS = 2200, 5200, 7500
FPS_CLIP = 30  # los clips se graban a pasos; cada fotograma vale 1/30 s

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
             ocultar: tuple[str, ...] = ()) -> dict:
    """escenas: hitos ya grabados ({nn, sha, fecha, chip, titulo, cifras, fotos, dir, cap, barra}) y escenas
    especiales ({tipo: "extraccion", ...}), en orden. `ocultar`: cifras que no salen (p. ej. «lineas»).

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
        nombres = {x["key"]: x["nombre"] for x in f["fichas"]} | {"__marco__": "Storybook" if tipo == "storybook" else "Marco"}
        fichas = []
        for ficha in f["fichas"]:
            item = {"key": f"{h['cap']}:{ficha['key']}", "nombre": ficha["nombre"], "w": ficha["light"]["w"],
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
                       "cifras": cifras, "cap": h["cap"],
                       "barra": h["barra"],
                       "clip": f"{_rel(Path(h['dir_clip']), video)}/clip/" if h.get("dir_clip") else f"{rel}/clip/", "fotogramas": f["fotogramas"], "inicio": t, "dur": dur,
                       "nuevas": [nombres[k] for k in f.get("nuevas", []) if k in nombres],
                       "cambiadas": [nombres[k] for k in f.get("cambiadas", []) if k in nombres],
                       "fichas": fichas})
        t += dur
    ultimo = next((e["cifras"] for e in reversed(salida) if e["cifras"]), {})
    definicion = [[k, l] for k, l in CIFRAS[tipo] if ultimo.get(k) and k not in ocultar]
    datos = {
        "proyecto": proyecto, "titulo": textos.get("titulo") or proyecto, "cierre": textos.get("cierre") or "",
        "barra": f"{'storybook' if tipo == 'storybook' else 'localhost'} · {proyecto}", "cifras": definicion,
        "ocultar": list(ocultar), "fps_clip": FPS_CLIP, "intro": INTRO_MS, "outro": OUTRO_MS, "hitos": salida,
    }
    (video / "datos.json").write_text(json.dumps(datos, indent=1, ensure_ascii=False), encoding="utf-8")
    reproductor = resources.files("cronica").joinpath("reproductor")
    (video / "reproductor.html").write_text(reproductor.joinpath("reproductor.html").read_text(encoding="utf-8"),
                                            encoding="utf-8")
    # Las letras van con el reproductor: el vídeo se graba igual sin red.
    (video / "fonts").mkdir(exist_ok=True)
    for f in reproductor.joinpath("fonts").iterdir():
        (video / "fonts" / f.name).write_bytes(f.read_bytes())
    return datos


def duracion_ms(datos: dict) -> int:
    return datos["intro"] + sum(h["dur"] for h in datos["hitos"]) + datos["outro"]


def _abrir(navegador, video: Path):
    datos = json.loads((video / "datos.json").read_text(encoding="utf-8"))
    rutas = [video] + [(video / h["clip"]).resolve() for h in datos["hitos"] if h.get("clip")]
    raiz = Path(os.path.commonpath([str(r.resolve()) for r in rutas]))
    srv = Servidor(raiz)
    page = navegador.new_page(viewport={"width": 1920, "height": 1080})
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
                print(f"\r  grabando {f * 100 // total:3d} %", end="", flush=True)
        ff.stdin.close()
        if ff.wait():
            raise RuntimeError("ffmpeg falló al codificar el vídeo")
        print("\r  grabando 100 %")
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
            raise RuntimeError(f"ffmpeg falló al poner la música: {r.stderr.strip()[-400:]}")
        mudo.unlink()
    else:
        shutil.move(str(mudo), str(salida))
    return salida
