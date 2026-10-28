"""Música de fondo generada: un pad ambiental que cambia de acorde con cada hito.

No usa muestras ni ficheros externos (nada con derechos): senos, una línea de bajo y un arpegio suave,
con eco y fundidos. Si se pasa --musica, se usa ese fichero en su lugar.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
# Progresión en La menor (semitonos desde La 220 Hz): Am9, Fmaj7, C(add9), G6, Dm9, Em7.
ACORDES = [(0, 3, 7, 10, 14), (-4, 0, 3, 7, 11), (3, 7, 10, 14, 15), (-2, 2, 5, 7, 10), (5, 8, 12, 15, 19), (7, 10, 14, 17, 19)]
ORDEN = [0, 1, 2, 3, 0, 1, 4, 5]


def _hz(semitonos: float, base: float = 220.0) -> float:
    return base * 2 ** (semitonos / 12)


def _envolvente(n: int, ataque: float, caida: float) -> np.ndarray:
    e = np.ones(n)
    a, c = min(int(ataque * SR), n // 2), min(int(caida * SR), n // 2)
    if a:
        e[:a] = np.linspace(0, 1, a) ** 2
    if c:
        e[-c:] = np.linspace(1, 0, c) ** 1.5
    return e


def generar(destino: Path, duracion_s: float, inicio_s: float, por_hito_s: float) -> Path:
    n = int(duracion_s * SR)
    izq, der = np.zeros(n), np.zeros(n)
    # Los acordes empiezan con la primera escena; la intro lleva el primero.
    cortes = [0.0] + [inicio_s + k * por_hito_s for k in range(1, int((duracion_s - inicio_s) / por_hito_s) + 1)]
    cortes.append(duracion_s)
    for k in range(len(cortes) - 1):
        a, b = int(cortes[k] * SR), min(n, int(cortes[k + 1] * SR) + int(1.2 * SR))
        if b <= a:
            continue
        t = np.arange(b - a) / SR
        acorde = ACORDES[ORDEN[k % len(ORDEN)]]
        env = _envolvente(b - a, 0.9, 1.4)
        pad_i, pad_d = np.zeros(b - a), np.zeros(b - a)
        for j, s in enumerate(acorde):
            f = _hz(s)
            lfo = 1 + 0.12 * np.sin(2 * np.pi * (0.18 + 0.05 * j) * t + j)
            pad_i += lfo * (np.sin(2 * np.pi * f * 0.998 * t) + 0.18 * np.sin(4 * np.pi * f * t))
            pad_d += lfo * (np.sin(2 * np.pi * f * 1.002 * t + 0.7) + 0.18 * np.sin(4 * np.pi * f * t + 0.3))
        bajo = 0.9 * np.sin(2 * np.pi * _hz(acorde[0], 55.0) * t) * _envolvente(b - a, 0.3, 1.0)
        # Arpegio de corcheas (≈ 100 bpm) que sube y baja por el acorde, con caída rápida.
        arp = np.zeros(b - a)
        paso = int(0.3 * SR)
        notas = list(acorde) + list(acorde[-2:0:-1])
        for m, p in enumerate(range(int(0.15 * SR), b - a, paso)):
            f = _hz(notas[m % len(notas)] + 12)
            largo = min(int(1.1 * SR), b - a - p)
            tt = np.arange(largo) / SR
            arp[p:p + largo] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 5.5) * (0.55 + 0.45 * (m % 2 == 0))
        izq[a:b] += env * (0.11 * pad_i + 0.10 * bajo + 0.07 * arp)
        der[a:b] += env * (0.11 * pad_d + 0.10 * bajo + 0.07 * np.roll(arp, int(0.012 * SR)))
    # Eco: dos reflexiones cruzadas entre canales.
    for retardo, g in ((0.37, 0.32), (0.61, 0.2), (0.93, 0.12)):
        d = int(retardo * SR)
        izq[d:] += g * der[:-d]
        der[d:] += g * izq[:-d]
    final = _envolvente(n, 1.5, 3.5)
    estereo = np.stack([izq * final, der * final], axis=1)
    estereo *= 0.5 / max(1e-9, np.abs(estereo).max())
    destino.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((estereo * 32767).astype("<i2").tobytes())
    return destino
