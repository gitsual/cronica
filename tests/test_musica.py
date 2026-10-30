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
    assert _argumentos([str(tmp_path)]).musica == "consola"
    assert _argumentos([str(tmp_path), "--musica", "noticiario"]).musica == "noticiario"
    pista = tmp_path / "pista.mp3"
    pista.write_bytes(b"")
    assert _argumentos([str(tmp_path), "--musica", str(pista)]).musica == str(pista)
    with pytest.raises(SystemExit):
        _argumentos([str(tmp_path), "--musica", "reguetón"])
