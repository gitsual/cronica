"""Rehace cronica/orquesta/banco.ogg + banco.json, las muestras con las que suena la música de cronica.

De dónde sale cada sonido (todo se puede redistribuir):

- VSCO-2 Community Edition, de Versilian Studios (CC0): arpa, contrabajo y violines en pizzicato, violines y
  chelos sostenidos, fagot, clarinete, flauta, oboe, glockenspiel, claves y maraca.
  https://github.com/sgossner/VSCO-2-CE
- FluidR3_GM, de Frank Wen (licencia MIT; el .sf2 sale del paquete fluid-soundfont-gm de Debian): acordeón,
  caja de música, celesta, vibráfono, piano eléctrico, guitarra de nailon, contrabajo, cuerdas y la batería.

Cada muestra se pasa a mono a 44,1 kHz, se recorta al ataque y se le detecta la nota (los nombres de los ficheros
usan convenciones de octava distintas). Todas van seguidas en un solo Ogg Vorbis, con su posición en banco.json.

Necesita (solo para rehacerlo; cronica no los usa): pip install librosa soundfile  ·  y ffmpeg en el PATH.

    python herramientas/banco_muestras.py [carpeta de trabajo]
"""
from __future__ import annotations

import concurrent.futures as cf
import io
import json
import lzma
import re
import struct
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

SR = 44100
RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "cronica" / "orquesta"
TRABAJO = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / ".banco-trabajo"
VSCO = "https://raw.githubusercontent.com/sgossner/VSCO-2-CE/master/"
DEB = "https://deb.debian.org/debian/pool/main/f/fluid-soundfont/fluid-soundfont-gm_3.1-5.3_all.deb"

# VSCO: carpeta -> (instrumento, la capa que se queda de cada nota, segundos como mucho, sostenido)
DE_VSCO = {
    "Strings/Harp/": ("arpa", r"_mf\.wav$", 4.0, False),
    "Strings/Solo Contrabass/Pizz/": ("contrabajo_pizz", r"_v3_rr1\.wav$", 1.6, False),
    "Strings/Violin Section/Pizz/": ("violines_pizz", r"_v2_rr1\.wav$", 1.0, False),
    "Strings/Violin Section/susVib/": ("violines", r"_v1\.wav$", 6.0, True),
    "Strings/Cello Section/susvib/": ("chelos", r"_v1_1\.wav$", 6.0, True),
    "Woodwinds/Bassoon/stac/": ("fagot_stac", r"_v2_rr1\.wav$", 0.7, False),
    "Woodwinds/Clarinet/susLong/": ("clarinete", r"_v2_rr1_sum\.wav$", 5.0, True),
    "Woodwinds/Clarinet/stac/": ("clarinete_stac", r"_v2_rr1_sum\.wav$", 0.6, False),
    "Woodwinds/Flute/susvib/": ("flauta", r"_v1_1\.wav$", 5.0, True),
    "Woodwinds/Oboe/Vib/": ("oboe", r"_v1_Main\.wav$", 5.0, True),
    "Percussion/Glock/": ("glock", r"glock_medium_.*\.wav$", 3.0, False),
}
PERCUSION_VSCO = {"claves": "VSCO 1 Percussion/varWood/claves_mf.wav",
                  "maraca": "VSCO 1 Percussion/varWood/Camo's Shaker/shake1.wav"}
# FluidR3: presets General MIDI (banco 0) y teclas de la batería (banco 128).
DE_FLUID = {"acordeon": 21, "caja_musica": 10, "celesta": 8, "vibrafono": 11, "rhodes": 4, "guitarra_nylon": 24,
            "bajo_acustico": 32, "cuerdas_lentas": 49}
BATERIA = {"bombo": 36, "aro": 37, "charles": 42, "campana_ride": 53, "triangulo": 81, "shaker": 82}
NOTAS = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}


def bajar(url: str, fichero: Path) -> Path:
    if not fichero.exists():
        fichero.parent.mkdir(parents=True, exist_ok=True)
        fichero.write_bytes(urllib.request.urlopen(url, timeout=300).read())
    return fichero


def a_mono(y: np.ndarray, sr: int) -> np.ndarray:
    y = y.mean(axis=1) if y.ndim == 2 else y
    return librosa.resample(y, orig_sr=sr, target_sr=SR) if sr != SR else y


