import pytest

from cronica import montaje
from cronica.cli import _argumentos


def _preparar(video, estetica):
    return montaje.preparar(video, "demo", "estatico", [], {"rotulos": {}}, (), estetica)


def test_cada_estetica_deja_su_reproductor_y_las_letras(tmp_path):
    _preparar(tmp_path / "a", "diario")
    assert "fecha_larga" in (tmp_path / "a" / "reproductor.html").read_text(encoding="utf-8")
    assert (tmp_path / "a" / "fonts" / "Newsreader.ttf").is_file()
    _preparar(tmp_path / "b", "clasica")
    html = (tmp_path / "b" / "reproductor.html").read_text(encoding="utf-8")
    assert "noticiario" not in html and "window.seek = seek" in html


def test_un_reproductor_propio(tmp_path):
    propio = tmp_path / "mio.html"
    propio.write_text("<script>window.seek = () => {}</script>", encoding="utf-8")
    _preparar(tmp_path / "v", str(propio))
    assert (tmp_path / "v" / "reproductor.html").read_text(encoding="utf-8") == propio.read_text(encoding="utf-8")


def test_estetica_que_no_existe(tmp_path):
    assert _argumentos([str(tmp_path)]).estetica == "diario"
    with pytest.raises(SystemExit):
        _argumentos([str(tmp_path), "--estetica", "periodico"])
