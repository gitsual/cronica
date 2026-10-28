"""Graba la app en uso, fotograma a fotograma: un cursor visible busca lo nuevo, lo abre, pasa por encima,
pulsa y escribe. Cada fotograma lleva movimiento: no hay esperas grabadas.

Se graba «a pasos» (mover el ratón un poco, foto, otro poco, foto…) en vez de en tiempo real: así cada foto
es nítida, el ritmo no depende de lo rápida que sea la máquina y las cargas no se ven (se espera sin grabar).
"""
from __future__ import annotations

import math
from pathlib import Path

ANCHO, ALTO = 1600, 900
FPS = 30

# Cursor dibujado en el documento principal (encima del iframe de Storybook), movido desde Python.
CURSOR = """(() => {
  if (window.top !== window) return;
  const poner = () => {
    if (document.getElementById('__cronica_cursor')) return;
    const c = document.createElement('div');
    c.id = '__cronica_cursor';
    c.style.cssText = 'position:fixed;left:0;top:0;width:30px;height:30px;z-index:2147483647;pointer-events:none;' +
      'transform:translate(-100px,-100px);filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))';
    c.innerHTML = '<svg width="30" height="30" viewBox="0 0 24 24"><path d="M4 2.5l15 9.2-6.6 1.5 3.9 7.4-2.9 1.5-3.9-7.5L4 19.4z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    const r = document.createElement('div');
    r.id = '__cronica_onda';
    r.style.cssText = 'position:fixed;left:0;top:0;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;' +
      'border:3px solid #00b0bd;z-index:2147483646;pointer-events:none;opacity:0';
    document.documentElement.append(r, c);
  };
  window.__cronica = (x, y, onda) => {
    poner();
    document.getElementById('__cronica_cursor').style.transform = `translate(${x - 4}px,${y - 3}px)`;
    const r = document.getElementById('__cronica_onda');
    r.style.left = x + 'px'; r.style.top = y + 'px';
    r.style.opacity = onda > 0 ? String(onda) : '0';
    r.style.transform = `scale(${1.6 - onda * .9})`;
  };
  document.addEventListener('DOMContentLoaded', poner);
})()"""

ZOOM = 1.5
INTERACTIVOS = ("button:not([disabled]), input:not([type=hidden]):not([disabled]), textarea, select, "
                "[role=button], [role=tab], [role=switch], [role=checkbox], [role=radio], [role=combobox], "
                "[role=option], [role=menuitem], summary, label[for]")


class Lleno(Exception):
    """Se acabó el presupuesto de fotogramas de la escena."""


def _suave(k: float) -> float:
    return k * k * (3 - 2 * k)


class Camara:
    def __init__(self, page, carpeta: Path, maximo: int):
        self.page, self.carpeta, self.maximo = page, carpeta, maximo
        self.n, self.x, self.y, self.onda = 0, ANCHO * 0.55, ALTO * 0.5, 0.0
        carpeta.mkdir(parents=True, exist_ok=True)
        for viejo in carpeta.glob("*.jpg"):
            viejo.unlink()

    def foto(self) -> None:
        if self.n >= self.maximo:
            raise Lleno
        try:
            self.page.evaluate("([x, y, o]) => window.__cronica && window.__cronica(x, y, o)", [self.x, self.y, self.onda])
        except Exception:
            pass
        self.page.screenshot(path=str(self.carpeta / f"{self.n:04d}.jpg"), type="jpeg", quality=86)
        self.n += 1
        self.onda = max(0.0, self.onda - 0.2)

    def mover(self, x: float, y: float, fotos: int | None = None) -> None:
        x0, y0 = self.x, self.y
        dist = math.hypot(x - x0, y - y0)
        fotos = fotos or max(8, min(22, int(dist / 45)))
        # Una curva leve, como una mano: el punto medio se separa un poco de la recta.
        cx, cy = (x0 + x) / 2 + (y - y0) * 0.12, (y0 + y) / 2 - (x - x0) * 0.12
        for i in range(1, fotos + 1):
            k = _suave(i / fotos)
            self.x = (1 - k) ** 2 * x0 + 2 * (1 - k) * k * cx + k * k * x
            self.y = (1 - k) ** 2 * y0 + 2 * (1 - k) * k * cy + k * k * y
            self.page.mouse.move(self.x, self.y)
            self.foto()

    def deriva(self, fotos: int) -> None:
        """El cursor se mueve despacio sin ir a ningún sitio: la imagen nunca se queda quieta."""
        x0, y0 = self.x, self.y
        for i in range(fotos):
            self.x, self.y = x0 + 14 * math.sin(i / 7), y0 + 8 * math.sin(i / 5)
            self.page.mouse.move(self.x, self.y)
            self.foto()

    def clic(self) -> None:
        self.page.mouse.down()
        self.onda = 1.0
        self.foto()
        self.page.mouse.up()
        self.foto()
        self.foto()

    def escribir(self, texto: str) -> None:
        for ch in texto:
            self.page.keyboard.type(ch)
            self.foto()
            self.foto()

    def rueda(self, total: float, fotos: int) -> None:
        for i in range(fotos):
            self.page.mouse.wheel(0, total / fotos)
            self.page.wait_for_timeout(15)
            self.foto()


