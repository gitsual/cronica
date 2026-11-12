import wave

import numpy as np
import pytest

from cronica import musica
from cronica.cli import _argumentos


@pytest.mark.parametrize("estilo", musica.ESTILOS)
def test_cada_estilo_suena_lo_que_dura_el_video(tmp_path, estilo):
    wav = musica.generar(tmp_path / f"{estilo}.wav", 12.0, [3.0, 7.5], estilo)
    with wave.open(str(wav)) as w:
        assert (w.getnchannels(), w.getframerate()) == (2, musica.SR)
        assert abs(w.getnframes() / musica.SR - 12.0) < 0.01
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2") / 32767
    assert 0.02 < np.sqrt((x ** 2).mean()) and np.abs(x).max() < 0.6


def test_estilo_o_fichero(tmp_path):
    assert _argumentos([str(tmp_path)]).musica == "ascensor"
    assert _argumentos([str(tmp_path), "--music", "fable"]).musica == "cuento"
    assert _argumentos([str(tmp_path), "--musica", "noticiario"]).musica == "noticiario"
    pista = tmp_path / "pista.mp3"
    pista.write_bytes(b"")
    assert _argumentos([str(tmp_path), "--musica", str(pista)]).musica == str(pista)
    with pytest.raises(SystemExit):
        _argumentos([str(tmp_path), "--musica", "reguetón"])


def _pista(f, segundos=40.0, bpm=120.0):
    """Una pista de prueba: un acorde distinto cada compás (ciclo de 8) y un golpe en cada pulso."""
    sr, negra = musica.SR, 60 / bpm
    t = np.arange(int(segundos * sr)) / sr
    compas = (t // (4 * negra)).astype(int) % 8
    raiz = np.array([0, 5, 7, 3, 0, 5, 9, 7])[compas]
    x = 0.2 * np.sin(2 * np.pi * 220 * 2 ** (raiz / 12) * t)
    x += 0.3 * np.exp(-((t % negra) * 40)) * np.sin(2 * np.pi * 80 * t)
    with wave.open(str(f), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.repeat(x[:, None], 2, axis=1) * 32767).astype("<i2").tobytes())
    f.with_suffix(".json").write_text('{"negra": 0.5, "uno": 0.0}', encoding="utf-8")
    return f


@pytest.mark.parametrize("segundos", [20.0, 40.0, 95.0])
def test_una_pista_se_ajusta_por_compases(tmp_path, segundos):
    pista = _pista(tmp_path / "bossa.wav")
    wav = musica.ajustar_pista(pista, tmp_path / "salida.wav", segundos, [5.0, 12.0])
    with wave.open(str(wav)) as w:
        assert abs(w.getnframes() / musica.SR - segundos) < 0.01
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2") / 32767
    assert np.abs(np.diff(x[::2])).max() < 0.5   # sin chasquidos en los empalmes


def test_los_saltos_respetan_la_frase():
    croma = np.eye(12)[np.arange(40) % 8]
    vol = np.zeros(40)
    corta = musica._secuencia(40, 22, croma, vol)
    larga = musica._secuencia(40, 90, croma, vol)
    for orden in (corta, larga):
        saltos = [(a, b) for a, b in zip(orden, orden[1:]) if b != a + 1]
        assert saltos and all((b - (a + 1)) % 4 == 0 for a, b in saltos)
        assert orden[:4] == [0, 1, 2, 3] and orden[-4:] == [36, 37, 38, 39]   # la entrada y el final de verdad
    assert 19 <= len(corta) <= 25 and 87 <= len(larga) <= 93


def test_una_pista_instalada_se_elige_por_su_nombre(tmp_path, monkeypatch):
    monkeypatch.setattr(musica, "carpeta_pistas", lambda: tmp_path)
    _pista(tmp_path / "Café Bossa Nova A.wav")
    assert list(musica.pistas()) == ["Café Bossa Nova A"]
    assert _argumentos([str(tmp_path), "--music", "Café Bossa Nova A"]).musica == str(tmp_path / "Café Bossa Nova A.wav")


def test_la_orquesta_toca_cada_pieza(tmp_path):
    for estilo in musica.ORQUESTA:
        wav = musica.generar(tmp_path / f"{estilo}.wav", 8.0, [3.0], estilo)
        with wave.open(str(wav)) as w:
            x = np.frombuffer(w.readframes(w.getnframes()), "<i2") / 32767
        assert 0.02 < np.sqrt((x ** 2).mean())


def test_aleatoria_elige_una_pista_instalada(tmp_path, monkeypatch):
    monkeypatch.setattr(musica, "carpeta_pistas", lambda: tmp_path)
    assert musica.elegir("aleatoria") in musica.ORQUESTA        # sin pistas, la orquesta
    for nombre in ("A", "B"):
        _pista(tmp_path / f"{nombre}.wav")
    elegidas = {musica.elegir("aleatoria", semilla=s) for s in range(20)}
    assert elegidas == {str(tmp_path / "A.wav"), str(tmp_path / "B.wav")}
    assert musica.elegir("vals") == "vals"
    assert _argumentos([str(tmp_path), "--music", "aleatoria"]).musica in elegidas


def test_preparar_deja_la_rejilla_y_el_bucle(tmp_path):
    pista = _pista(tmp_path / "bossa.wav", segundos=60)
    meta = musica.preparar_pista(pista)
    assert meta["negra"] == 0.5 and meta["uno"] == 0.0
    ini, fin = meta["bucle"]
    assert 0 < ini < fin <= 60 and round((fin - ini) / 2) % 4 == 0   # compases enteros, frases de cuatro
