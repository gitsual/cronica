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
    repo.pr(3, "errata", "Arregla una errata", {"contacto.html": pagina("Contacto", cuerpo="Escríbenos")})
    repo.commit("Actualiza el README", {"README.md": "Sin cambios en la interfaz"})
    salida = tmp_path / "video.mp4"

    assert main([str(repo.raiz), "-o", str(salida), "--segundos", "2", "--fps", "6"]) == 0

    trabajo = next((tmp_path / "cache").iterdir())
    datos = json.loads((trabajo / "video" / "datos.json").read_text(encoding="utf-8"))
    assert [h["rotulo"] for h in datos["hitos"]] == ["Primera página", "Página de contacto", "Tabla de precios",
                                                     "Arregla una errata"]
    assert [h["cifras"]["pantallas"] for h in datos["hitos"]] == [1, 2, 3, 3]
    assert datos["hitos"][1]["chip"].startswith("#1 · ")
    # Cada escena dice qué entra o qué cambia, y lleva su clip de la app en uso.
    assert datos["hitos"][1]["nuevas"] == ["contacto.html"]
    assert datos["hitos"][3]["nuevas"] == [] and datos["hitos"][3]["cambiadas"] == ["contacto.html"]
    assert all(h["fotogramas"] >= 20 for h in datos["hitos"])
    clip = trabajo / "hitos" / datos["hitos"][1]["clip"].split("/")[2] / "clip"
    assert len(list(clip.glob("*.jpg"))) == datos["hitos"][1]["fotogramas"]
    # El modo oscuro de la página se fotografía aparte.
    assert datos["hitos"][0]["fichas"][0].get("dark")

    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(salida)],
                         capture_output=True, text=True).stdout
    esperada = (datos["intro"] + sum(h["dur"] for h in datos["hitos"]) + datos["outro"]) / 1000
    assert abs(float(dur) - esperada) < 0.6
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1",
                              str(salida)], capture_output=True, text=True).stdout.split()
    assert streams == ["video", "audio"]

    # Los rótulos se pueden editar y el segundo pase sale entero de la caché.
    rot = json.loads((trabajo / "rotulos.json").read_text(encoding="utf-8"))
    rot["rotulos"][datos["hitos"][2]["sha"]] = "Llegan los precios"
    (trabajo / "rotulos.json").write_text(json.dumps(rot), encoding="utf-8")
    assert main([str(repo.raiz), "-o", str(salida), "--segundos", "2", "--fps", "6", "--sin-musica", "--previa"]) == 0
    datos = json.loads((trabajo / "video" / "datos.json").read_text(encoding="utf-8"))
    assert datos["hitos"][2]["rotulo"] == "Llegan los precios"
    assert len(list((trabajo / "previa").glob("*.png"))) == 6


def test_sin_interfaz(repo, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CRONICA_CACHE", str(tmp_path / "cache"))
    repo.commit("lib", {"lib.py": "x = 1\n"})
    assert main([str(repo.raiz)]) == 3
    assert "solo hace vídeos de proyectos con interfaz" in capsys.readouterr().out


def test_no_es_repo(tmp_path, monkeypatch):
    # Que git no suba a buscar un repositorio por encima (en algunos equipos la carpeta temporal está dentro de uno).
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert main([str(tmp_path)]) == 2


def test_extraccion_a_otro_repositorio(tmp_path, monkeypatch):
    """Un proyecto que se muda: escena de extracción entre los dos y el primer hito del nuevo siempre sale."""
    from tests.conftest import Repo
    monkeypatch.setenv("CRONICA_CACHE", str(tmp_path / "cache"))
    viejo = Repo(tmp_path / "viejo")
    viejo.commit("Primera página", {"index.html": pagina("Mi app"), "README.md": "viejo\n"})
    viejo.commit("Contacto", {"index.html": pagina("Mi app", ["contacto.html"]), "contacto.html": pagina("Contacto")})
    nuevo = Repo(tmp_path / "nuevo")
    nuevo.commit("Importa la web del repositorio viejo", {"index.html": pagina("Mi app", ["contacto.html"]),
                                                          "contacto.html": pagina("Contacto")})
    nuevo.commit("Precios", {"index.html": pagina("Mi app", ["contacto.html", "precios.html"]),
                             "precios.html": pagina("Precios")})

    assert main([str(viejo.raiz), str(nuevo.raiz), "--segundos", "2", "--sin-musica", "--previa"]) == 0

    trabajo = next(d for d in (tmp_path / "cache").iterdir() if "+" in d.name)
    datos = json.loads((trabajo / "video" / "datos.json").read_text(encoding="utf-8"))
    tipos = [h.get("tipo", "hito") for h in datos["hitos"]]
    assert tipos == ["hito", "hito", "extraccion", "hito", "hito"]
    ext = datos["hitos"][2]
    assert (ext["de"], ext["a"], ext["ficheros"], ext["ficheros_b"]) == ("viejo", "nuevo", 2, 2)
    assert ext["rotulo"] == "Extracción: la interfaz se muda a nuevo"
    # El primer hito del nuevo no cambia nada a la vista, pero sale: es el resultado de la mudanza.
    assert datos["hitos"][3]["fotogramas"] > 0 and datos["hitos"][3]["barra"].endswith("nuevo")
    assert len(list((trabajo / "previa").glob("*.png"))) == 7
