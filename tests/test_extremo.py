"""De la carpeta al mp4 con un sitio estático de cuatro hitos (necesita Chromium de Playwright y ffmpeg)."""
import json
import shutil
import subprocess

import pytest

from cronica.cli import main
from tests.conftest import pagina

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sin ffmpeg")


def test_de_la_carpeta_al_video(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("CRONICA_CACHE", str(tmp_path / "cache"))
    repo.commit("Primera página", {"index.html": pagina("Mi app")})
    repo.pr(1, "contacto", "Página de contacto", {"index.html": pagina("Mi app", ["contacto.html"]),
                                                   "contacto.html": pagina("Contacto")})
    repo.pr(2, "precios", "Tabla de precios", {"index.html": pagina("Mi app", ["contacto.html", "precios.html"]),
                                                "precios.html": pagina("Precios")})
    repo.commit("Arregla una errata", {"contacto.html": pagina("Contacto", cuerpo="Escríbenos")})
    salida = tmp_path / "video.mp4"

    assert main([str(repo.raiz), "-o", str(salida), "--segundos", "1", "--fps", "6"]) == 0

    trabajo = next((tmp_path / "cache").iterdir())
    datos = json.loads((trabajo / "video" / "datos.json").read_text(encoding="utf-8"))
    assert [h["rotulo"] for h in datos["hitos"]] == ["Primera página", "Página de contacto", "Tabla de precios",
                                                     "Arregla una errata"]
    assert [h["cifras"]["pantallas"] for h in datos["hitos"]] == [1, 2, 3, 3]
    assert datos["hitos"][1]["chip"].startswith("#1 · ")
    # El modo oscuro de la página se fotografía aparte.
    assert datos["hitos"][0]["fichas"][0].get("dark")

    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(salida)],
                         capture_output=True, text=True).stdout
    assert abs(float(dur) - (3.2 + 4 * 1 + 7)) < 0.6
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1",
                              str(salida)], capture_output=True, text=True).stdout.split()
    assert streams == ["video", "audio"]

    # Los rótulos se pueden editar y el segundo pase sale entero de la caché.
    rot = json.loads((trabajo / "rotulos.json").read_text(encoding="utf-8"))
    rot["rotulos"][datos["hitos"][2]["sha"]] = "Llegan los precios"
    (trabajo / "rotulos.json").write_text(json.dumps(rot), encoding="utf-8")
    assert main([str(repo.raiz), "-o", str(salida), "--segundos", "1", "--fps", "6", "--sin-musica", "--previa"]) == 0
    datos = json.loads((trabajo / "video" / "datos.json").read_text(encoding="utf-8"))
    assert datos["hitos"][2]["rotulo"] == "Llegan los precios"
    assert len(list((trabajo / "previa").glob("*.png"))) == 6


def test_sin_interfaz(repo, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CRONICA_CACHE", str(tmp_path / "cache"))
    repo.commit("lib", {"lib.py": "x = 1\n"})
    assert main([str(repo.raiz)]) == 3
    assert "solo hace vídeos de proyectos con interfaz" in capsys.readouterr().out


def test_no_es_repo(tmp_path):
    assert main([str(tmp_path)]) == 2
