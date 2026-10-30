import json

import pytest

from cronica import i18n, montaje
from cronica.cli import _argumentos, _guion, _mesa


@pytest.fixture(autouse=True)
def ingles():
    i18n.poner("en")
    yield
    i18n.poner("en")


def test_fechas_en_los_dos_idiomas():
    assert i18n.fecha_larga("2026-06-09") == "Tuesday, June 9, 2026"
    assert i18n.rango("2026-03-02", "2026-06-23") == "From March 2 to June 23, 2026"
    assert i18n.lapso("2026-03-02", "2026-06-23") == "Four months"
    assert i18n.fecha_corta("2026-06-09") == "9 JUN 2026"
    i18n.poner("es")
    assert i18n.fecha_larga("2026-06-09") == "Martes, 9 de junio de 2026"
    assert i18n.rango("2025-12-30", "2026-01-02") == "Del 30 de diciembre de 2025 al 2 de enero de 2026"
    assert i18n.lapso("2026-03-02", "2026-03-20") == "Tres semanas"
    assert i18n.fecha_corta("2026-08-09") == "9 AGO 2026"


def test_cada_texto_tiene_su_traduccion():
    assert i18n._("Núm. {i} de {n}", i=3, n=9) == "No. 3 of 9"
    assert i18n._("la página sale vacía") == "the page comes out empty"
    i18n.poner("es")
    assert i18n._("Núm. {i} de {n}", i=3, n=9) == "Núm. 3 de 9"
    assert all(k in i18n.EN for k in i18n.reproductor()["t"])


def test_el_video_lleva_sus_palabras(tmp_path):
    datos = montaje.preparar(tmp_path, "demo", "estatico", [], {"rotulos": {}})
    assert datos["lang"] == "en" and datos["t"]["En cifras"] == "By the numbers"
    assert ["lineas", "Lines"] not in datos["cifras"]   # sin escenas no hay cifras, pero tampoco se rompe
    i18n.poner("es")
    datos = json.loads(json.dumps(montaje.preparar(tmp_path, "demo", "estatico", [], {"rotulos": {}})))
    assert datos["t"]["En cifras"] == "En cifras" and datos["locale"] == "es-ES"


def test_opciones_en_ingles_y_en_espanol(tmp_path):
    a = _argumentos([str(tmp_path), "--music", "newsreel", "--look", "classic", "--hide", "lines", "--mode", "static"])
    b = _argumentos([str(tmp_path), "--musica", "noticiario", "--estetica", "clasica", "--ocultar", "lineas",
                     "--modo", "estatico", "--lang", "es"])
    for campo in ("musica", "estetica", "ocultar", "modo"):
        assert getattr(a, campo) == getattr(b, campo)
    assert a.idioma == "en" and b.idioma == "es" and i18n.idioma == "es"
    with pytest.raises(SystemExit):
        _argumentos([str(tmp_path), "--hide", "bananas"])


def test_mesa_de_redaccion_en_los_dos_idiomas():
    ingles = {"title": "Garden", "closing": "x", "headlines": {"abc1234": "Cards"},
              "acts": [{"from": "abc1234", "title": "Act", "line": "Why"}]}
    dentro = _mesa(ingles)
    assert dentro["titulo"] == "Garden" and dentro["rotulos"] == {"abc1234": "Cards"}
    assert dentro["actos"] == [{"desde": "abc1234", "titulo": "Act", "frase": "Why"}]
    assert _mesa(dentro, al_ingles=True)["acts"][0]["line"] == "Why"


def test_guion_de_la_demo_en_ingles():
    g = _guion({"site": "x", "steps": [{"story": "a--b", "seconds": 5, "headline": "Hi",
                                        "actions": [{"click": "button", "in": "toolbar"}, {"scroll": 300}]}]})
    paso = g["pasos"][0]
    assert g["sitio"] == "x" and paso["segundos"] == 5 and paso["rotulo"] == "Hi"
    assert paso["acciones"] == [{"clic": "button", "en": "barra"}, {"rueda": 300}]