def _caja(handle) -> dict | None:
    try:
        b = handle.bounding_box()
    except Exception:
        return None
    if not b or b["width"] < 6 or b["height"] < 6:
        return None
    if b["x"] + b["width"] / 2 > ANCHO - 4 or b["y"] + b["height"] / 2 > ALTO - 4 or b["x"] < 0 or b["y"] < 0:
        return None
    return b


def _centro(b: dict) -> tuple[float, float]:
    return b["x"] + b["width"] / 2, b["y"] + min(b["height"] / 2, 18)


def _usar(cam: Camara, contexto, maximo: int = 3) -> int:
    """Pasa por encima de los controles de la vista, pulsa los botones y escribe en los campos."""
    usados = 0
    try:
        handles = contexto.query_selector_all(INTERACTIVOS)
    except Exception:
        return 0
    vistos = []
    for h in handles:
        if usados >= maximo:
            break
        b = _caja(h)
        if not b or any(abs(b["x"] - v["x"]) < 30 and abs(b["y"] - v["y"]) < 20 for v in vistos):
            continue
        vistos.append(b)
        tag = (h.evaluate("e => e.tagName") or "").lower()
        tipo = (h.get_attribute("type") or "").lower()
        cam.mover(*_centro(b))
        cam.deriva(5)
        if tag in ("input", "textarea") and tipo not in ("checkbox", "radio", "range", "button", "submit", "color", "file"):
            cam.clic()
            cam.escribir("Hola")
            cam.deriva(4)
        elif tag != "select":
            cam.clic()
            cam.deriva(6)
            try:
                cam.page.keyboard.press("Escape")  # cierra el menú o el diálogo que haya abierto el clic
            except Exception:
                pass
        usados += 1
    return usados


def _recorrer_texto(cam: Camara, zona: dict) -> None:
    """Para una página sin controles (documentación, foundations): baja leyendo y vuelve un poco."""
    cam.mover(zona["x"] + zona["width"] * 0.45, zona["y"] + zona["height"] * 0.5)
    cam.rueda(900, 40)
    cam.deriva(6)
    cam.rueda(-300, 14)


# ---------------------------------------------------------------- Storybook

def _iframe(page):
    h = page.query_selector("#storybook-preview-iframe")
    return h.content_frame() if h else None


def _esperar_story(page) -> None:
    try:
        f = _iframe(page)
        if f:
            f.wait_for_selector("#storybook-root *, #root *, #storybook-docs *, .sbdocs *", timeout=10_000)
    except Exception:
        pass
    # El componente, grande: en un lienzo de 1600 px un botón a tamaño real no se ve. Las páginas de
    # documentación (foundations) se dejan como son, para que se lean enteras.
    try:
        f = _iframe(page)
        if f:
            f.evaluate("""z => { const r = document.querySelector('#storybook-root, #root');
              if (r && !document.querySelector('#storybook-docs:not([hidden]) .sbdocs, .sb-show-main.sb-main-padded .sbdocs'))
                r.style.zoom = z }""", ZOOM)
    except Exception:
        pass
    page.wait_for_timeout(350)


