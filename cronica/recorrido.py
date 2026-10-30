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
      'border:3px solid #b3301c;z-index:2147483646;pointer-events:none;opacity:0';
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
        ruta = str(self.carpeta / f"{self.n:04d}.jpg")
        try:
            self.page.screenshot(path=ruta, type="jpeg", quality=86)
        except Exception:
            # Un clic en un enlace: la foto ha caído en mitad de la navegación. Se espera a la página nueva.
            try:
                self.page.wait_for_load_state("load", timeout=8_000)
            except Exception:
                pass
            self.page.screenshot(path=ruta, type="jpeg", quality=86)
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


# ---------------------------------------------------------------- paseo final

def _conmutadores(page) -> list[dict]:
    """Los menús de la barra de Storybook que cambian un «global» (tema, diseño…): botón y opciones."""
    try:
        return page.evaluate("""() => {
          const almacen = (window.__STORYBOOK_PREVIEW__
            || document.querySelector('#storybook-preview-iframe')?.contentWindow?.__STORYBOOK_PREVIEW__)?.storyStoreValue;
          const tipos = almacen?.userGlobals?.globalTypes || almacen?.projectAnnotations?.globalTypes || {};
          return Object.entries(tipos).filter(([, t]) => t.toolbar && (t.toolbar.items || []).length > 1).map(([k, t]) => ({
            clave: k, titulo: t.toolbar.title || t.description || k, descripcion: t.description || '',
            opciones: t.toolbar.items.map(i => typeof i === 'string' ? { valor: i, titulo: i } : { valor: i.value, titulo: i.title || i.value }),
          }))
        }""")
    except Exception:
        return []


def _boton_de(page, c: dict):
    """El botón de la barra para un global: por su título, su descripción o el título de la opción activa."""
    candidatos = [c["descripcion"], c["titulo"]] + [o["titulo"] for o in c["opciones"]]
    for texto in candidatos:
        if not texto:
            continue
        # Storybook 9+: aria-label = «descripción + opción activa».
        for sel in (f"button[title='{texto}']", f"button[aria-label='{texto}']", f"button[aria-label^='{texto} ']"):
            h = page.query_selector(sel)
            if h and _caja(h):
                return h
    for h in page.query_selector_all("button"):
        t = (h.inner_text() or "").strip()
        if t and any(t == o["titulo"] for o in c["opciones"]) and _caja(h):
            return h
    return None


def _cambiar(cam: Camara, c: dict, valor: dict) -> bool:
    """Abre el menú del global en la barra y elige la opción, como lo haría una persona."""
    page = cam.page
    boton = _boton_de(page, c)
    b = _caja(boton) if boton else None
    if not b:
        return False
    cam.mover(*_centro(b))
    cam.clic()
    page.wait_for_timeout(200)
    opcion = None
    for sel in (f"[role=menuitem]:has-text('{valor['titulo']}')", f"[role=option]:has-text('{valor['titulo']}')",
                f"button:has-text('{valor['titulo']}')", f"a:has-text('{valor['titulo']}')"):
        for h in page.query_selector_all(sel):
            if _caja(h) and (h.inner_text() or "").strip() == valor["titulo"]:
                opcion = h
                break
        if opcion:
            break
    cam.deriva(4)
    ob = _caja(opcion) if opcion else None
    if not ob:
        page.keyboard.press("Escape")
        return False
    cam.mover(*_centro(ob), fotos=10)
    cam.clic()
    _esperar_story(page)
    cam.deriva(6)
    return True


# ---------------------------------------------------------------- demo guiada

def _abrir_story(cam: Camara, base: str, story: str, panel: str | None) -> None:
    """Va a la story desde la barra lateral si está a la vista; si no (o si hace falta el panel), por la URL."""
    page = cam.page
    enlace = None if panel else page.query_selector(f"[data-item-id='{story}']")
    b = _caja(enlace) if enlace else None
    if b:
        cam.mover(*_centro(b), fotos=10)
        cam.clic()
    else:
        # Los globals que ya se han cambiado (tema, diseño…) siguen puestos: van en la URL.
        globales = page.evaluate("() => new URL(location.href).searchParams.get('globals') || ''")
        page.goto(f"{base}/index.html?path=/story/{story}" + (f"&globals={globales}" if globales else "") +
                  ("" if panel else "&panel=false"))
        try:
            page.wait_for_selector("#storybook-preview-iframe", timeout=20_000)
        except Exception:
            pass
    _esperar_story(page)
    if panel:
        mostrar = page.query_selector("button[aria-label='Show addon panel'], button[title='Show addon panel']")
        mb = _caja(mostrar) if mostrar else None
        if mb:
            cam.mover(*_centro(mb))
            cam.clic()
            page.wait_for_timeout(500)
        pestana = page.query_selector(f"button:has-text('{panel}'), [role=tab]:has-text('{panel}')")
        pb = _caja(pestana) if pestana else None
        if pb:
            cam.mover(*_centro(pb))
            cam.clic()
            page.wait_for_timeout(600)


