"""Música de fondo generada, en cinco estilos (--musica <estilo>):

- taller (por defecto): una canción de taller de inventor, de cuento, a lo Tomohito Nishiura (Dark Chronicle).
  La bemol a 100 bpm: fagot saltando, acordeón musette, clarinete con apoyaturas, glockenspiel y caja china.
- cuento: de noche y con misterio, a lo «The Spirit King» (Dark Cloud). Do menor a 117 bpm: caja de música
  en corcheas, arpa, cuerdas graves en pedal, una flauta y campanas en cada cambio de escena.
- consola: una canción alegre de salón, en la línea de los menús de consola. Do mayor con
  swing a 116 bpm, intro + A A B A en bucle: vibráfono con la melodía, piano eléctrico a contratiempo,
  bajo, percusión suave y un destello muy flojo en cada cambio de escena.
- noticiario: una marcha de noticiario de cine, a juego con la estética del diario. Si bemol a 128 bpm,
  metales con la melodía, tuba y acordes en «um-pa», caja, bombo y platillo al empezar cada parte.
- ambiente: el pad de antes, sin melodía, que cambia de acorde con cada escena.

Todo sale de senos y ruido (nada con derechos). Si se pasa --musica con un fichero, se usa ese.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
ESTILOS = ("taller", "cuento", "consola", "noticiario", "ambiente")


def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _env(n: int, ataque: float, caida: float, suelta: float = 0.06) -> np.ndarray:
    t = np.arange(n) / SR
    e = np.exp(-t * caida)
    a = max(1, min(int(ataque * SR), n))
    e[:a] *= np.linspace(0, 1, a)
    s = min(int(suelta * SR), n)
    if s:
        e[-s:] *= np.linspace(1, 0, s)
    return e


class _Mezcla:
    def __init__(self, n: int):
        self.izq, self.der = np.zeros(n), np.zeros(n)

    def poner(self, t0: float, senal: np.ndarray, gan: float, pan: float = 0.0) -> None:
        a = int(t0 * SR)
        if a >= len(self.izq) or a < 0:
            return
        s = senal[: len(self.izq) - a] * gan
        self.izq[a:a + len(s)] += s * np.sqrt((1 - pan) / 2)
        self.der[a:a + len(s)] += s * np.sqrt((1 + pan) / 2)

    def sala(self, reflexiones: tuple[tuple[float, float], ...]) -> None:
        """Unas reflexiones cruzadas entre canales, para que no suene seco."""
        for retardo, g in reflexiones:
            d = int(retardo * SR)
            self.izq[d:] += g * self.der[:-d]
            self.der[d:] += g * self.izq[:-d]


class _Compas:
    """Dónde cae cada corchea: negra a `bpm` y, con swing, la de contratiempo se retrasa."""

    def __init__(self, bpm: float, swing: float = 0.5):
        self.negra = 60 / bpm
        self.corchea = self.negra / 2
        self.largo = 4 * self.negra
        self.swing = swing

    def corchea_s(self, k: int) -> float:
        return (k // 2) * self.negra + (self.swing * self.negra if k % 2 else 0)


def _bucle(intro: list, forma: list):
    """La intro y luego la forma en bucle, compás a compás."""
    yield from intro
    while True:
        for seccion in forma:
            yield from seccion


# ---------------------------------------------------------------- instrumentos

def _vibrafono(f: float, dur: float) -> np.ndarray:
    n = int((dur + 0.6) * SR)
    t = np.arange(n) / SR
    indice = 1.4 * np.exp(-t * 9)
    voz = np.sin(2 * np.pi * f * t + indice * np.sin(2 * np.pi * f * 4 * t))
    voz += 0.12 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t * 6)
    tremolo = 1 + 0.18 * np.sin(2 * np.pi * 5.2 * t)
    return voz * tremolo * _env(n, 0.004, 2.6, 0.12)


def _piano(f: float, dur: float) -> np.ndarray:
    n = int((dur + 0.15) * SR)
    t = np.arange(n) / SR
    indice = 2.0 * np.exp(-t * 7)
    voz = np.sin(2 * np.pi * f * t + indice * np.sin(2 * np.pi * f * t))
    return voz * _env(n, 0.003, 3.2, 0.08)


def _bajo(f: float, dur: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    voz = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) * np.exp(-t * 8) + 0.1 * np.sin(6 * np.pi * f * t)
    return voz * _env(n, 0.006, 2.2, 0.05)


def _metal(f: float, dur: float, brillo: float = 1.0) -> np.ndarray:
    """Una trompeta de juguete: armónicos que se abren al soplar y un vibrato que llega tarde."""
    n = int((dur + 0.08) * SR)
    t = np.arange(n) / SR
    vibrato = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - 0.15) / 0.2, 0, 1)
    fase = 2 * np.pi * f * np.cumsum(vibrato) / SR
    apertura = 0.75 * brillo * np.clip(t / 0.05, 0, 1)
    voz = sum(np.sin(k * fase) * apertura ** (k - 1) / k for k in range(1, 9))
    return voz * _env(n, 0.02, 0.6, 0.07)


def _ruido(dur: float, caida: float, semilla: int) -> np.ndarray:
    n = int(dur * SR)
    r = np.random.default_rng(semilla).standard_normal(n)
    return np.diff(r, prepend=0) * _env(n, 0.001, caida, 0.01)


def _bombo(dur: float = 0.3) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    fase = 2 * np.pi * np.cumsum(50 + 70 * np.exp(-t * 30)) / SR
    return np.sin(fase) * _env(n, 0.002, 12, 0.02)


def _aro() -> np.ndarray:
    n = int(0.08 * SR)
    t = np.arange(n) / SR
    return (0.6 * np.sin(2 * np.pi * 1750 * t) + 0.5 * _ruido(0.08, 0, 3)[:n]) * _env(n, 0.001, 70, 0.01)


def _caja(semilla: int = 5) -> np.ndarray:
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    cuero = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)
    return (0.5 * cuero + 0.8 * _ruido(0.22, 0, semilla)) * _env(n, 0.001, 16, 0.02)


def _platillo() -> np.ndarray:
    return _ruido(2.2, 1.8, 9) + 0.5 * _ruido(2.2, 4, 10)


def _destello() -> np.ndarray:
    """Tres notas de campanilla que suben (Sol, Do, Mi), para el cambio de escena."""
    largo = int(0.9 * SR)
    s = np.zeros(largo)
    for k, nota in enumerate((91, 96, 100)):
        p = int(k * 0.045 * SR)
        v = _vibrafono(_hz(nota), 0.2)[: largo - p]
        s[p:p + len(v)] += v * (0.8 - 0.15 * k)
    return s


# ---------------------------------------------------------------- consola

# Acordes como (fundamental MIDI, intervalos). La voz del piano se coloca cerca del Do central.
CONSOLA_ACORDES = {
    "C6": (48, (0, 4, 7, 9)), "Cmaj7": (48, (0, 4, 7, 11)), "A7": (45, (0, 4, 7, 10)),
    "Dm7": (50, (0, 3, 7, 10)), "G7": (43, (0, 4, 7, 10)), "Em7": (52, (0, 3, 7, 10)),
    "Fmaj7": (41, (0, 4, 7, 11)), "Fm6": (41, (0, 3, 7, 9)),
}
# Cada sección: 8 compases; cada compás, uno o dos acordes y la melodía como (corchea, nota MIDI, corcheas).
CONSOLA_A = [
    (["Cmaj7"], [(0, 76, 1), (1, 79, 1), (2, 83, 2), (5, 81, 1), (6, 79, 2)]),
    (["A7"], [(0, 76, 1), (1, 73, 1), (2, 76, 2), (4, 79, 3)]),
    (["Dm7"], [(0, 77, 1), (1, 81, 1), (2, 84, 2), (5, 83, 1), (6, 81, 2)]),
    (["G7"], [(0, 79, 1), (1, 77, 1), (2, 74, 2), (4, 71, 2), (6, 74, 2)]),
    (["Em7"], [(0, 79, 1), (1, 83, 1), (2, 86, 2), (5, 84, 1), (6, 83, 2)]),
    (["A7"], [(0, 81, 1), (1, 79, 1), (2, 76, 1), (3, 73, 1), (4, 76, 4)]),
    (["Dm7", "G7"], [(0, 77, 1), (1, 76, 1), (2, 74, 2), (4, 79, 1), (5, 77, 1), (6, 71, 2)]),
    (["C6"], [(0, 72, 4), (6, 79, 1), (7, 76, 1)]),
]
CONSOLA_B = [
    (["Fmaj7"], [(0, 81, 3), (3, 79, 1), (4, 76, 4)]),
    (["Fm6"], [(0, 80, 3), (3, 77, 1), (4, 74, 4)]),
    (["Em7"], [(0, 79, 2), (2, 83, 2), (4, 86, 3), (7, 84, 1)]),
    (["A7"], [(0, 85, 4), (4, 81, 2), (6, 79, 2)]),
    (["Dm7"], [(0, 77, 1), (1, 81, 1), (2, 84, 2), (4, 86, 4)]),
    (["G7"], [(0, 84, 2), (2, 83, 2), (4, 79, 2), (6, 77, 2)]),
    (["Em7", "A7"], [(0, 76, 2), (2, 79, 2), (4, 79, 1), (5, 76, 1), (6, 73, 2)]),
    (["Dm7", "G7"], [(0, 74, 2), (2, 77, 2), (4, 79, 2), (6, 71, 2)]),
]


def _consola(m: _Mezcla, duracion_s: float, cambios_s: list[float]) -> None:
    c = _Compas(116, swing=0.62)
    intro = [(a, []) for a, _ in CONSOLA_A[:4]]
    for i, (acordes, melodia) in enumerate(_bucle(intro, [CONSOLA_A, CONSOLA_A, CONSOLA_B, CONSOLA_A])):
        t0 = i * c.largo
        if t0 >= duracion_s:
            break
        mitad = len(acordes) > 1
        for j, nombre in enumerate(acordes):
            raiz, ints = CONSOLA_ACORDES[nombre]
            ta = t0 + j * 2 * c.negra
            # Piano: golpe corto en la parte y otro a contratiempo (charlestón), la voz en el registro medio.
            voz = [raiz + x + (12 if raiz + x < 55 else 0) for x in ints]
            golpes = [(0, 0.9), (3, 0.6)] if not mitad else [(0, 0.9)]
            for k, g in golpes:
                for q, nota in enumerate(voz):
                    m.poner(ta + c.corchea_s(k), _piano(_hz(nota), c.corchea * (1.6 if k == 0 else 1.1)), 0.04 * g,
                            -0.35 + 0.23 * q)
            # Bajo: fundamental y quinta (o solo la fundamental si el compás tiene dos acordes).
            bajo = raiz - 12 if raiz >= 48 else raiz
            notas = [(0, bajo), (2, bajo + 7)] if not mitad else [(0, bajo)]
            for k, nota in notas:
                m.poner(ta + k * c.negra, _bajo(_hz(nota), c.negra * 1.8), 0.16)
        for k, nota, largo in melodia:
            m.poner(t0 + c.corchea_s(k), _vibrafono(_hz(nota), largo * c.corchea), 0.14, 0.05)
        # Percusión: maraca en las corcheas, aro en 2 y 4, bombo suave en 1 y 3.
        for k in range(8):
            m.poner(t0 + c.corchea_s(k), _ruido(0.07, 55, 100 + k), 0.012 if k % 2 == 0 else 0.02, 0.45)
        for b in (1, 3):
            m.poner(t0 + b * c.negra, _aro(), 0.035, -0.3)
        for b in (0, 2):
            m.poner(t0 + b * c.negra, _bombo(), 0.09)
    destello = _destello()
    for t in cambios_s:
        if 0 < t < duracion_s - 1:
            m.poner(t, destello, 0.035, 0.3)
    m.sala(((0.043, 0.18), (0.071, 0.14), (0.113, 0.1), (0.197, 0.06)))


# ---------------------------------------------------------------- noticiario

NOTICIARIO_ACORDES = {
    "Bb": (46, (0, 4, 7)), "Eb": (51, (0, 4, 7)), "F7": (41, (0, 4, 7, 10)),
    "Gm": (43, (0, 3, 7)), "C7": (48, (0, 4, 7, 10)),
}
NOTICIARIO_A = [
    ("Bb", [(0, 77, 3), (3, 74, 1), (4, 77, 2), (6, 82, 2)]),
    ("Eb", [(0, 79, 2), (2, 75, 2), (4, 79, 2), (6, 82, 2)]),
    ("F7", [(0, 81, 3), (3, 79, 1), (4, 77, 2), (6, 75, 2)]),
    ("Bb", [(0, 74, 4), (4, 70, 2), (6, 74, 2)]),
    ("Gm", [(0, 74, 3), (3, 77, 1), (4, 79, 2), (6, 82, 2)]),
    ("C7", [(0, 84, 3), (3, 82, 1), (4, 79, 2), (6, 76, 2)]),
    ("F7", [(0, 77, 2), (2, 81, 2), (4, 84, 2), (6, 81, 2)]),
    ("Bb", [(0, 82, 6)]),
]
NOTICIARIO_B = [
    ("Eb", [(0, 79, 4), (4, 82, 4)]),
    ("Eb", [(0, 87, 4), (4, 86, 2), (6, 84, 2)]),
    ("Bb", [(0, 82, 4), (4, 77, 4)]),
    ("Gm", [(0, 79, 2), (2, 82, 2), (4, 86, 4)]),
    ("C7", [(0, 88, 4), (4, 84, 2), (6, 82, 2)]),
    ("C7", [(0, 79, 4), (4, 76, 4)]),
    ("F7", [(0, 77, 2), (2, 81, 2), (4, 84, 2), (6, 87, 2)]),
    ("F7", [(0, 86, 4), (4, 84, 2), (6, 81, 2)]),
]
# La fanfarria de entrada, sobre la dominante: tres llamadas y una nota larga.
NOTICIARIO_INTRO = [("F7", [(0, 77, 1), (1, 77, 1), (2, 77, 1), (3, 81, 5)]), ("F7", [(0, 84, 6)])]


def _noticiario(m: _Mezcla, duracion_s: float, cambios_s: list[float]) -> None:
    c = _Compas(128)
    entrada = len(NOTICIARIO_INTRO)
    for i, (nombre, melodia) in enumerate(_bucle(NOTICIARIO_INTRO, [NOTICIARIO_A, NOTICIARIO_A, NOTICIARIO_B, NOTICIARIO_A])):
        t0 = i * c.largo
        if t0 >= duracion_s:
            break
        raiz, ints = NOTICIARIO_ACORDES[nombre]
        dentro = i - entrada   # compás dentro de la forma (negativo en la fanfarria)
        # Um-pa: tuba en 1 y 3 (fundamental y quinta), acorde corto de metales en 2 y 4.
        if dentro >= 0:
            for b, nota in ((0, raiz - 12), (2, raiz - 5)):
                m.poner(t0 + b * c.negra, _bajo(_hz(nota), c.negra * 0.9), 0.2)
                m.poner(t0 + b * c.negra, _bombo(), 0.08)
            voz = [raiz + x + (12 if raiz + x < 57 else 0) for x in ints]
            for b in (1, 3):
                for q, nota in enumerate(voz):
                    m.poner(t0 + b * c.negra, _metal(_hz(nota), c.corchea * 0.8, 0.7), 0.022, -0.4 + 0.25 * q)
        for k, nota, largo in melodia:
            m.poner(t0 + c.corchea_s(k), _metal(_hz(nota), largo * c.corchea * 0.92), 0.075, 0.08)
            m.poner(t0 + c.corchea_s(k), _vibrafono(_hz(nota + 12), 0.15), 0.025, 0.3)   # el glockenspiel dobla
        # Caja en 2 y 4; al final de cada cuatro compases (y en la fanfarria), un redoble que lleva al siguiente.
        for b in (1, 3):
            m.poner(t0 + b * c.negra, _caja(), 0.07, -0.2)
        if dentro < 0 or dentro % 4 == 3:
            golpes = 16 if dentro < 0 else 6
            for g in range(golpes):
                m.poner(t0 + (4 - golpes / 4) * c.negra + g * c.negra / 4, _caja(20 + g), 0.025 + 0.04 * g / golpes, -0.2)
        if i == 0 or (dentro >= 0 and dentro % 8 == 0):
            m.poner(t0, _platillo(), 0.05, 0.35)
    m.sala(((0.031, 0.2), (0.057, 0.16), (0.089, 0.12), (0.149, 0.08), (0.23, 0.05)))


# ---------------------------------------------------------------- ambiente

# Progresión en La menor (semitonos desde La 220 Hz): Am9, Fmaj7, C(add9), G6, Dm9, Em7.
AMBIENTE_ACORDES = [(0, 3, 7, 10, 14), (-4, 0, 3, 7, 11), (3, 7, 10, 14, 15), (-2, 2, 5, 7, 10), (5, 8, 12, 15, 19),
                    (7, 10, 14, 17, 19)]
AMBIENTE_ORDEN = [0, 1, 2, 3, 0, 1, 4, 5]


def _ambiente(m: _Mezcla, duracion_s: float, cambios_s: list[float]) -> None:
    n = len(m.izq)
    cortes = [0.0] + [c for c in cambios_s if 0 < c < duracion_s] + [duracion_s]
    for k in range(len(cortes) - 1):
        a, b = int(cortes[k] * SR), min(n, int(cortes[k + 1] * SR) + int(1.2 * SR))
        if b <= a:
            continue
        t = np.arange(b - a) / SR
        acorde = AMBIENTE_ACORDES[AMBIENTE_ORDEN[k % len(AMBIENTE_ORDEN)]]
        env = _env(b - a, 0.9, 0, 1.4)
        pad_i, pad_d = np.zeros(b - a), np.zeros(b - a)
        for j, s in enumerate(acorde):
            f = 220.0 * 2 ** (s / 12)
            lfo = 1 + 0.12 * np.sin(2 * np.pi * (0.18 + 0.05 * j) * t + j)
            pad_i += lfo * (np.sin(2 * np.pi * f * 0.998 * t) + 0.18 * np.sin(4 * np.pi * f * t))
            pad_d += lfo * (np.sin(2 * np.pi * f * 1.002 * t + 0.7) + 0.18 * np.sin(4 * np.pi * f * t + 0.3))
        bajo = 0.9 * np.sin(2 * np.pi * 55.0 * 2 ** (acorde[0] / 12) * t) * _env(b - a, 0.3, 0, 1.0)
        # Arpegio de corcheas (≈ 100 bpm) que sube y baja por el acorde, con caída rápida.
        arp = np.zeros(b - a)
        paso = int(0.3 * SR)
        notas = list(acorde) + list(acorde[-2:0:-1])
        for q, p in enumerate(range(int(0.15 * SR), b - a, paso)):
            f = 440.0 * 2 ** (notas[q % len(notas)] / 12)
            largo = min(int(1.1 * SR), b - a - p)
            tt = np.arange(largo) / SR
            arp[p:p + largo] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 5.5) * (0.55 + 0.45 * (q % 2 == 0))
        m.izq[a:b] += env * (0.11 * pad_i + 0.10 * bajo + 0.07 * arp)
        m.der[a:b] += env * (0.11 * pad_d + 0.10 * bajo + 0.07 * np.roll(arp, int(0.012 * SR)))
    m.sala(((0.37, 0.32), (0.61, 0.2), (0.93, 0.12)))


# ---------------------------------------------------------------- taller y cuento: instrumentos de cuento

def _cuerda(f: float, dur: float, brillo: float = 0.5, semilla: int = 0, caida: float = 0.996) -> np.ndarray:
    """Una cuerda pulsada (Karplus-Strong): pizzicato con brillo bajo, arpa con brillo alto."""
    periodo = max(2, int(round(SR / f)))
    n = int(dur * SR)
    ruido = np.random.default_rng(semilla).uniform(-1, 1, periodo)
    for _ in range(int((1 - brillo) * 6)):
        ruido = 0.5 * (ruido + np.roll(ruido, 1))
    bloques = [ruido - ruido.mean()]
    anterior_ultimo = 0.0
    while len(bloques) * periodo < n:
        b = bloques[-1]
        nuevo = caida * 0.5 * (b + np.concatenate(([anterior_ultimo], b[:-1])))
        anterior_ultimo = b[-1]
        bloques.append(nuevo)
    voz = np.concatenate(bloques)[:n]
    return voz * _env(n, 0.001, 0.0, 0.05) / max(1e-9, np.abs(voz).max())


def _lengueta(f: float, dur: float, armonicos: tuple[float, ...], ataque: float = 0.03,
              vibrato: float = 0.0, desafine: float = 0.0, caida: float = 0.4) -> np.ndarray:
    """Un instrumento de lengüeta o de soplo a base de armónicos; con desafine, dos voces (acordeón musette)."""
    n = int((dur + 0.08) * SR)
    t = np.arange(n) / SR
    vib = 1 + vibrato * np.sin(2 * np.pi * 5.3 * t) * np.clip((t - 0.18) / 0.25, 0, 1)
    voz = np.zeros(n)
    for d in ((1 - desafine, 1 + desafine) if desafine else (1.0,)):
        fase = 2 * np.pi * f * d * np.cumsum(vib) / SR
        voz += sum(a * np.sin((k + 1) * fase) for k, a in enumerate(armonicos) if a and (k + 1) * f * d < SR / 2.2)
    return voz * _env(n, ataque, caida, 0.07)


CLARINETE = (1.0, 0.04, 0.45, 0.03, 0.22, 0.02, 0.1, 0.0, 0.05)
ACORDEON = (1.0, 0.7, 0.55, 0.42, 0.3, 0.22, 0.15, 0.1)
FAGOT = (0.55, 1.0, 0.75, 0.45, 0.28, 0.16, 0.08)
FLAUTA = (1.0, 0.22, 0.07, 0.03)
CUERDAS = tuple(1 / k for k in range(1, 11))


def _caja_musica(f: float) -> np.ndarray:
    """Una púa de caja de música: fundamental limpia y parciales altos que se apagan enseguida."""
    n = int(1.6 * SR)
    t = np.arange(n) / SR
    voz = (np.sin(2 * np.pi * f * t) * np.exp(-t * 2.4) + 0.35 * np.sin(2 * np.pi * f * 3.01 * t) * np.exp(-t * 9)
           + 0.12 * np.sin(2 * np.pi * f * 5.43 * t) * np.exp(-t * 18))
    return voz * _env(n, 0.002, 0.0, 0.2)


def _campana(f: float, dur: float = 2.5) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    parciales = ((1.0, 1.0, 1.2), (2.0, 0.5, 2.0), (2.4, 0.35, 2.6), (3.0, 0.25, 3.5), (4.2, 0.15, 5.0))
    return sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t * c) for r, a, c in parciales) * _env(n, 0.002, 0, 0.3)


def _caja_china(semilla: int = 0) -> np.ndarray:
    n = int(0.09 * SR)
    t = np.arange(n) / SR
    golpe = (np.sin(2 * np.pi * 1180 * t) + 0.4 * np.sin(2 * np.pi * 2650 * t)) * np.exp(-t * 55)
    return golpe + 0.1 * _ruido(0.09, 60, semilla)[:n]


def _filtrar(m: _Mezcla, corte_hz: float) -> None:
    """Un paso bajo suave sobre toda la mezcla (en frecuencia): el sonido cálido y apagado de la sala."""
    for canal in (m.izq, m.der):
        espectro = np.fft.rfft(canal)
        f = np.fft.rfftfreq(len(canal), 1 / SR)
        espectro *= 1 / np.sqrt(1 + (f / corte_hz) ** 4)
        canal[:] = np.fft.irfft(espectro, len(canal))


# ---------------------------------------------------------------- taller

# Una canción de taller de inventor, de cuento: La bemol mayor a 100 bpm, fagot saltando en cada pulso,
# acordeón musette con los acordes, clarinete con la melodía (cromatismos y apoyaturas), glockenspiel que
# contesta al final de cada frase, caja china y pizzicato a contratiempo.
TALLER_ACORDES = {
    "Ab": (44, (0, 4, 7)), "Fm": (41, (0, 3, 7)), "Db": (49, (0, 4, 7)), "Eb7": (39, (0, 4, 7, 10)),
    "C7": (48, (0, 4, 7, 10)), "Bbm7": (46, (0, 3, 7, 10)), "Dbm": (49, (0, 3, 7)), "F7": (41, (0, 4, 7, 10)),
    "Ab/C": (48, (-4, 0, 3)),
}
TALLER_A = [
    (["Ab"], [(0, 72, 1), (1, 75, 1), (2, 80, 2), (4, 79, 1), (5, 80, 1), (6, 77, 2)]),
    (["Fm"], [(0, 77, 1), (1, 76, 1), (2, 77, 1), (3, 80, 1), (4, 84, 3), (7, 82, 1)]),
    (["Db"], [(0, 80, 2), (2, 77, 1), (3, 73, 1), (4, 77, 2), (6, 80, 1), (7, 79, 1)]),
    (["Eb7"], [(0, 79, 3), (3, 75, 1), (4, 73, 2), (6, 70, 2)]),
    (["Ab"], [(0, 72, 1), (1, 75, 1), (2, 80, 2), (4, 84, 1), (5, 82, 1), (6, 80, 2)]),
    (["C7"], [(0, 79, 1), (1, 78, 1), (2, 79, 1), (3, 76, 1), (4, 72, 2), (6, 70, 1), (7, 72, 1)]),
    (["Fm"], [(0, 73, 1), (1, 72, 1), (2, 73, 1), (3, 77, 1), (4, 80, 2), (6, 77, 2)]),
    (["Bbm7", "Eb7"], [(0, 75, 2), (2, 73, 1), (3, 72, 1), (4, 70, 2), (6, 67, 1), (7, 70, 1)]),
]
TALLER_B = [
    (["Db"], [(0, 77, 3), (3, 80, 1), (4, 85, 4)]),
    (["Dbm"], [(0, 84, 2), (2, 80, 2), (4, 76, 4)]),
    (["Ab/C"], [(0, 75, 1), (1, 77, 1), (2, 80, 2), (4, 79, 1), (5, 80, 1), (6, 84, 2)]),
    (["F7"], [(0, 81, 3), (3, 80, 1), (4, 77, 2), (6, 75, 2)]),
    (["Bbm7"], [(0, 73, 1), (1, 77, 1), (2, 80, 2), (4, 82, 2), (6, 80, 2)]),
    (["Eb7"], [(0, 79, 2), (2, 82, 2), (4, 85, 3), (7, 84, 1)]),
    (["Ab"], [(0, 84, 4), (4, 80, 2), (6, 75, 2)]),
    (["Eb7"], [(0, 79, 1), (1, 80, 1), (2, 79, 1), (3, 77, 1), (4, 75, 2), (6, 74, 1), (7, 75, 1)]),
]


def _taller(m: _Mezcla, duracion_s: float, cambios_s: list[float]) -> None:
    c = _Compas(100, swing=0.56)
    intro = [(a, []) for a, _ in TALLER_A[:2]]
    for i, (acordes, melodia) in enumerate(_bucle(intro, [TALLER_A, TALLER_A, TALLER_B, TALLER_A])):
        t0 = i * c.largo
        if t0 >= duracion_s:
            break
        por_acorde = 4 // len(acordes)
        for j, nombre in enumerate(acordes):
            raiz, ints = TALLER_ACORDES[nombre]
            ta = t0 + j * por_acorde * c.negra
            # Fagot: fundamental, quinta, octava y una nota de paso cromática hacia el siguiente acorde.
            bajo = raiz - 12 if raiz >= 46 else raiz
            linea = [bajo, bajo + 7, bajo + 12, bajo + 6] if por_acorde == 4 else [bajo, bajo + 7]
            for b, nota in enumerate(linea):
                m.poner(ta + b * c.negra, _lengueta(_hz(nota), c.negra * 0.75, FAGOT, ataque=0.015, caida=2.5), 0.12, -0.15)
                # El contrabajo en pizzicato dobla al fagot una octava abajo: el suelo de la canción.
                m.poner(ta + b * c.negra, _cuerda(_hz(nota - 12), 0.7, 0.0, 70 + i * 5 + b, 0.994), 0.22, 0)
            # Acordeón: el acorde sostenido en la parte fuerte y un golpe corto de fuelle en el contratiempo.
            voz = [raiz + x + 12 if raiz + x < 58 else raiz + x for x in ints]
            for q, nota in enumerate(voz):
                m.poner(ta, _lengueta(_hz(nota), c.negra * min(por_acorde, 2) * 0.9, ACORDEON, ataque=0.04,
                                      desafine=0.0022, caida=0.9), 0.022, -0.45 + 0.2 * q)
                if por_acorde == 4:
                    m.poner(ta + 2 * c.negra + c.swing * c.negra, _lengueta(_hz(nota), c.corchea * 0.8, ACORDEON,
                            ataque=0.02, desafine=0.0022, caida=3), 0.016, -0.45 + 0.2 * q)
            # Pizzicato a contratiempo, en la tercera del acorde.
            for b in (1, 3)[: por_acorde // 2]:
                m.poner(ta + b * c.negra, _cuerda(_hz(raiz + ints[1] + 12), 0.5, 0.15, 30 + i * 7 + b), 0.045, 0.45)
        for k, nota, largo in melodia:
            ini = t0 + c.corchea_s(k)
            # Una apoyatura de abajo en las notas largas que caen en parte fuerte: el adorno del clarinete.
            if largo >= 2 and k % 2 == 0 and ini > 0.06:
                m.poner(ini - 0.055, _lengueta(_hz(nota - 1), 0.05, CLARINETE, ataque=0.008, caida=3), 0.045, 0.1)
            m.poner(ini, _lengueta(_hz(nota), largo * c.corchea * 0.95, CLARINETE, ataque=0.025, vibrato=0.006,
                                   caida=0.5), 0.085, 0.1)
        # El glockenspiel contesta en el último tiempo de cada frase de dos compases.
        if melodia and i % 2 == 1:
            nota = melodia[-1][1]
            for d, salto in enumerate((0, 7, 12)):
                m.poner(t0 + 3 * c.negra + d * c.corchea / 2, _vibrafono(_hz(nota + 12 + salto), 0.12), 0.03, 0.35)
        # Caja china en 2 y 4.
        for b in (1, 3):
            m.poner(t0 + b * c.negra, _caja_china(i * 4 + b), 0.035, -0.35)
    for t in cambios_s:
        if 0 < t < duracion_s - 1:
            for d, nota in enumerate((80, 84, 87, 92)):
                m.poner(t + d * 0.05, _vibrafono(_hz(nota + 12), 0.15), 0.028 - 0.004 * d, 0.3)
    m.sala(((0.029, 0.2), (0.053, 0.15), (0.087, 0.11), (0.139, 0.07), (0.21, 0.04)))
    _filtrar(m, 4200)


# ---------------------------------------------------------------- cuento

# Un cuento con un rey de los espíritus: Do menor a 117 bpm, una caja de música en corcheas que da vueltas
# sobre el acorde, arpa en negras, cuerdas graves que sostienen la nota pedal dos compases, una flauta
# que entra a la segunda vuelta y campanas en cada cambio de escena. Todo apagado, como de noche.
CUENTO_ACORDES = {
    "Cm": (48, (0, 3, 7)), "Ab": (44, (0, 4, 7)), "Fm": (41, (0, 3, 7)), "G7": (43, (0, 4, 7, 10)),
    "Eb": (51, (0, 4, 7)), "G": (43, (0, 4, 7)), "Bb": (46, (0, 4, 7)),
}
CUENTO_FORMA = ["Cm", "Cm", "Ab", "Ab", "Fm", "Fm", "G7", "G7", "Cm", "Cm", "Eb", "Bb", "Fm", "Ab", "G", "G"]
CUENTO_FLAUTA = [
    [(0, 75, 6), (6, 74, 2)], [(0, 72, 8)], [(0, 72, 4), (4, 75, 4)], [(0, 80, 6), (6, 79, 2)],
    [(0, 77, 4), (4, 80, 4)], [(0, 84, 6), (6, 82, 2)], [(0, 83, 4), (4, 79, 4)], [(0, 77, 4), (4, 74, 4)],
    [(0, 75, 3), (3, 74, 1), (4, 72, 4)], [(0, 67, 8)], [(0, 70, 4), (4, 75, 4)], [(0, 74, 6), (6, 77, 2)],
    [(0, 77, 4), (4, 80, 4)], [(0, 84, 4), (4, 82, 2), (6, 80, 2)], [(0, 79, 8)], [(0, 74, 4), (4, 71, 4)],
]


def _cuento(m: _Mezcla, duracion_s: float, cambios_s: list[float]) -> None:
    c = _Compas(117)
    i = 0
    while i * c.largo < duracion_s:
        t0 = i * c.largo
        vuelta, k = divmod(i - 4, len(CUENTO_FORMA)) if i >= 4 else (-1, i)
        raiz, ints = CUENTO_ACORDES[CUENTO_FORMA[k]]
        # Caja de música: fundamental, quinta, tercera, quinta, octava… dando vueltas en el registro medio.
        arriba = raiz + 12 if raiz < 48 else raiz
        giro = [0, 7, ints[1] + 12, 7, 12, 7, ints[1], 7] if k % 2 == 0 else [12, ints[1] + 12, 7, ints[1], 0, 7, 12, 19]
        for q, s in enumerate(giro):
            m.poner(t0 + q * c.corchea, _caja_musica(_hz(arriba + s)), 0.085 * (1.0 if q % 2 == 0 else 0.75),
                    0.3 - 0.08 * (q % 4))
        # Arpa en negras, en el registro medio.
        for b, s in enumerate((0, 7, 12, ints[1] + 12)):
            m.poner(t0 + b * c.negra, _cuerda(_hz(raiz + s), 1.4, 0.7, 50 + 4 * i + b, 0.9985), 0.06, -0.35)
        # Nota pedal de las cuerdas graves: entra al principio de cada pareja de compases.
        if k % 2 == 0:
            m.poner(t0, _lengueta(_hz(raiz - 12), 2 * c.largo, CUERDAS, ataque=0.45, desafine=0.003, caida=0.05), 0.03)
            m.poner(t0, _lengueta(_hz(raiz), 2 * c.largo, CUERDAS, ataque=0.6, desafine=0.004, caida=0.08), 0.011, -0.2)
        # La flauta canta en las vueltas impares; en las pares, la caja de música va sola.
        if vuelta >= 0 and vuelta % 2 == 0:
            for kk, nota, largo in CUENTO_FLAUTA[k]:
                m.poner(t0 + kk * c.corchea, _lengueta(_hz(nota), largo * c.corchea * 0.95, FLAUTA, ataque=0.07,
                                                       vibrato=0.007, caida=0.2), 0.07, 0.1)
        i += 1
    for t in [0.0, *cambios_s]:
        if 0 <= t < duracion_s - 1:
            m.poner(t, _campana(_hz(84)), 0.03, -0.25)
            m.poner(t + 0.11, _campana(_hz(91)), 0.02, 0.3)
    m.sala(((0.047, 0.24), (0.083, 0.2), (0.131, 0.15), (0.211, 0.11), (0.337, 0.07), (0.53, 0.04)))
    _filtrar(m, 2600)


def generar(destino: Path, duracion_s: float, cambios_s: list[float], estilo: str = ESTILOS[0]) -> Path:
    """cambios_s: cuándo empieza cada escena después de la primera (destello en «consola», acorde nuevo en
    «ambiente»)."""
    if estilo not in ESTILOS:
        raise ValueError(f"estilo de música desconocido: {estilo} (hay {', '.join(ESTILOS)})")
    n = int(duracion_s * SR)
    m = _Mezcla(n)
    {"taller": _taller, "cuento": _cuento, "consola": _consola, "noticiario": _noticiario,
     "ambiente": _ambiente}[estilo](m, duracion_s, cambios_s)
    final = _env(n, 0.0, 0.0, 3.5)
    entrada = min(int(0.8 * SR), n)
    final[:entrada] *= np.linspace(0, 1, entrada)
    estereo = np.stack([m.izq * final, m.der * final], axis=1)
    estereo *= 0.55 / max(1e-9, np.abs(estereo).max())
    destino.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((estereo * 32767).astype("<i2").tobytes())
    return destino
