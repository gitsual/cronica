"""Las imágenes del README: logotipo, el proceso, la gráfica del ejemplo, la terminal, la música y las galeradas.

    python examples/garden/construir.py garden
    CRONICA_CACHE=cache cronica garden > garden.log
    CRONICA_CACHE=cache cronica garden --preview
    python assets/readme/construir.py garden cache/garden-<hash> garden.log

Todo sale de la ejecución real del ejemplo: las cifras, la salida de la terminal y los fotogramas. Se dibuja con
las mismas letras que el vídeo y el mismo papel, tinta y sello.
"""
import base64
import io
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "assets"))
from cronica import historia, musica  # noqa: E402
from icono import sello  # noqa: E402

FUENTES = (RAIZ / "cronica" / "reproductor" / "fonts").as_uri()
SALIDA = RAIZ / "assets"
PAPEL, TINTA, SELLO, GASTADA, SALA, SELLO_NEGRO = "#EDE6D6", "#191612", "#B3301C", "#5A5247", "#12100D", "#E0533B"

BASE = f"""
@font-face{{font-family:Gotica;src:url({FUENTES}/UnifrakturMaguntia.ttf)}}
@font-face{{font-family:News;src:url({FUENTES}/Newsreader.ttf);font-weight:200 800}}
@font-face{{font-family:News;src:url({FUENTES}/Newsreader-Italic.ttf);font-style:italic;font-weight:200 800}}
@font-face{{font-family:Mono;src:url({FUENTES}/IBMPlexMono-Medium.woff2)}}
*{{box-sizing:border-box;margin:0}} body{{background:transparent}}
.mono{{font-family:Mono;letter-spacing:.12em;text-transform:uppercase}}
.doble{{border-top:3px solid currentColor;height:6px;border-bottom:1px solid currentColor}}
"""


def sello_uri(lado: int = 512) -> str:
    buf = io.BytesIO()
    sello(lado).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class Imprenta:
    """Un Chromium para pasar HTML a PNG, esperando a que las letras estén cargadas."""

    def __init__(self, pw):
        self.nav = pw.chromium.launch()

    def foto(self, html: str, destino: Path, ancho: int, alto: int, transparente: bool = False, escala: float = 2):
        ctx = self.nav.new_context(viewport={"width": ancho, "height": alto}, device_scale_factor=escala)
        page = ctx.new_page()
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(f"<!doctype html><meta charset='utf-8'><style>{BASE}</style>{html}")
        page.goto(Path(f.name).as_uri())
        page.evaluate("""async () => { for (const f of ['40px Gotica','800 40px News','italic 40px News','40px Mono'])
                                          await document.fonts.load(f); }""")
        page.screenshot(path=str(destino), omit_background=transparente)
        ctx.close()
        Path(f.name).unlink()


# ---------------------------------------------------------------- logotipo

def logotipo(imp: Imprenta) -> None:
    for tema, tinta, rojo in (("light", TINTA, SELLO), ("dark", PAPEL, SELLO_NEGRO)):
        html = f"""
<div style="display:flex;align-items:center;gap:34px;padding:10px 24px;color:{tinta}">
  <img src="{sello_uri()}" style="width:150px;height:150px">
  <div>
    <div style="font:96px/1 Gotica;letter-spacing:-1px">Crónica</div>
    <div class="mono" style="font-size:15px;margin-top:14px;white-space:nowrap;color:{rojo}">The newsreel of an interface · from its git history</div>
  </div>
</div>"""
        imp.foto(html, SALIDA / f"logo-{tema}.png", 820, 190, transparente=True)


# ---------------------------------------------------------------- cómo se hace un número

PASOS = [
    ("Read", "historia.py", "The first-parent line of the branch. One PR is one issue; without merges, the commits that change the most."),
    ("Detect", "detectar.py", "Storybook, a web app or plain HTML, decided on the last commit and kept for the whole run."),
    ("Build", "construir.py", "Each issue in its own <i>clone --shared</i>. Your folder is never checked out or written to."),
    ("Photograph", "fotos.py · recorrido.py", "Every screen in light and dark, and the app in use with a visible cursor that clicks."),
    ("Compare", "cambios.py", "An issue that changes nothing on screen gets no page. Only what you can see makes the news."),
    ("Write", "rotulos.py", "Headlines from PR titles, or from a local model. <i>rotulos.json</i> is the news desk."),
    ("Print", "montaje.py · musica.py", "The player, frame by frame at 1080p and 30 fps, with music generated on the spot."),
]


