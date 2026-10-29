"""Dibuja el icono de cronica.exe: el sello rojo con la C de la cabecera, ligeramente girado.

Uso: python assets/icono.py  ->  assets/cronica.ico y assets/cronica.png
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

AQUI = Path(__file__).parent
GOTICA = AQUI.parent / "cronica" / "reproductor" / "fonts" / "UnifrakturMaguntia.ttf"
SELLO, PAPEL = (179, 48, 28, 255), (237, 230, 214, 255)


def sello(lado: int = 1024) -> Image.Image:
    im = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    m = lado * .04
    d.ellipse([m, m, lado - m, lado - m], fill=PAPEL)
    d.ellipse([m, m, lado - m, lado - m], outline=SELLO, width=round(lado * .075))
    i = lado * .17
    d.ellipse([i, i, lado - i, lado - i], outline=SELLO, width=round(lado * .018))
    letra = ImageFont.truetype(str(GOTICA), round(lado * .62))
    d.text((lado / 2, lado * .53), "C", font=letra, fill=SELLO, anchor="mm")
    return im.rotate(9, resample=Image.BICUBIC)


if __name__ == "__main__":
    im = sello()
    im.resize((256, 256), Image.LANCZOS).save(AQUI / "cronica.png")
    im.save(AQUI / "cronica.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(AQUI / "cronica.ico")
