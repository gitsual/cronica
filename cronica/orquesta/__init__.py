"""La orquesta de cronica: un sampler con instrumentos grabados de verdad.

Las muestras están en banco.ogg (todas seguidas) y banco.json (dónde empieza cada una, su nota y su bucle). Salen de
VSCO-2 Community Edition (CC0) y de FluidR3_GM (MIT); herramientas/banco_muestras.py las rehace desde sus fuentes.
El banco se descodifica una vez con ffmpeg, que cronica ya necesita para el vídeo.
"""
from __future__ import annotations

import functools
import json
import subprocess
import wave
from importlib import resources
from pathlib import Path

import numpy as np

SR = 44100


@functools.lru_cache(maxsize=1)
def banco(ffmpeg: str = "ffmpeg") -> tuple[dict, np.ndarray]:
    """(índice, todas las muestras en un solo array mono float32)."""
    carpeta = resources.files("cronica").joinpath("orquesta")
    indice = json.loads(carpeta.joinpath("banco.json").read_text(encoding="utf-8"))
    with resources.as_file(carpeta.joinpath("banco.ogg")) as ogg:
        crudo = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(ogg), "-f", "s16le", "-ac", "1",
                                "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return indice, np.frombuffer(crudo, "<i2").astype(np.float32) / 32768


def golpe(nombre: str, ffmpeg: str = "ffmpeg") -> np.ndarray:
    """Una muestra de percusión (batería o percusión) por su nombre: bombo, aro, charles, claves…"""
    indice, todo = banco(ffmpeg)
    for grupo in ("bateria", "percusion"):
        for e in indice["instrumentos"].get(grupo, []):
            if e.get("nombre") == nombre:
                return todo[e["inicio"]:e["inicio"] + e["largo"]]
    raise KeyError(nombre)


class Instrumento:
    """Un instrumento afinado: toca cualquier nota con la muestra más cercana, alargándola con su bucle."""

    def __init__(self, nombre: str, ataque: float = 0.003, suelta: float = 0.25, gan: float = 1.0,
                 ffmpeg: str = "ffmpeg"):
        indice, todo = banco(ffmpeg)
        self.muestras = []
        for e in indice["instrumentos"][nombre]:
            y = todo[e["inicio"]:e["inicio"] + e["largo"]]
            bucle = e.get("bucle")
            if bucle and bucle[1] - bucle[0] > 2000 and bucle[1] <= len(y):
                # Fundido cruzado en el empalme: el final del bucle se mezcla con lo de antes de su inicio.
                a, b = bucle
                xf = min(2000, a, (b - a) // 2)
                k = np.linspace(0, 1, xf, dtype=np.float32)
                y = y.copy()
                y[b - xf:b] = y[b - xf:b] * (1 - k) + y[a - xf:a] * k
            else:
                bucle = None
            self.muestras.append((e["raiz"] + e.get("cents", 0) / 100, y, bucle))
        self.ataque, self.suelta, self.gan = ataque, suelta, gan

    def nota(self, midi: float, dur: float, vel: float = 0.8) -> np.ndarray:
        raiz, y, bucle = min(self.muestras, key=lambda m: abs(m[0] - midi))
        pos = np.arange(int((dur + self.suelta) * SR)) * 2 ** ((midi - raiz) / 12)
        if bucle:
            a, b = bucle
            fuera = pos >= b
            pos[fuera] = a + (pos[fuera] - a) % (b - a)
        pos = pos[pos < len(y) - 1]
        i = pos.astype(int)
        f = pos - i
        voz = y[i] * (1 - f) + y[i + 1] * f
        env = np.ones(len(voz))
        a = min(len(env), max(1, int(self.ataque * SR)))
        env[:a] = np.linspace(0, 1, a)
        corte = int(dur * SR)
        if corte < len(env):
            env[corte:] = np.linspace(1, 0, len(env) - corte) ** 2
        return voz * env * vel * self.gan


class Mezcla:
    """El estéreo donde se ponen las notas, con un poco de humanidad (tiempo e intensidad) y una sala."""

    def __init__(self, segundos: float, semilla: int = 7):
        self.n = int(segundos * SR)
        self.izq, self.der = np.zeros(self.n), np.zeros(self.n)
        self.rng = np.random.default_rng(semilla)

    def poner(self, t: float, x: np.ndarray, gan: float = 1.0, pan: float = 0.0, humano: float = 0.006) -> None:
        if humano:
            t += self.rng.normal(0, humano)
        gan *= 1 + self.rng.normal(0, 0.06)
        a = int(max(0.0, t) * SR)
        if a >= self.n:
            return
        x = x[: self.n - a] * gan
        self.izq[a:a + len(x)] += x * np.sqrt((1 - pan) / 2)
        self.der[a:a + len(x)] += x * np.sqrt((1 + pan) / 2)

    def sala(self, rt60: float, mezcla: float, brillo: float = 5000) -> None:
        """Reverb por convolución con una sala sintética: ruido que se apaga, distinto en cada canal."""
        largo = int(rt60 * 1.2 * SR)
        t = np.arange(largo) / SR
        caida = np.exp(-6.9 * t / rt60)
        salida = []
        for canal, semilla in ((self.izq, 1), (self.der, 2)):
            ir = np.random.default_rng(semilla).standard_normal(largo) * caida
            ir[:int(0.018 * SR)] = 0
            f = np.fft.rfftfreq(largo, 1 / SR)
            ir = np.fft.irfft(np.fft.rfft(ir) / np.sqrt(1 + (f / brillo) ** 2), largo)
            ir /= np.sqrt((ir ** 2).sum())
            m = 1 << int(np.ceil(np.log2(self.n + largo)))
            mojado = np.fft.irfft(np.fft.rfft(canal, m) * np.fft.rfft(ir, m), m)[: self.n]
            salida.append(canal * (1 - mezcla) + mojado * mezcla * 2.2)
        self.izq, self.der = salida


def leer_wav(f: Path) -> np.ndarray:
    with wave.open(str(f)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