def proceso(imp: Imprenta) -> None:
    columnas = "".join(f"""
<div class="col">
  <div class="n">{i}</div>
  <h3>{t}</h3>
  <p>{d}</p>
  <div class="mono mod">{m}</div>
</div>""" for i, (t, m, d) in enumerate(PASOS, 1))
    html = f"""
<style>
.hoja{{background:{PAPEL};color:{TINTA};padding:34px 40px 30px;width:1600px}}
.cab{{display:flex;justify-content:space-between;align-items:baseline}}
.fila{{display:grid;grid-template-columns:repeat(7,1fr) 170px;margin-top:22px}}
.col{{padding:0 18px;border-left:1px solid {TINTA}}} .col:first-child{{border-left:none;padding-left:0}}
.n{{font:800 64px/1 News;color:{SELLO}}} h3{{font:800 30px/1.1 News;margin:6px 0 10px}}
p{{font:italic 400 18px/1.35 News;color:{GASTADA};min-height:122px}} .mod{{font-size:11px;margin-top:10px}}
.fin{{display:flex;flex-direction:column;align-items:center;justify-content:center;border-left:3px double {TINTA};padding-left:18px}}
</style>
<div class="hoja">
  <div class="cab"><div style="font:44px Gotica">How an issue is made</div>
  <div class="mono" style="font-size:13px">From a git history to a newsreel, in seven steps</div></div>
  <div class="doble" style="margin-top:12px"></div>
  <div class="fila">{columnas}
    <div class="fin"><img src="{sello_uri(256)}" style="width:110px"><div class="mono" style="font-size:12px;margin-top:12px;text-align:center">&lt;folder&gt;-<br>evolution.mp4</div></div>
  </div>
  <div class="doble" style="margin-top:22px"></div>
  <div class="mono" style="font-size:11px;margin-top:10px;color:{GASTADA}">Everything is cached per issue · interrupted runs resume where they stopped · editing a headline only re-prints the film</div>
</div>"""
    imp.foto(html, SALIDA / "proceso.png", 1600, 470)


# ---------------------------------------------------------------- el ejemplo, número a número

def renglones(texto: str, ancho: int) -> list[str]:
    salida, actual = [], ""
    for palabra in texto.split():
        if actual and len(actual) + 1 + len(palabra) > ancho:
            salida.append(actual)
            actual = palabra
        else:
            actual = f"{actual} {palabra}".strip()
    return salida + [actual]


def grafica(imp: Imprenta, repo: Path, publicados: set[str]) -> None:
    lineas = historia.git(repo, "log", "--first-parent", "--reverse", "--format=%h|%ad|%s%n%b", "--date=short", "main")
    commits = []
    for bloque in re.split(r"\n(?=[0-9a-f]{7}\|)", lineas.strip()):
        cab, *cuerpo = bloque.split("\n")
        sha, fecha, asunto = cab.split("|", 2)
        titulo = next((c for c in cuerpo if c.strip()), asunto) if asunto.startswith("Merge") else asunto
        commits.append((sha, fecha, titulo.strip(), historia.cifras_git(repo, sha)["lineas"]))

    ancho, alto, izq, base = 1500, 520, 70, 340
    paso = (ancho - izq - 40) / len(commits)
    tope = max(c[3] for c in commits) * 1.15
    marcas = []
    for i, (sha, fecha, titulo, n) in enumerate(commits):
        x = izq + i * paso + paso * 0.2
        w = paso * 0.6
        h = (base - 60) * n / tope
        sale = sha in publicados
        estilo = (f'fill="{TINTA}"' if sale else f'fill="none" stroke="{GASTADA}" stroke-width="2" stroke-dasharray="6 5"')
        marcas.append(f'<rect x="{x:.0f}" y="{base - h:.0f}" width="{w:.0f}" height="{h:.0f}" {estilo}/>')
        marcas.append(f'<text x="{x + w / 2:.0f}" y="{base - h - 12:.0f}" class="v">{n}</text>')
        cx = x + w / 2
        marcas.append(f'<circle cx="{cx:.0f}" cy="{base + 26}" r="9" fill="{SELLO if sale else "none"}" stroke="{SELLO}" stroke-width="2"/>')
        marcas.append(f'<text x="{cx:.0f}" y="{base + 62}" class="f">{fecha[5:]}</text>')
        for k, renglon in enumerate(renglones(titulo.split(":")[-1].strip().capitalize(), 17)[:3]):
            marcas.append(f'<text x="{cx:.0f}" y="{base + 86 + k * 19}" class="t" {"" if sale else "font-style=italic"}>{renglon}</text>')
        if not sale:
            marcas.append(f'<text x="{cx:.0f}" y="{base - h - 40:.0f}" class="nota">no page: nothing changes on screen</text>')
    svg = f"""<svg width="{ancho}" height="{alto}" xmlns="http://www.w3.org/2000/svg">
<style>.v{{font:800 22px News;fill:{TINTA};text-anchor:middle}} .f{{font:13px Mono;fill:{GASTADA};text-anchor:middle;letter-spacing:.1em}}
.t{{font:15px News;fill:{TINTA};text-anchor:middle}} .nota{{font:italic 15px News;fill:{SELLO};text-anchor:middle}}</style>
<line x1="{izq - 10}" x2="{ancho - 30}" y1="{base}" y2="{base}" stroke="{TINTA}" stroke-width="2"/>
{''.join(marcas)}</svg>"""
    html = f"""
<div style="background:{PAPEL};color:{TINTA};padding:30px 40px 18px;width:1580px">
  <div style="display:flex;justify-content:space-between;align-items:baseline">
    <div style="font:800 34px News">The example, issue by issue</div>
    <div class="mono" style="font-size:12px;color:{GASTADA}">Lines of interface code after each PR · <span style="color:{SELLO}">●</span> got a page in the video</div>
  </div>
  <div class="doble" style="margin:10px 0 18px"></div>
  {svg}
</div>"""
    imp.foto(html, SALIDA / "cifras.png", 1580, 640)


