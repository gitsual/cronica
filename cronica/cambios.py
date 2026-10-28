"""Qué cambia a la vista entre un hito y lo que se enseñó antes: fichas nuevas y fichas que se ven distinto."""
from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageChops
except ImportError:  # sin Pillow se compara byte a byte (más estricto: cualquier píxel cuenta)
    Image = None

UMBRAL_PIXELES = 60      # píxeles que tienen que cambiar: una palabra cambiada ya pasa; Chromium pinta igual
                         # dos veces lo mismo, así que no hay ruido que filtrar
UMBRAL_TONO = 24         # diferencia por canal (0-255) para contar un píxel como cambiado


def distinta(a: Path, b: Path) -> bool:
    if Image is None:
        return a.read_bytes() != b.read_bytes()
    with Image.open(a) as ia, Image.open(b) as ib:
        if ia.size != ib.size:
            return True
        dif = ImageChops.difference(ia.convert("RGB"), ib.convert("RGB")).convert("L")
        if not dif.getbbox():
            return False
        hist = dif.histogram()
        cambiados = sum(hist[UMBRAL_TONO:])
        return cambiados > UMBRAL_PIXELES


def comparar(previas: dict[str, Path], fichas: list[dict], carpeta: Path) -> tuple[list[str], list[str]]:
    """(claves nuevas, claves que se ven distinto), comparando la foto clara de cada ficha."""
    nuevas, cambiadas = [], []
    for f in fichas:
        actual = carpeta / f["light"]["file"]
        antes = previas.get(f["key"])
        if antes is None:
            nuevas.append(f["key"])
        elif not antes.exists() or distinta(antes, actual):
            cambiadas.append(f["key"])
    return nuevas, cambiadas