def _ir_a_story(cam: Camara, story: dict) -> None:
    """Busca el componente en la barra lateral, escribiendo su nombre, y lo abre."""
    page = cam.page
    buscador = page.query_selector("#storybook-explorer-searchfield, input[placeholder*='Find' i], input[type=search]")
    b = _caja(buscador) if buscador else None
    if b:
        cam.mover(*_centro(b))
        cam.clic()
        page.keyboard.press("Control+A")
        cam.escribir(story["nombre"][:14])
        page.wait_for_timeout(250)
        cam.foto()
    enlace = page.query_selector(f"[data-item-id='{story['id']}'], a[href$='/story/{story['id']}']")
    b = _caja(enlace) if enlace else None
    if b:
        cam.mover(*_centro(b))
        cam.clic()
    else:
        page.evaluate("id => { const u = new URL(location.href); u.searchParams.set('path', '/story/' + id); "
                      "history.pushState({}, '', u); dispatchEvent(new PopStateEvent('popstate')) }", story["id"])
    _esperar_story(page)
    if buscador and b:
        try:
            buscador.fill("")
        except Exception:
            pass


def storybook(navegador, base: str, focos: list[dict], hermanas: dict[str, list[dict]], inicio: str,
              carpeta: Path, maximo: int) -> int:
    """focos: [{id, nombre}] de lo que entra o cambia; hermanas: otras stories de cada foco (variantes)."""
    ctx = navegador.new_context(viewport={"width": ANCHO, "height": ALTO})
    ctx.add_init_script(CURSOR)
    page = ctx.new_page()
    # Sin el panel de controles: la vista del componente ocupa toda la altura.
    page.goto(f"{base}/index.html?path=/story/{inicio}&panel=false")
    try:
        page.wait_for_selector("#storybook-preview-iframe", timeout=20_000)
    except Exception:
        pass
    _esperar_story(page)
    cam = Camara(page, carpeta, maximo)
    try:
        for story in focos:
            if story["id"] != inicio or cam.n:
                _ir_a_story(cam, story)
            f = _iframe(page)
            usados = _usar(cam, f) if f else 0
            if not usados:
                marco = page.query_selector("#storybook-preview-iframe")
                zona = _caja(marco) if marco else None
                if zona and f and f.evaluate("() => document.scrollingElement.scrollHeight > innerHeight + 80"):
                    _recorrer_texto(cam, zona)
                elif zona:
                    cam.mover(zona["x"] + zona["width"] * 0.4, zona["y"] + zona["height"] * 0.3)
                    cam.deriva(14)
            for variante in hermanas.get(story["id"], [])[:2]:
                enlace = page.query_selector(f"[data-item-id='{variante['id']}']")
                b = _caja(enlace) if enlace else None
                if not b:
                    continue
                cam.mover(*_centro(b))
                cam.clic()
                _esperar_story(page)
                f = _iframe(page)
                if not (f and _usar(cam, f, 1)):
                    cam.deriva(10)
        cam.deriva(8)
    except Lleno:
        pass
    finally:
        ctx.close()
    return cam.n


# ---------------------------------------------------------------- web

def web(navegador, base: str, focos: list[str], carpeta: Path, maximo: int) -> int:
    ctx = navegador.new_context(viewport={"width": ANCHO, "height": ALTO})
    ctx.add_init_script(CURSOR)
    page = ctx.new_page()
    page.goto(base + "/")
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
    cam = Camara(page, carpeta, maximo)
    try:
        for ruta in focos:
            if ruta != "/":
                destino = ruta.lstrip("/")
                enlace = page.query_selector(f"a[href='{ruta}'], a[href='{destino}'], a[href='./{destino}']")
                b = _caja(enlace) if enlace else None
                if b:
                    cam.mover(*_centro(b))
                    cam.clic()
                else:
                    page.goto(base + ruta)
                try:
                    page.wait_for_load_state("networkidle", timeout=8_000)
                except Exception:
                    pass
                page.wait_for_timeout(250)
            if not _usar(cam, page):
                cam.mover(ANCHO * 0.45, ALTO * 0.45)
                cam.deriva(10)
            if page.evaluate("() => document.scrollingElement.scrollHeight > innerHeight + 80"):
                cam.rueda(700, 30)
                cam.rueda(-700, 18)
        cam.deriva(8)
    except Lleno:
        pass
    finally:
        ctx.close()
    return cam.n