# ---------------------------------------------------------------- la terminal

def terminal(imp: Imprenta, log: Path, proyecto: str, tmp: Path) -> None:
    texto = log.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    ruta = re.search(r"^(\S:\\.*?\\" + re.escape(proyecto) + r")$", texto, re.M).group(1)
    carpeta = "C:\\projects\\" + proyecto
    texto = texto.replace(ruta, carpeta)
    texto = re.sub(r"\S:\\[^\s]*\\cache\\", r"%LOCALAPPDATA%\\cronica\\", texto)
    texto = re.sub(r"\S:\\[^\s]*?\\(" + re.escape(proyecto) + r"-[\w-]+\.mp4)", lambda m: "C:\\projects\\" + m.group(1), texto)
    lineas = [l for l in texto.split("\n")]
    estados: list[tuple[list[str], float]] = []
    vistas: list[str] = []
    orden = "cronica " + carpeta
    for k in range(0, len(orden) + 1, 2):
        estados.append(([f"$ {orden[:k]}▌"], 0.06))
    estados.append(([f"$ {orden}"], 0.5))
    vistas.append(f"$ {orden}")
    for l in lineas:
        if "recording" in l:
            for paso in [p for p in l.split("\r") if p.strip()]:
                estados.append((vistas + [paso.rstrip()], 0.35))
            vistas.append([p for p in l.split("\r") if p.strip()][-1].rstrip())
            continue
        vistas.append(l.rstrip())
        estados.append((list(vistas), 0.45 if l.strip().startswith("[") else 0.15))
    estados[-1] = (estados[-1][0], 4.0)

    def pintar(l: str) -> str:
        l = l.replace("&", "&amp;").replace("<", "&lt;")
        l = re.sub(r"(nothing changes on screen: no page)", rf"<span style='color:{GASTADA}'>\1</span>", l)
        l = re.sub(r"\bok\b", rf"<b style='color:{SELLO_NEGRO}'>ok</b>", l)
        l = re.sub(r"^\$ ", rf"<span style='color:{SELLO_NEGRO}'>$</span> ", l)
        l = re.sub(r"^(Done.*)$", r"<b>\1</b>", l)
        return l

    lista = []
    for i, (vis, dur) in enumerate(estados):
        cuerpo = "\n".join(pintar(v) for v in vis)
        html = f"""
<div style="background:{SALA};color:{PAPEL};width:1560px;height:600px;padding:0;border:1px solid #3a342c">
  <div style="display:flex;justify-content:space-between;padding:10px 18px;border-bottom:1px solid #3a342c">
    <span class="mono" style="font-size:11px;color:#8f8676">Terminal</span><span style="font:20px Gotica">Crónica</span>
    <span class="mono" style="font-size:11px;color:#8f8676">time compressed</span></div>
  <pre style="font:14px/1.6 Mono;padding:16px 20px;white-space:pre">{cuerpo}</pre>
</div>"""
        png = tmp / f"t{i:03d}.png"
        imp.foto(html, png, 1560, 600, escala=1)
        lista.append(f"file '{png.as_posix()}'\nduration {dur}\n")
    lista.append(f"file '{png.as_posix()}'\n")
    (tmp / "lista.txt").write_text("".join(lista), encoding="utf-8")
    gif(["-f", "concat", "-safe", "0", "-i", str(tmp / "lista.txt")], SALIDA / "gifs" / "terminal.gif", 1200, 12)


