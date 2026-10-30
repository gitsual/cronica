"""Los ajustes de cronica, guardados en un fichero y editables desde su ventana, «la redacción».

    cronica --settings          (o doble clic en cronica.exe sin carpeta)

Lo que se guarda aquí son los valores por defecto de cada vídeo: el idioma, el modelo que escribe los titulares,
la música, la estética, cuántos hitos y cuántos segundos de app en uso. Una opción en la línea de órdenes manda
sobre el ajuste; el ajuste, sobre el valor de fábrica.
"""
from __future__ import annotations

import copy
import functools
import http.server
import json
import os
import sys
import threading
import urllib.request
from importlib import resources
from pathlib import Path

BACKENDS = ("off", "ollama", "openai")
OLLAMA, OPENAI = "http://127.0.0.1:11434", "http://127.0.0.1:1234/v1"
DEFECTO = {
    "lang": "en",
    "ai": {"backend": "off", "url": "", "model": "", "key": ""},
    "music": "consola",
    "look": "diario",
    "max_milestones": 30,
    "seconds": 6.0,
}


def ruta() -> Path:
    if os.environ.get("CRONICA_CONFIG"):
        return Path(os.environ["CRONICA_CONFIG"])
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "cronica" / "settings.json"


def _limpiar(d: dict) -> dict:
    """Lo leído, encima de los valores de fábrica; lo que no tiene sentido se queda en el de fábrica."""
    from . import i18n, montaje, musica
    salida = copy.deepcopy(DEFECTO)
    if d.get("lang") in i18n.IDIOMAS:
        salida["lang"] = d["lang"]
    ai = d.get("ai") or {}
    if ai.get("backend") in BACKENDS:
        salida["ai"]["backend"] = ai["backend"]
    for k in ("url", "model", "key"):
        if isinstance(ai.get(k), str):
            salida["ai"][k] = ai[k].strip()
    if d.get("music") in musica.ESTILOS or (isinstance(d.get("music"), str) and Path(d["music"]).is_file()):
        salida["music"] = d["music"]
    if d.get("look") in montaje.ESTETICAS or (isinstance(d.get("look"), str) and Path(d["look"]).is_file()):
        salida["look"] = d["look"]
    try:
        salida["max_milestones"] = max(2, min(200, int(d.get("max_milestones", 30))))
        salida["seconds"] = max(1.0, min(60.0, float(d.get("seconds", 6.0))))
    except (TypeError, ValueError):
        pass
    return salida


def leer() -> dict:
    try:
        return _limpiar(json.loads(ruta().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return copy.deepcopy(DEFECTO)


def guardar(d: dict) -> dict:
    limpio = _limpiar(d)
    ruta().parent.mkdir(parents=True, exist_ok=True)
    ruta().write_text(json.dumps(limpio, indent=1, ensure_ascii=False), encoding="utf-8")
    return limpio


# ---------------------------------------------------------------- el modelo

def base(ai: dict) -> str:
    return (ai.get("url") or (OPENAI if ai.get("backend") == "openai" else OLLAMA)).rstrip("/")


def _pedir(url: str, clave: str = "", cuerpo: dict | None = None, timeout: float = 8) -> dict:
    cab = {"Content-Type": "application/json"}
    if clave:
        cab["Authorization"] = f"Bearer {clave}"
    req = urllib.request.Request(url, json.dumps(cuerpo).encode() if cuerpo is not None else None, cab)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def modelos(ai: dict) -> list[str]:
    """Los modelos que ofrece el servidor: /api/tags en Ollama, /models en uno compatible con OpenAI."""
    if ai.get("backend") == "ollama":
        return [m["name"] for m in _pedir(base(ai) + "/api/tags").get("models", []) if "embed" not in m["name"]]
    if ai.get("backend") == "openai":
        return [m["id"] for m in _pedir(base(ai) + "/models", ai.get("key", "")).get("data", [])]
    return []


def probar(ai: dict) -> str:
    """Una pregunta corta al modelo elegido; devuelve lo que contesta (o lanza)."""
    from . import rotulos
    return rotulos.llm("Answer with one word: OK", ai.get("model") or None, ai, json_mode=False, timeout=60).strip()[:80]


# ---------------------------------------------------------------- la ventana

class _Redaccion(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, datos, codigo: int = 200) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _fichero(self, recurso, tipo: str) -> None:
        cuerpo = recurso.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        paquete = resources.files("cronica")
        if self.path in ("/", "/index.html"):
            return self._fichero(paquete.joinpath("redaccion", "ajustes.html"), "text/html; charset=utf-8")
        if self.path.startswith("/fonts/") and "/" not in self.path[7:]:
            f = paquete.joinpath("reproductor", "fonts", self.path[7:])
            if f.is_file():
                tipo = "font/woff2" if f.name.endswith(".woff2") else "font/ttf"
                return self._fichero(f, tipo)
        if self.path == "/api/settings":
            from . import __version__, musica, montaje
            return self._json({"settings": leer(), "path": str(ruta()), "version": __version__,
                               "music": list(musica.ESTILOS), "looks": list(montaje.ESTETICAS)})
        self.send_error(404)

    def do_POST(self):
        datos = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        try:
            if self.path == "/api/settings":
                return self._json({"settings": guardar(datos)})
            if self.path == "/api/models":
                return self._json({"models": modelos(datos)})
            if self.path == "/api/test":
                return self._json({"answer": probar(datos)})
        except Exception as error:
            return self._json({"error": str(error)[:300]}, 502)
        self.send_error(404)


class Redaccion:
    """El servidor de la ventana de ajustes, en un puerto libre de 127.0.0.1."""

    def __init__(self):
        self._srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Redaccion)
        self.url = f"http://127.0.0.1:{self._srv.server_address[1]}/"
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()

    def cerrar(self) -> None:
        self._srv.shutdown()
        self._srv.server_close()


def abrir_ventana() -> int:
    """Abre la redacción en una ventana de Chromium sin barras y espera a que se cierre."""
    from .i18n import _
    srv = Redaccion()
    print(_("La redacción está en {u} (cierra la ventana para terminar).", u=srv.url))
    try:
        import tempfile
        from playwright.sync_api import sync_playwright
        from .cli import _instalar_chromium
        with sync_playwright() as p, tempfile.TemporaryDirectory() as perfil:
            def lanzar():
                return p.chromium.launch_persistent_context(
                    perfil, headless=False, no_viewport=True,
                    args=[f"--app={srv.url}", "--window-size=980,1040"])
            try:
                ctx = lanzar()
            except Exception as error:
                if "Executable doesn't exist" not in str(error) and "playwright install" not in str(error):
                    raise
                _instalar_chromium()
                ctx = lanzar()
            pagina = next((pg for pg in ctx.pages if pg.url.startswith(srv.url)), None) or ctx.pages[0]
            if not pagina.url.startswith(srv.url):
                pagina.goto(srv.url)
            pagina.wait_for_event("close", timeout=0)
            ctx.close()
    except Exception:
        import webbrowser
        webbrowser.open(srv.url)
        try:
            input(_("Pulsa Intro cuando hayas terminado…"))
        except EOFError:
            pass
    finally:
        srv.cerrar()
    return 0