def recortar(y: np.ndarray, segundos: float) -> np.ndarray:
    ini = max(0, int(np.argmax(np.abs(y) > np.abs(y).max() * 0.06)) - int(0.004 * SR))
    return y[ini:ini + int(segundos * SR)]


def nota_detectada(y: np.ndarray, nombre_midi: int) -> int:
    """La octava del nombre corregida con la altura medida (cada instrumento numera las octavas a su manera)."""
    trozo = y[int(0.05 * SR):int(0.6 * SR)] if len(y) > int(0.6 * SR) else y
    f0 = librosa.yin(trozo, fmin=30, fmax=4200, sr=SR, frame_length=4096)
    medida = librosa.hz_to_midi(np.median(f0[np.isfinite(f0)]))
    return min((nombre_midi + 12 * k for k in (-2, -1, 0, 1, 2)), key=lambda x: abs(x - medida))


def de_vsco() -> dict[str, list]:
    lista = json.loads(urllib.request.urlopen(
        "https://api.github.com/repos/sgossner/VSCO-2-CE/git/trees/master?recursive=1", timeout=120).read())
    rutas = [t["path"] for t in lista["tree"] if t["type"] == "blob"]
    trabajos = []
    for carpeta, (inst, regla, _s, _sos) in DE_VSCO.items():
        for r in rutas:
            if r.startswith(carpeta) and "/" not in r[len(carpeta):] and re.search(regla, r):
                trabajos.append((inst, r))
    with cf.ThreadPoolExecutor(12) as ex:
        list(ex.map(lambda t: bajar(VSCO + urllib.parse.quote(t[1]), TRABAJO / "vsco" / t[1]), trabajos))
    salida: dict[str, list] = {}
    for inst, r in trabajos:
        carpeta = next(c for c, v in DE_VSCO.items() if v[0] == inst)
        _i, _r, segundos, sostenido = DE_VSCO[carpeta]
        y, sr = sf.read(TRABAJO / "vsco" / r, always_2d=True)
        y = recortar(a_mono(y, sr), segundos)
        m = re.search(r"_([A-G]#?)(-?\d)(?:_|\.wav$)", Path(r).name)
        raiz = nota_detectada(y, (int(m[2]) + 1) * 12 + NOTAS[m[1]])
        bucle = [int(1.2 * SR), len(y) - int(0.5 * SR)] if sostenido and len(y) > int(2.5 * SR) else None
        salida.setdefault(inst, []).append({"raiz": int(raiz), "y": y, "bucle": bucle})
    salida["percusion"] = []
    for nombre, r in PERCUSION_VSCO.items():
        f = bajar(VSCO + urllib.parse.quote(r), TRABAJO / "vsco" / r)
        y, sr = sf.read(f, always_2d=True)
        salida["percusion"].append({"nombre": nombre, "y": recortar(a_mono(y, sr), 1.5)})
    return salida


