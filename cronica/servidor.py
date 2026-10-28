"""Servidor estático en un puerto libre, con vuelta a index.html para las rutas de una SPA."""
from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path


class _Silencioso(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
                      ".svg": "image/svg+xml", ".wasm": "application/wasm"}

    def log_message(self, *args):
        pass

    def send_head(self):
        ruta = Path(self.translate_path(self.path))
        # Una ruta de la app (sin extensión) que no existe en disco es de la SPA: se sirve index.html.
        if not ruta.exists() and "." not in ruta.name:
            self.path = "/index.html"
        return super().send_head()


class Servidor:
    def __init__(self, raiz: Path):
        manejador = functools.partial(_Silencioso, directory=str(raiz))
        self._srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), manejador)
        self.url = f"http://127.0.0.1:{self._srv.server_address[1]}"
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()

    def __enter__(self) -> "Servidor":
        return self

    def __exit__(self, *exc) -> None:
        self._srv.shutdown()
        self._srv.server_close()
