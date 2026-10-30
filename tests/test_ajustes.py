import http.server
import json
import threading
import urllib.request

import pytest

from cronica import ajustes, i18n, rotulos
from cronica.cli import _argumentos


@pytest.fixture(autouse=True)
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("CRONICA_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.delenv("CRONICA_LANG", raising=False)
    monkeypatch.delenv("CRONICA_LLM", raising=False)
    yield
    i18n.poner("en")


class _Falso(http.server.BaseHTTPRequestHandler):
    """Un servidor compatible con OpenAI que tiene un modelo y contesta «OK»."""
    pedidos: list = []

    def log_message(self, *args):
        pass

    def _json(self, datos):
        cuerpo = json.dumps(datos).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        _Falso.pedidos.append(("GET", self.path, self.headers.get("Authorization")))
        self._json({"data": [{"id": "modelo-falso"}]})

    def do_POST(self):
        cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Falso.pedidos.append(("POST", self.path, cuerpo["model"]))
        self._json({"choices": [{"message": {"content": "OK"}}]})


@pytest.fixture
def falso():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Falso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Falso.pedidos.clear()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown()


def test_sin_fichero_valen_los_de_fabrica():
    assert ajustes.leer() == ajustes.DEFECTO


def test_lo_que_no_tiene_sentido_no_se_guarda():
    s = ajustes.guardar({"lang": "fr", "ai": {"backend": "skynet", "model": " qwen3 "}, "music": "rock",
                         "max_milestones": "9999", "seconds": "x"})
    assert s["lang"] == "en" and s["ai"]["backend"] == "off" and s["ai"]["model"] == "qwen3"
    assert s["music"] == "consola" and s["max_milestones"] == 200
    assert ajustes.leer() == s


def test_los_ajustes_son_los_valores_por_defecto(tmp_path):
    ajustes.guardar({"lang": "es", "music": "noticiario", "look": "clasica", "max_milestones": 12, "seconds": 3,
                     "ai": {"backend": "openai", "url": "http://x:1234/v1", "model": "m1", "key": "k"}})
    a = _argumentos([str(tmp_path)])
    assert (a.idioma, a.musica, a.estetica, a.max_hitos, a.segundos) == ("es", "noticiario", "clasica", 12, 3)
    assert a.ia == "m1" and a.llm["url"] == "http://x:1234/v1" and a.llm["key"] == "k"
    # Una opción manda sobre el ajuste.
    b = _argumentos([str(tmp_path), "--lang", "en", "--music", "ambient", "-n", "5", "--ai", "m2"])
    assert (b.idioma, b.musica, b.max_hitos, b.ia, b.llm["model"]) == ("en", "ambiente", 5, "m2", "m2")


def test_sin_modelo_en_los_ajustes_no_hay_ia_salvo_que_se_pida(tmp_path):
    assert _argumentos([str(tmp_path)]).ia is None
    a = _argumentos([str(tmp_path), "--ai"])
    assert a.ia == "" and a.llm["backend"] == "ollama"


def test_la_variable_de_entorno_manda_sobre_el_servidor(tmp_path, monkeypatch):
    ajustes.guardar({"ai": {"backend": "ollama", "model": "m1"}})
    monkeypatch.setenv("CRONICA_LLM", "http://otra:1234/v1")
    a = _argumentos([str(tmp_path), "--ai"])
    assert a.llm["backend"] == "openai" and a.llm["url"] == "http://otra:1234/v1"


def test_modelos_y_prueba_contra_un_servidor(falso):
    ai = {"backend": "openai", "url": falso, "model": "modelo-falso", "key": "secreta"}
    assert ajustes.modelos(ai) == ["modelo-falso"]
    assert ajustes.probar(ai) == "OK"
    assert ("GET", "/v1/models", "Bearer secreta") in _Falso.pedidos
    assert ("POST", "/v1/chat/completions", "modelo-falso") in _Falso.pedidos


def test_la_ventana_lee_y_guarda(falso):
    srv = ajustes.Redaccion()
    try:
        html = urllib.request.urlopen(srv.url).read().decode()
        assert "The newsroom" in html and "La redacción" in html
        datos = json.loads(urllib.request.urlopen(srv.url + "api/settings").read())
        assert datos["settings"] == ajustes.DEFECTO and datos["path"].endswith("settings.json")
        pedir = lambda ruta, d: json.loads(urllib.request.urlopen(urllib.request.Request(
            srv.url + ruta, json.dumps(d).encode(), {"Content-Type": "application/json"})).read())
        assert pedir("api/models", {"backend": "openai", "url": falso})["models"] == ["modelo-falso"]
        guardado = pedir("api/settings", {**ajustes.DEFECTO, "lang": "es"})["settings"]
        assert guardado["lang"] == "es" and ajustes.leer()["lang"] == "es"
        assert urllib.request.urlopen(srv.url + "fonts/Newsreader.ttf").status == 200
    finally:
        srv.cerrar()


def test_los_titulares_usan_el_modelo_de_los_ajustes(falso):
    hitos = [{"nn": "01", "fecha": "2026-01-01", "titulo": "a", "nuevas": [], "commits": ["x"]}]
    _Falso.do_POST_original = _Falso.do_POST

    def contesta_json(self):
        json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._json({"choices": [{"message": {"content": '{"titulo": "T", "cierre": "C", "rotulos": {"01": "Uno"}}'}}]})
    _Falso.do_POST = contesta_json
    try:
        r = rotulos.con_ia("p", hitos, None, "en", {"backend": "openai", "url": falso, "model": "modelo-falso", "key": ""})
    finally:
        _Falso.do_POST = _Falso.do_POST_original
    assert r["rotulos"] == {"01": "Uno"} and r["titulo"] == "T"