def de_fluid() -> dict[str, list]:
    sf2 = TRABAJO / "FluidR3_GM.sf2"
    if not sf2.exists():
        datos = bajar(DEB, TRABAJO / "fluid.deb").read_bytes()
        i = 8
        while i < len(datos):
            nombre, tam = datos[i:i + 16].decode().strip(), int(datos[i + 48:i + 58].decode().strip())
            if nombre.startswith("data.tar"):
                crudo = datos[i + 60:i + 60 + tam]
                with tarfile.open(fileobj=io.BytesIO(lzma.decompress(crudo) if nombre.endswith(".xz") else crudo)) as t:
                    sf2.write_bytes(next(t.extractfile(m) for m in t.getmembers() if m.name.endswith("FluidR3_GM.sf2")).read())
            i += 60 + tam + (tam % 2)
    b = sf2.read_bytes()

    def trozos(off, fin):
        while off < fin:
            tam = struct.unpack("<I", b[off + 4:off + 8])[0]
            yield b[off:off + 4], off + 8, tam
            off += 8 + tam + (tam % 2)

    smpl, pdta = None, {}
    for cid, off, tam in trozos(12, len(b)):
        if cid == b"LIST":
            for c2, o2, t2 in trozos(off + 4, off + tam):
                if b[off:off + 4] == b"sdta" and c2 == b"smpl":
                    smpl = o2
                if b[off:off + 4] == b"pdta":
                    pdta[c2.decode()] = (o2, t2)

    def tabla(n, t):
        o, total = pdta[n]
        return [b[o + k:o + k + t] for k in range(0, total, t)]

    phdr = [struct.unpack("<HHH", r[20:26]) for r in tabla("phdr", 38)]
    pbag = [struct.unpack("<HH", r) for r in tabla("pbag", 4)]
    pgen = [struct.unpack("<HH", r) for r in tabla("pgen", 4)]
    inst = [struct.unpack("<H", r[20:22])[0] for r in tabla("inst", 22)]
    ibag = [struct.unpack("<HH", r) for r in tabla("ibag", 4)]
    igen = [struct.unpack("<HH", r) for r in tabla("igen", 4)]
    shdr = [(*struct.unpack("<IIIII", r[20:40]), r[40], struct.unpack("<b", r[41:42])[0],
             r[:20].split(b"\0")[0].decode("latin1")) for r in tabla("shdr", 46)]

    def zonas(programa, banco):
        k = next(i for i, p in enumerate(phdr[:-1]) if p[0] == programa and p[1] == banco)
        for bag in range(phdr[k][2], phdr[k + 1][2]):
            for g in range(pbag[bag][0], pbag[bag + 1][0]):
                if pgen[g][0] == 41:
                    v = pgen[g][1]
                    for ib in range(inst[v], inst[v + 1]):
                        rango, sid, raiz = (0, 127), None, None
                        for ig in range(ibag[ib][0], ibag[ib + 1][0]):
                            op, val = igen[ig]
                            rango = (val & 0xFF, val >> 8) if op == 43 else rango
                            raiz = val if op == 58 else raiz
                            sid = val if op == 53 else sid
                        if sid is not None:
                            yield rango, sid, raiz

    def muestra(sid):
        ini, fin, lini, lfin, sr, tono, cents, _n = shdr[sid]
        y = np.frombuffer(b[smpl + 2 * ini:smpl + 2 * fin], "<i2").astype(np.float32) / 32768
        k = SR / sr
        bucle = [int((lini - ini) * k), int((lfin - ini) * k)] if lfin - lini > 64 else None
        return a_mono(y, sr), tono, cents, bucle

    salida: dict[str, list] = {}
    for nombre, prog in DE_FLUID.items():
        vistas = set()
        for _rango, sid, raiz_forzada in zonas(prog, 0):
            y, tono, cents, bucle = muestra(sid)
            raiz = raiz_forzada if raiz_forzada is not None and raiz_forzada < 128 else tono
            if raiz in vistas or shdr[sid][-1].endswith("R"):
                continue
            vistas.add(raiz)
            salida.setdefault(nombre, []).append({"raiz": int(raiz), "cents": int(cents), "y": y, "bucle": bucle})
    salida["bateria"] = []
    todas = list(zonas(0, 128))
    for nombre, tecla in BATERIA.items():
        sid = next(s for r, s, _x in todas if r[0] <= tecla <= r[1])
        salida["bateria"].append({"nombre": nombre, "y": muestra(sid)[0]})
    return salida


def main() -> None:
    TRABAJO.mkdir(parents=True, exist_ok=True)
    instrumentos = {**de_vsco(), **de_fluid()}
    trozos, indice, pos = [], {}, 0
    hueco = np.zeros(int(0.02 * SR), np.float32)
    for inst, muestras in sorted(instrumentos.items()):
        for mu in sorted(muestras, key=lambda x: x.get("raiz", 0)):
            y = (mu["y"] / max(1e-9, np.abs(mu["y"]).max()) * 0.9).astype(np.float32)
            entrada = {k: v for k, v in mu.items() if k != "y"} | {"inicio": pos, "largo": len(y)}
            indice.setdefault(inst, []).append(entrada)
            trozos += [y, hueco]
            pos += len(y) + len(hueco)
    crudo = TRABAJO / "banco.wav"
    sf.write(crudo, np.concatenate(trozos), SR, subtype="PCM_16")
    DESTINO.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(crudo), "-c:a", "libvorbis", "-q:a", "6",
                    str(DESTINO / "banco.ogg")], check=True)
    (DESTINO / "banco.json").write_text(json.dumps({"sr": SR, "muestras": pos, "instrumentos": indice}, indent=1),
                                        encoding="utf-8")
    print(f"{sum(len(v) for v in indice.values())} muestras, {pos / SR:.0f} s, "
          f"{(DESTINO / 'banco.ogg').stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
