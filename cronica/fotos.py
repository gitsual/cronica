"""Fotografía las fichas del mosaico de un hito ya servido (la app en uso la graba recorrido.py).

  storybook  ficha = cada componente (su primera story), recortada a lo que ocupa, en claro y oscuro
  web        ficha = cada pantalla enlazada desde la portada, entera, en claro y oscuro (si la app lo distingue)

Devuelve (y deja en fotos.json) {fichas: [{key, nombre, light: {file, w, h}, dark}], stories, variantes}.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

MARGEN = 24
MAX_FICHAS = 48
MAX_PANTALLAS = 8

CAJA_VISIBLE = """() => {
  const docs = document.querySelector('#storybook-docs');
  const root = (docs && !docs.hidden && docs.offsetHeight > 20) ? docs
    : (document.querySelector('#storybook-root') || document.querySelector('#root') || document.body);
  const r = root.getBoundingClientRect();
  // Lo que se ve: texto, hojas (svg, img, input) y cajas con fondo o borde.
  // Un contenedor que ocupa todo el ancho sin pintar nada no cuenta.
  let x0 = Infinity, y0 = Infinity, x1 = 0, y1 = 0;
  const add = b => {
    if (b.width < 1 || b.height < 1) return;
    x0 = Math.min(x0, b.left); y0 = Math.min(y0, b.top); x1 = Math.max(x1, b.right); y1 = Math.max(y1, b.bottom);
  };
  const paints = el => {
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return false;
    const bg = cs.backgroundColor;
    return (bg && bg !== 'transparent' && !/rgba\\(.*,\\s*0\\)$/.test(bg))
      || parseFloat(cs.borderTopWidth) + parseFloat(cs.borderBottomWidth) > 0
      || cs.boxShadow !== 'none' || cs.backgroundImage !== 'none';
  };
  for (const el of root.querySelectorAll('*')) {
    const b = el.getBoundingClientRect();
    const leaf = el.children.length === 0 || el instanceof SVGSVGElement;
    if (!leaf && !paints(el)) continue;
    if (!leaf && b.width >= r.width - 2 && b.height >= r.height - 2) continue;
    add(b);
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (!n.textContent.trim()) continue;
    const range = document.createRange(); range.selectNodeContents(n); add(range.getBoundingClientRect());
  }
  if (x0 === Infinity) return null;
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}"""

# Una página «vacía» (error de build, pantalla en blanco) no vale como hito.
CONTENIDO = """() => {
  let n = 0;
  for (const el of document.body.querySelectorAll('*')) {
    const b = el.getBoundingClientRect();
    if (b.width > 4 && b.height > 4 && getComputedStyle(el).visibility !== 'hidden') n++;
  }
  return { elementos: n, texto: (document.body.innerText || '').trim().length };
}"""


def _asentar(page, extra: int = 400) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass
    try:
        page.evaluate("document.fonts.ready")
    except Exception:
        pass
    page.wait_for_timeout(extra)


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")[:80] or "inicio"


def _guardar(out: Path, datos: dict) -> dict:
    (out / "fotos.json").write_text(json.dumps(datos, indent=1, ensure_ascii=False), encoding="utf-8")
    return datos


# ---------------------------------------------------------------- storybook

def _indice(page, base: str) -> list[dict]:
    for nombre in ("index.json", "stories.json"):
        r = page.request.get(f"{base}/{nombre}")
        if r.ok:
            try:
                datos = r.json()
            except Exception:
                continue
            entradas = datos.get("entries") or datos.get("stories") or {}
            return [{"id": e.get("id", k), "title": e.get("title") or e.get("kind", ""), "name": e.get("name", ""),
                     "type": e.get("type", "story"), "tags": e.get("tags") or []} for k, e in entradas.items()]
    return []


def _una_por_componente(entradas: list[dict]) -> list[dict]:
    """La story principal de cada componente y, además, cada página de documentación suelta (una guía en MDX
    que no acompaña a ningún componente): también es interfaz que alguien abre y lee."""
    por_titulo: dict[str, list[dict]] = {}
    con_stories = {e["title"] for e in entradas if e["type"] == "story"}
    for e in entradas:
        suelta = e["type"] == "docs" and ("unattached-mdx" in e["tags"] or e["title"] not in con_stories)
        if (e["type"] == "story" or suelta) and e["title"]:
            por_titulo.setdefault(e["title"], []).append(e)
    elegidas = []
    for lista in por_titulo.values():
        elegidas.append(next((e for e in lista if e["name"].lower() in ("default", "primary", "básico", "basico",
                                                                          "basic", "playground")), lista[0]))
    return elegidas


def storybook(navegador, base: str, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    page = navegador.new_page(viewport={"width": 1280, "height": 900})
    entradas = _indice(page, base)
    stories = _una_por_componente(entradas)[:MAX_FICHAS]
    fichas, avisos = [], []
    for s in stories:
        ficha = {"key": s["title"], "nombre": s["title"].split("/")[-1], "id": s["id"]}
        crudas = {}
        for tema in ("light", "dark"):
            sufijo = "&globals=theme:dark;backgrounds.value:!hex(1b1b1f)" if tema == "dark" else ""
            try:
                modo = "docs" if s["type"] == "docs" else "story"
                page.goto(f"{base}/iframe.html?id={s['id']}&viewMode={modo}{sufijo}")
                _asentar(page)
                caja = page.evaluate(CAJA_VISIBLE)
                if not caja:
                    raise RuntimeError("vacía")
                x, y = max(0, caja["x"] - MARGEN), max(0, caja["y"] - MARGEN)
                w, h = min(1280 - x, caja["w"] + 2 * MARGEN), min(900 - y, caja["h"] + 2 * MARGEN)
                if w < 8 or h < 8:
                    raise RuntimeError("vacía")
                png = page.screenshot(clip={"x": x, "y": y, "width": w, "height": h})
                if tema == "dark" and png == crudas.get("light"):
                    continue  # este Storybook no cambia con el tema: no hay versión oscura
                crudas[tema] = png
                nombre = f"{_slug(s['id'])}.{tema}.png"
                (out / nombre).write_bytes(png)
                ficha[tema] = {"file": nombre, "w": round(w), "h": round(h)}
            except Exception as error:  # una story rota en un commit viejo no para el resto
                ficha[tema] = None
                if tema == "light":
                    avisos.append(f"{s['id']}: {str(error).splitlines()[0][:100]}")
        if ficha.get("light"):
            fichas.append(ficha)
    page.close()

    # El marco de Storybook (barra lateral, barra de herramientas): también cambia de un hito a otro.
    if fichas:
        marco = navegador.new_page(viewport={"width": 1600, "height": 900})
        try:
            primera = next((f["id"] for f in fichas if "foundation" not in f["key"].lower()), fichas[0]["id"])
            marco.goto(f"{base}/index.html?path=/story/{primera}&panel=false")
            _asentar(marco, 1200)
            # Solo el marco: el lienzo del componente se tapa, que ya se compara ficha a ficha.
            marco.add_style_tag(content="#storybook-preview-wrapper, #storybook-preview-iframe { visibility: hidden !important }")
            marco.screenshot(path=str(out / "marco.png"))
        except Exception as error:
            avisos.append(f"marco: {str(error).splitlines()[0][:100]}")
        finally:
            marco.close()
    n_stories = sum(1 for e in entradas if e["type"] == "story")
    variantes: dict[str, list[dict]] = {}
    for e in entradas:
        if e["type"] == "story":
            variantes.setdefault(e["title"], []).append({"id": e["id"], "nombre": e["name"]})
    return _guardar(out, {"fichas": fichas, "stories": n_stories, "variantes": variantes, "avisos": avisos})


# ---------------------------------------------------------------- web

def _rutas(page, base: str) -> list[str]:
    hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
    origen = urlparse(base)
    vistas, rutas = set(), []
    for href in hrefs:
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        u = urlparse(urljoin(base + "/", href))
        if (u.scheme, u.netloc) != (origen.scheme, origen.netloc):
            continue
        ruta = (u.path or "/") + (f"#{u.fragment}" if u.fragment.startswith("/") else "")
        ext = Path(u.path).suffix.lower()
        if ext and ext not in (".html", ".htm"):
            continue
        if ruta not in vistas and ruta not in ("/", "/index.html"):
            vistas.add(ruta)
            rutas.append(ruta)
    return rutas[:MAX_PANTALLAS - 1]


def web(navegador, base: str, out: Path) -> dict | None:
    """None si la portada sale vacía (build roto o app que no arranca sin backend)."""
    out.mkdir(parents=True, exist_ok=True)
    ctx = navegador.new_context(viewport={"width": 1920, "height": 1080})
    page = ctx.new_page()
    page.goto(base + "/")
    _asentar(page, 1200)
    hay = page.evaluate(CONTENIDO)
    if hay["elementos"] < 3 and hay["texto"] < 10:
        ctx.close()
        return None
    rutas = ["/"] + _rutas(page, base)
    ctx.close()

    fichas, avisos = [], []
    for ruta in rutas:
        ficha = {"key": ruta, "nombre": "inicio" if ruta == "/" else ruta.strip("/#").split("/")[-1] or ruta}
        crudas = {}
        for tema in ("light", "dark"):
            ctx = navegador.new_context(viewport={"width": 1440, "height": 900},
                                        color_scheme="dark" if tema == "dark" else "light")
            page = ctx.new_page()
            try:
                page.goto(base + ruta)
                _asentar(page, 800)
                png = page.screenshot()
                if tema == "dark" and png == crudas.get("light"):
                    continue
                crudas[tema] = png
                nombre = f"{_slug(ruta)}.{tema}.png"
                (out / nombre).write_bytes(png)
                ficha[tema] = {"file": nombre, "w": 1440, "h": 900}
            except Exception as error:
                ficha[tema] = None
                avisos.append(f"{ruta}: {str(error).splitlines()[0][:100]}")
            finally:
                ctx.close()
        if ficha.get("light"):
            fichas.append(ficha)

    return _guardar(out, {"fichas": fichas, "stories": 0, "avisos": avisos})
