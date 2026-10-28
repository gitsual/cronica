"""Junta los hitos en datos.json, graba el reproductor fotograma a fotograma y le pone la música."""
from __future__ import annotations

import json
import shutil
import subprocess
from importlib import resources
from pathlib import Path

from .servidor import Servidor

INTRO_MS, OUTRO_MS = 3200, 7000

CIFRAS = {
    "storybook": [("componentes", "Componentes"), ("stories", "Stories"), ("ficheros", "Ficheros"),
                  ("lineas", "Líneas"), ("commits", "Commits")],
    "web": [("pantallas", "Pantallas"), ("ficheros", "Ficheros"), ("lineas", "Líneas"), ("commits", "Commits"),
            ("autores", "Autores")],
}
CIFRAS["estatico"] = CIFRAS["web"]


def preparar(video: Path, trabajo: Path, proyecto: str, tipo: str, hitos: list[dict], textos: dict,
             por_hito_ms: int) -> dict:
    """hitos: [{nn, sha, fecha, chip, titulo, cifras, fotos}] ya fotografiados, en orden."""
    if video.exists():
        shutil.rmtree(video)
    (video / "fotos").mkdir(parents=True)
    salida = []
    for h in hitos:
        origen = trabajo / "hitos" / h["sha"][:12]
        destino = video / "fotos" / h["nn"]
        destino.mkdir()
        f = h["fotos"]
        shutil.copy2(origen / f["principal"], destino / "principal.png")
        fichas = []
        for ficha in f["fichas"]:
            item = {"key": ficha["key"], "nombre": ficha["nombre"], "w": ficha["light"]["w"], "h": ficha["light"]["h"],
                    "cubre": tipo != "storybook"}
            for tema in ("light", "dark"):
                if ficha.get(tema):
                    shutil.copy2(origen / ficha[tema]["file"], destino / ficha[tema]["file"])
                    item[tema] = f"fotos/{h['nn']}/{ficha[tema]['file']}"
            fichas.append(item)
        visibles = [x for x in fichas if not any(p in x["key"].lower() for p in ("foundation", "intro", "welcome"))]
        cifras = {**h["cifras"], "componentes": len(visibles), "pantallas": len(fichas), "stories": f.get("stories", 0)}
        salida.append({"nn": h["nn"], "sha": h["sha"][:7], "fecha": h["fecha"], "chip": h["chip"],
                       "rotulo": textos["rotulos"].get(h["nn"], h["titulo"]), "cifras": cifras,
                       "principal": f"fotos/{h['nn']}/principal.png", "fichas": fichas})
    ultimo = salida[-1]["cifras"] if salida else {}
    definicion = [[k, l] for k, l in CIFRAS[tipo] if ultimo.get(k)]
    datos = {
        "proyecto": proyecto, "titulo": textos.get("titulo") or proyecto, "cierre": textos.get("cierre") or "",
        "barra": f"{'storybook' if tipo == 'storybook' else 'localhost'} · {proyecto}",
        "cifras": definicion, "por_hito": por_hito_ms, "intro": INTRO_MS, "outro": OUTRO_MS, "hitos": salida,
    }
    (video / "datos.json").write_text(json.dumps(datos, indent=1, ensure_ascii=False), encoding="utf-8")
    html = resources.files("cronica").joinpath("reproductor/reproductor.html").read_text(encoding="utf-8")
    (video / "reproductor.html").write_text(html, encoding="utf-8")
    return datos


def duracion_ms(datos: dict) -> int:
    return datos["intro"] + len(datos["hitos"]) * datos["por_hito"] + datos["outro"]


def _abrir(navegador, video: Path):
    srv = Servidor(video)
    page = navegador.new_page(viewport={"width": 1920, "height": 1080})
    page.goto(f"{srv.url}/reproductor.html")
    page.wait_for_function("window.ready === true", timeout=180_000)
    return srv, page


def fotogramas(navegador, video: Path, instantes_ms: list[int], destino: Path) -> list[Path]:
    """Fotos sueltas del vídeo, para revisarlo sin renderizarlo entero."""
    destino.mkdir(parents=True, exist_ok=True)
    srv, page = _abrir(navegador, video)
    rutas = []
    try:
        for ms in instantes_ms:
            page.evaluate(f"seek({ms})")
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