# ---------------------------------------------------------------- GIF y galeradas

def gif(entrada: list[str], destino: Path, ancho: int, fps: int) -> None:
    destino.parent.mkdir(exist_ok=True)
    filtro = (f"fps={fps},scale={ancho}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=160:stats_mode=diff[p];"
              "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *entrada, "-filter_complex", filtro, str(destino)], check=True)


def galeradas(previa: Path) -> None:
    fotos = sorted(previa.glob("*.png"))[1:-1]   # sin la portada ni el cierre: solo los números
    entradas = []
    for f in fotos[:9]:
        entradas += ["-i", str(f)]
    pads = "".join(f"[{i}:v]scale=640:-1,pad=660:380:10:10:color=0xEDE6D6[v{i}];" for i in range(len(fotos[:9])))
    pila = "".join(f"[v{i}]" for i in range(len(fotos[:9])))
    filtro = pads + f"{pila}xstack=inputs=9:layout=0_0|w0_0|w0+w1_0|0_h0|w0_h0|w0+w1_h0|0_h0+h1|w0_h0+h1|w0+w1_h0+h1"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *entradas, "-filter_complex", filtro, "-frames:v", "1",
                    str(SALIDA / "galeradas.jpg")], check=True)


# ---------------------------------------------------------------- la música

def musicas(imp: Imprenta, tmp: Path) -> None:
    filas = []
    textos = {"consola": ("consola", "default", "a cheerful swing tune in C major, 116 bpm, like a console menu"),
              "noticiario": ("noticiario", "", "a cinema newsreel march in B♭, brass, snare and a cymbal per part"),
              "ambiente": ("ambiente", "", "a pad with no melody that changes chord with every scene")}
    for estilo in musica.ESTILOS:
        wav = musica.generar(tmp / f"{estilo}.wav", 24, [4, 8, 12, 16, 20], estilo)
        import wave
        with wave.open(str(wav)) as w:
            datos = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).reshape(-1, w.getnchannels())
        mono = np.abs(datos.mean(axis=1))
        cubos = np.array_split(mono, 284)
        picos = np.array([c.max() for c in cubos])
        picos = picos / picos.max()
        barras = "".join(f'<rect x="{i * 4}" y="{40 - p * 38:.1f}" width="2.4" height="{max(1, p * 76):.1f}" rx="1"/>'
                         for i, p in enumerate(picos))
        nombre, defecto, desc = textos[estilo]
        etiqueta = f' <span style="color:{SELLO}">· {defecto}</span>' if defecto else ""
        filas.append(f"""
<div style="display:grid;grid-template-columns:360px 1fr;align-items:center;padding:14px 0;border-top:1px solid {TINTA}">
  <div><div class="mono" style="font-size:16px">--musica {nombre}{etiqueta}</div>
  <div style="font:italic 17px/1.3 News;color:{GASTADA};margin-top:6px">{desc}</div></div>
  <svg width="1140" height="80" style="fill:{TINTA}">{barras}</svg>
</div>""")
    html = f"""<div style="background:{PAPEL};color:{TINTA};padding:26px 36px 14px;width:1580px">
<div style="font:800 30px News;margin-bottom:12px">Three scores, generated on your machine</div>{''.join(filas)}</div>"""
    imp.foto(html, SALIDA / "musica.png", 1580, 420)


if __name__ == "__main__":
    repo, cache, log = (Path(a) for a in sys.argv[1:4])
    import json
    datos = json.loads((cache / "video" / "datos.json").read_text(encoding="utf-8"))
    publicados = {h["sha"] for h in datos["hitos"]}
    with sync_playwright() as pw, tempfile.TemporaryDirectory() as t:
        imp = Imprenta(pw)
        logotipo(imp)
        proceso(imp)
        grafica(imp, repo, publicados)
        musicas(imp, Path(t))
        terminal(imp, log, repo.name, Path(t))
    galeradas(cache / "previa")
    print("hecho:", ", ".join(sorted(p.name for p in SALIDA.glob("*.*"))))
