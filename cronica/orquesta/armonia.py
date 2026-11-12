"""La armonía: acordes extendidos, voces que se mueven lo mínimo y una contramelodía de notas guía.

- Los acordes se escriben con su cifrado (Fmaj9, Gm9, C13sus4, C7b9, Bbm6/9…) y se tocan sin fundamental, a lo
  jazz: las dos notas guía (tercera y séptima, o sexta) más dos colores (novena, trecena, oncena…).
- conducir() elige, de todas las disposiciones posibles, la cadena que menos se mueve de un acorde al siguiente
  (programación dinámica con la suma de distancias, como en Tymoczko, «The Geometry of Musical Chords», 2006).
- guias() saca una nota guía por compás, la más cercana a la anterior y en sentido contrario a la melodía.
"""
from __future__ import annotations

import itertools

import numpy as np

PC = {"C": 0, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}
# cualidad -> (intervalos guía, intervalos de color, quinta)
CUALIDADES = {
    "maj9": ((4, 11), (14,), 7), "m9": ((3, 10), (14,), 7), "9sus4": ((5, 10), (14,), 7),
    "13sus4": ((5, 10), (14, 21), 7), "7b9": ((4, 10), (13,), 7), "13": ((4, 10), (21, 14), 7),
    "m7": ((3, 10), (), 7), "maj7#11": ((4, 11), (18,), 7), "m6/9": ((3, 9), (14,), 7), "6/9": ((4, 9), (14,), 7),
    "7(13)": ((4, 10), (21,), 7), "m7b5": ((3, 10), (), 6),
}


def acorde(simbolo: str) -> tuple[int, list[int], list[int]]:
    """'Fmaj9' -> (clase de la fundamental, clases guía, clases de color)."""
    raiz = simbolo[:2] if simbolo[1:2] in ("b", "#") else simbolo[:1]
    guia_, color, quinta = CUALIDADES[simbolo[len(raiz):]]
    r = PC[raiz]
    return r, [(r + i) % 12 for i in guia_], [(r + i) % 12 for i in color] + [(r + quinta) % 12]


def disposiciones(simbolo: str, grave: int = 55, agudo: int = 76) -> list[tuple[int, ...]]:
    """Las disposiciones de cuatro notas sin fundamental que caben en el registro medio y suenan limpias."""
    _r, guia_, color = acorde(simbolo)
    candidatas = set()
    for extra in itertools.combinations(color, 2) if len(color) >= 2 else [tuple(color) * 2]:
        clases = list(guia_) + list(extra)
        alturas = [[p for p in range(grave, agudo + 1) if p % 12 == c] for c in clases]
        for combo in itertools.product(*alturas):
            v = tuple(sorted(combo))
            # Cuatro notas distintas, en menos de una novena, sin segunda menor arriba ni notas pegadas abajo.
            if len(set(v)) == 4 and v[-1] - v[0] <= 14 and v[-1] - v[-2] != 1 and v[1] - v[0] >= 2:
                candidatas.add(v)
    return sorted(candidatas)


def conducir(simbolos: list[str], centro: int = 66) -> list[tuple[int, ...]]:
    """La cadena de disposiciones que menos se mueve, sin alejarse del centro del registro."""
    capas = [disposiciones(s) for s in simbolos]
    coste = [{v: abs(np.mean(v) - centro) * 0.6 for v in capas[0]}]
    previo: list[dict] = [{}]
    for k in range(1, len(capas)):
        c, p = {}, {}
        for v in capas[k]:
            mejor = min(capas[k - 1], key=lambda u: coste[-1][u] + sum(abs(a - b) for a, b in zip(u, v)))
            c[v] = coste[-1][mejor] + sum(abs(a - b) for a, b in zip(mejor, v)) + abs(np.mean(v) - centro) * 0.3
            p[v] = mejor
        coste.append(c)
        previo.append(p)
    v = min(coste[-1], key=coste[-1].get)
    camino = [v]
    for k in range(len(capas) - 1, 0, -1):
        v = previo[k][v]
        camino.append(v)
    return camino[::-1]


def guias(simbolos: list[str], melodias: list[list], inicio: int = 64) -> list[int]:
    """Una nota guía por compás: la más cercana a la anterior, mejor si va en contra de la melodía."""
    linea, previa = [], inicio
    for s, mel in zip(simbolos, melodias):
        _r, guia_, _c = acorde(s)
        sube = len(mel) > 1 and mel[-1][1] > mel[0][1]

        def coste(p: int) -> float:
            mov = p - previa
            contrario = (mov < 0) if sube else (mov > 0)
            return abs(mov) - (1.5 if contrario and mov else 0) + (3 if mov == 0 else 0)

        previa = min((p for p in range(56, 72) if p % 12 in guia_), key=coste)
        linea.append(previa)
    return linea