def _accion(cam: Camara, a: dict, conmutadores: list[dict]) -> None:
    page = cam.page
    if "global" in a:   # una opción de la barra de Storybook, por su título («Dark», «Compacto»…)
        for c in conmutadores:
            o = next((o for o in c["opciones"] if o["titulo"] == a["global"]), None)
            if o:
                _cambiar(cam, c, o)
                return
    elif "clic" in a:   # un selector de Playwright, en la story (por defecto) o en el Storybook («en»: «barra»)
        contexto = page if a.get("en") == "barra" else _iframe(page)
        h = None
        try:
            h = contexto.wait_for_selector(a["clic"], state="visible", timeout=4_000) if contexto else None
        except Exception:
            pass
        b = _caja(h) if h else None
        if b:
            cam.mover(*_centro(b))
            cam.deriva(3)
            cam.clic()
            page.wait_for_timeout(a.get("espera", 300))
            cam.deriva(a.get("deriva", 8))
    elif "usar" in a:
        f = _iframe(page)
        if f:
            _usar(cam, f, a["usar"])
    elif "leer" in a:
        marco = page.query_selector("#storybook-preview-iframe")
        zona = _caja(marco) if marco else None
        if zona:
            _recorrer_texto(cam, zona)
    elif "rueda" in a:
        cam.rueda(a["rueda"], a.get("fotos", 24))
    elif "deriva" in a:
        cam.deriva(a["deriva"])


def demo(navegador, base: str, pasos: list[dict], carpetas: list[Path]) -> list[int]:
    """Una demo guiada: cada paso abre una story, hace sus acciones (cambiar un global de la barra, pulsar algo
    de la story o del Storybook, usar los controles, leer) y se graba en su carpeta, con sus segundos justos.
    Los globals que se cambian siguen cambiados en los pasos siguientes, como al usarlo de verdad."""
    ctx = navegador.new_context(viewport={"width": ANCHO, "height": ALTO})
    ctx.add_init_script(CURSOR)
    ctx.grant_permissions(["clipboard-read", "clipboard-write"])
    page = ctx.new_page()
    page.goto(f"{base}/index.html?path=/story/{pasos[0]['story']}&panel=false")
    try:
        page.wait_for_selector("#storybook-preview-iframe", timeout=20_000)
    except Exception:
        pass
    _esperar_story(page)
    conmutadores = _conmutadores(page)
    hechos, x, y = [], ANCHO * 0.55, ALTO * 0.5
    try:
        for k, (paso, carpeta) in enumerate(zip(pasos, carpetas)):
            maximo = int(paso.get("segundos", 6) * FPS)
            cam = Camara(page, carpeta, maximo)
            cam.x, cam.y = x, y
            try:
                if k or paso.get("panel"):
                    _abrir_story(cam, base, paso["story"], paso.get("panel"))
                for a in paso.get("acciones", []):
                    _accion(cam, a, conmutadores)
                while True:   # lo que sobre, con el cursor en marcha: cada paso dura lo que pide
                    cam.deriva(10)
            except Lleno:
                pass
            hechos.append(cam.n)
            x, y = cam.x, cam.y
    finally:
        ctx.close()
    return hechos


def paseo(navegador, base: str, componentes: list[dict], carpeta: Path, maximo: int) -> int:
    """Recorre todos los componentes desde la barra lateral y, cada pocos, cambia un tema de la barra de Storybook
    (claro/oscuro, y cualquier otro global con menú: diseño, densidad…), para enseñarlo todo en todas sus formas."""
    ctx = navegador.new_context(viewport={"width": ANCHO, "height": ALTO})
    ctx.add_init_script(CURSOR)
    page = ctx.new_page()
    page.goto(f"{base}/index.html?path=/story/{componentes[0]['id']}&panel=false")
    try:
        page.wait_for_selector("#storybook-preview-iframe", timeout=20_000)
    except Exception:
        pass
    _esperar_story(page)
    cam = Camara(page, carpeta, maximo)
    conmutadores = _conmutadores(page)
    # Un cambio de tema cada pocos componentes, rotando por los globals y sus opciones.
    cambios_pendientes = []
    for c in conmutadores:
        for o in c["opciones"][1:] + c["opciones"][:1]:
            cambios_pendientes.append((c, o))
    cada = max(3, len(componentes) // max(1, len(cambios_pendientes) + 1))
    por_componente = max(14, (maximo - 60 * len(cambios_pendientes)) // max(1, len(componentes)) - 4)
    try:
        for k, comp in enumerate(componentes):
            if k and k % cada == 0 and cambios_pendientes:
                c, o = cambios_pendientes.pop(0)
                _cambiar(cam, c, o)
            # En la barra lateral: la story si está a la vista; si no, el componente (que se despliega y abre la
            # primera); si tampoco, se va directo.
            b = None
            for item in (comp["id"], comp["id"].split("--")[0]):
                enlace = page.query_selector(f"[data-item-id='{item}']")
                b = _caja(enlace) if enlace else None
                if b:
                    break
            if b:
                cam.mover(*_centro(b), fotos=8)
                cam.clic()
            else:
                page.goto(f"{base}/index.html?path=/story/{comp['id']}&panel=false")
            _esperar_story(page)
            f = _iframe(page)
            if not (f and por_componente > 24 and _usar(cam, f, 1)):
                marco = page.query_selector("#storybook-preview-iframe")
                zona = _caja(marco) if marco else None
                if zona:
                    cam.mover(zona["x"] + zona["width"] * 0.42, zona["y"] + zona["height"] * 0.3, fotos=6)
                cam.deriva(max(4, por_componente - 14))
        while cambios_pendientes:
            _cambiar(cam, *cambios_pendientes.pop(0))
        cam.deriva(10)
    except Lleno:
        pass
    finally:
        ctx.close()
    return cam.n
