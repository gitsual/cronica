"""La duración máxima y el formato del vídeo (horizontal o vertical)."""
import pytest

from cronica import montaje
from cronica.cli import _argumentos


def _clip(nn, segundos, nuevas=(), **extra):
    fotogramas = int(segundos * montaje.FPS_CLIP)
    return {"nn": nn, "fotogramas": fotogramas, "dur": round(fotogramas * 1000 / montaje.FPS_CLIP),
            "nuevas": list(nuevas), "cambiadas": [], "fichas": [{"key": f"0:{nn}"}], **extra}


def _total(salida, actos):
    fijo = montaje.INTRO_MS + montaje.OUTRO_MS + montaje.ACTO_MS * len(actos)
    return fijo + sum(e["dur"] for e in salida)


def test_si_ya_cabe_no_se_toca():
    salida = [_clip("01", 6), _clip("02", 6)]
    assert montaje.encajar(salida, {}, 60_000) is None
    assert all("vel" not in e for e in salida)


def test_acelera_los_clips_hasta_caber():
    salida = [_clip(f"{i:02d}", 6) for i in range(10)]   # 60 s de clips + 7,4 s fijos
    ajuste = montaje.encajar(salida, {}, 45_000)
    assert ajuste["quitados"] == 0 and 1 < ajuste["vel"] <= montaje.VEL_MAX
    assert _total(salida, {}) <= 45_000
    assert all(e["vel"] == salida[0]["vel"] for e in salida)


def test_quita_hitos_del_medio_y_el_acto_pasa_al_siguiente():
    salida = [_clip(f"{i:02d}", 6, nuevas=["Botón"] if i in (0, 9) else []) for i in range(10)]
    actos = {"03": {"titulo": "Segunda parte"}}
    ajuste = montaje.encajar(salida, actos, 20_000)
    assert ajuste["quitados"] > 0
    assert salida[0]["nn"] == "00" and salida[-1]["nn"] == "09"   # el primero y el último se quedan
    assert _total(salida, actos) <= 20_000
    assert all(e["dur"] >= montaje.ESCENA_MIN_MS - 1 for e in salida)
    assert len(actos) == 1 and next(iter(actos)) in {e["nn"] for e in salida}


def test_el_hito_quitado_deja_sus_fichas_al_siguiente():
    salida = [_clip("00", 6), _clip("01", 6, nuevas=["Tabla"]), _clip("02", 6, nuevas=["Botón", "Menú"]), _clip("03", 6)]
    montaje.encajar(salida, {}, 16_000)
    nns = [e["nn"] for e in salida]
    assert "01" not in nns   # el que menos traía
    siguiente = salida[nns.index("02")]
    assert "Tabla" in siguiente["nuevas"] and {"0:01", "0:02"} <= {f["key"] for f in siguiente["fichas"]}


def test_la_demo_del_final_no_se_quita():
    salida = [_clip(f"{i:02d}", 6) for i in range(6)] + [_clip("demo", 20, demo=1)]
    montaje.encajar(salida, {}, 25_000)
    assert salida[-1]["nn"] == "demo"


def test_datos_con_formato_y_lienzo(tmp_path):
    datos = montaje.preparar(tmp_path / "v", "demo", "estatico", [], {"rotulos": {}}, (), "diario", "vertical")
    assert (datos["formato"], datos["ancho"], datos["alto"]) == ("vertical", 1080, 1920)
    html = (tmp_path / "v" / "reproductor.html").read_text(encoding="utf-8")
    assert "html.vertical" in html and "h.vel || 1" in html


def test_opciones(tmp_path):
    args = _argumentos([str(tmp_path), "--duration", "60", "--format", "portrait"])
    assert (args.duracion, args.formato) == (60, "vertical")
    assert _argumentos([str(tmp_path)]).formato == "horizontal"
    with pytest.raises(SystemExit):
        _argumentos([str(tmp_path), "--format", "vertical", "--look", "classic"])
    with pytest.raises(SystemExit):
        _argumentos([str(tmp_path), "--duration", "-3"])
