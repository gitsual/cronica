"""La música de fondo, escrita para cada vídeo: dura lo que dura y cada cambio de escena cae en ella.

Con la orquesta (instrumentos grabados de verdad, cronica/orquesta):

- ascensor (por defecto): bossa de ascensor como marco, con los colores de un menú de consola, de un café de
  acordeón y de un taller de inventor entrando por secciones. Armonía de novenas con las voces bien llevadas.
- vals: un vals de café en re menor, acordeón y «um-pa-pa» de contrabajo y violines en pizzicato.
- taller: la bemol a 104 bpm, fagot y contrabajo saltando, acordeón a contratiempo, clarinete y glockenspiel.
- cuento: de noche, arpa y caja de música en ostinato, chelos, flauta y oboe.

Con síntesis (senos y ruido), los de antes: consola, noticiario y ambiente.

Si se pasa --music con un fichero, se ajusta al vídeo por compases (ajustar_pista).
"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 44100
ESTILOS = ("ascensor", "vals", "taller", "cuento", "consola", "noticiario", "ambiente")
ORQUESTA = ("ascensor", "vals", "taller", "cuento")


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


def generar(destino: Path, duracion_s: float, cambios_s: list[float], estilo: str = ESTILOS[0],
            ffmpeg: str = "ffmpeg") -> Path:
    """cambios_s: cuándo empieza cada escena después de la primera. Los estilos de la orquesta necesitan ffmpeg
    para leer sus muestras."""
    if estilo not in ESTILOS:
        raise ValueError(f"estilo de música desconocido: {estilo} (hay {', '.join(ESTILOS)})")
    n = int(duracion_s * SR)
    if estilo in ORQUESTA:
        from .orquesta import piezas
        o = getattr(piezas, estilo)(duracion_s, cambios_s, ffmpeg)
        izq, der = o.izq[:n], o.der[:n]
    else:
        m = _Mezcla(n)
        {"consola": _consola, "noticiario": _noticiario, "ambiente": _ambiente}[estilo](m, duracion_s, cambios_s)
        izq, der = m.izq, m.der
    return _escribir(destino, izq, der)


def _escribir(destino: Path, izq: np.ndarray, der: np.ndarray, normalizar: bool = True,
              fundido: bool = True) -> Path:
    n = len(izq)
    final = np.ones(n)
    if fundido:
        final = _env(n, 0.0, 0.0, 3.5)
        entrada = min(int(0.8 * SR), n)
        final[:entrada] *= np.linspace(0, 1, entrada)
    estereo = np.stack([izq * final, der * final], axis=1)
    if normalizar:
        estereo *= 0.55 / max(1e-9, np.abs(estereo).max())
    destino.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(estereo, -1, 1) * 32767).astype("<i2").tobytes())
    return destino


# ---------------------------------------------------------------- pistas propias, ajustadas por compases

EXTENSIONES = (".mp3", ".wav", ".ogg", ".flac", ".m4a")


def carpeta_pistas() -> Path:
    """Donde viven las pistas propias que se eligen por nombre (junto a settings.json)."""
    from . import ajustes
    return ajustes.ruta().parent / "pistas"


def pistas() -> dict[str, Path]:
    """Las pistas propias instaladas: nombre (el del fichero, sin extensión) -> fichero."""
    carpeta = carpeta_pistas()
    if not carpeta.is_dir():
        return {}
    return {f.stem: f for f in sorted(carpeta.iterdir()) if f.suffix.lower() in EXTENSIONES}


def _pulso(x: np.ndarray) -> tuple[float, float]:
    """(segundos por negra, primer tiempo fuerte) de una mezcla mono: autocorrelación de la envolvente de ataques
    entre 70 y 180 bpm, y el uno donde más pesa el grave."""
    salto = 512
    tramas = len(x) // salto
    energia = np.sqrt(np.add.reduceat(x[: tramas * salto] ** 2, np.arange(0, tramas * salto, salto)) / salto)
    ataques = np.maximum(0, np.diff(np.log(energia + 1e-6), prepend=0))
    ataques -= ataques.mean()
    fps = SR / salto
    ac = np.fft.irfft(np.abs(np.fft.rfft(ataques, 2 * len(ataques))) ** 2)[: len(ataques)]
    lags = np.arange(int(fps * 60 / 180), int(fps * 60 / 70))
    # Entre el tempo y sus parientes (3:2, 2:1) gana el más habitual: una campana alrededor de 115 bpm.
    preferencia = np.exp(-0.5 * (np.log2(60 * fps / lags / 115) / 0.35) ** 2)
    negra = lags[np.argmax(ac[lags] * preferencia)] / fps
    paso = negra * fps

    def peso(f0: float) -> float:
        idx = (f0 + np.arange(0, len(ataques) - f0, 4 * paso)).astype(int)
        return ataques[idx[idx < len(ataques)]].sum()

    return float(negra), float(max(range(int(4 * paso)), key=peso) / fps)


def _rejilla(fichero: Path, mono: np.ndarray) -> tuple[float, float]:
    """La rejilla de la pista: de <pista>.json si está ({"negra": s, "uno": s}), si no, medida."""
    meta = fichero.with_suffix(".json")
    if meta.is_file():
        import json
        d = json.loads(meta.read_text(encoding="utf-8"))
        return float(d["negra"]), float(d["uno"])
    return _pulso(mono)


def _huellas(mono: np.ndarray, uno: int, compas: float, compases: int) -> tuple[np.ndarray, np.ndarray]:
    """Por compás: su croma (12 clases de altura, normalizado) y su volumen, para saber qué compases se parecen."""
    cromas, vol = [], []
    for b in range(compases):
        a = uno + int(round(b * compas))
        seg = mono[a:a + int(compas)]
        esp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        f = np.fft.rfftfreq(len(seg), 1 / SR)
        util = (f > 60) & (f < 5000)
        clase = np.round(12 * np.log2(f[util] / 440.0)).astype(int) % 12
        c = np.bincount(clase, weights=esp[util] ** 2, minlength=12)
        cromas.append(c / (np.linalg.norm(c) + 1e-9))
        vol.append(np.sqrt((seg ** 2).mean()) + 1e-6)
    return np.array(cromas), np.log(np.array(vol))


def _secuencia(compases: int, objetivo: int, croma: np.ndarray, vol: np.ndarray) -> list[int]:
    """Qué compases suenan, en orden, para durar `objetivo` compases: un salto hacia delante para acortar, o un
    bucle hacia atrás (repetido) para alargar. Se salta de un compás a otro que suena como el que tocaría."""
    def d(a: int, b: int) -> float:
        if not (0 <= a < compases and 0 <= b < compases):
            return 9.0
        return float(1 - croma[a] @ croma[b] + 0.5 * abs(vol[a] - vol[b]))

    def salto(i: int, j: int) -> float:   # tras el compás i-1 suena el j en vez del i
        # Saltar conservando el sitio dentro de la frase de cuatro compases (la pista puede tener un compás suelto
        # al principio, así que cuenta la distancia, no el número de compás).
        return d(i, j) + d(i - 1, j - 1) + (0 if (j - i) % 4 == 0 else 1.0)

    orden = list(range(compases))
    if objetivo >= compases:
        # Alargar: el bucle [y, x] que mejor empalma (x+1 ≈ y), de 8 a 32 compases, lejos del principio y del final.
        falta = objetivo - compases
        if falta == 0:
            return orden
        opciones = [(salto(x + 1, y) + (0 if (x - y + 1) % 8 == 0 else 0.3) + (0.25 if x - y + 1 < 16 else 0), y, x)
                    for x in range(8, compases - 4) for y in range(4, x - 6) if 8 <= x - y + 1 <= 32]
        if not opciones:
            return (orden * (objetivo // compases + 1))[:objetivo]
        _c, y, x = min(opciones)
        largo = x - y + 1
        vueltas = -(-falta // largo)
        orden = list(range(x + 1)) + list(range(y, x + 1)) * vueltas + list(range(x + 1, compases))
    # Acortar (o quitar lo que sobra de la última vuelta): un salto hacia delante, ni en los 4 primeros ni en los
    # 4 últimos compases, que conservan la entrada y el final de verdad.
    sobra = len(orden) - objetivo
    sobra += (-sobra) % 4   # frases enteras: puede quedar hasta tres compases corta (ajustar_pista la estira)
    if sobra > 0:
        opciones = [(salto(orden[p], orden[p + sobra]), p) for p in range(4, len(orden) - sobra - 4)]
        if opciones:
            _c, p = min(opciones)
            orden = orden[:p] + orden[p + sobra:]
        else:
            orden = orden[:objetivo]
    return orden


def _estirar(x: np.ndarray, tempo: float, ffmpeg: str) -> np.ndarray:
    """La misma música más lenta (tempo < 1) sin cambiar el tono: atempo de ffmpeg."""
    crudo = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    salida = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-f", "s16le", "-ac", "2", "-ar", str(SR), "-i", "-",
                             "-af", f"atempo={tempo:.5f}", "-f", "s16le", "-ac", "2", "-ar", str(SR), "-"],
                            input=crudo, capture_output=True, check=True).stdout
    return np.frombuffer(salida, "<i2").astype(np.float32).reshape(-1, 2) / 32768


def ajustar_pista(fichero: Path, destino: Path, duracion_s: float, cambios_s: list[float],
                  ffmpeg: str = "ffmpeg") -> Path:
    """Una pista propia a la medida del vídeo, por compases enteros: si el vídeo es más corto, se salta un trozo del
    medio y la canción llega a su final de verdad; si es más largo, se repite en bucle un trozo del cuerpo. Los
    empalmes van en el uno de un compás, entre compases que se parecen, con un fundido de 40 ms. En cada cambio de
    escena suena un triángulo en el pulso más cercano."""
    crudo = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(fichero), "-f", "s16le", "-ac", "2",
                            "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(crudo, "<i2").astype(np.float32).reshape(-1, 2) / 32768
    if not len(x):
        raise ValueError(f"no hay audio en {fichero}")
    n = int(duracion_s * SR)
    mono = x.mean(axis=1)
    negra, uno_s = _rejilla(fichero, mono)
    compas, uno = 4 * negra * SR, int(uno_s * SR)
    total = int((len(x) - uno) // compas)
    cola = x[uno + int(round(total * compas)):]
    objetivo = max(4, int((n - uno - len(cola)) // compas))
    croma, vol = _huellas(mono, uno, compas, total)
    orden = _secuencia(total, objetivo, croma, vol)
    xf = int(0.04 * SR)
    trozos, previo = [x[:uno]], None
    for b in orden:
        a = uno + int(round(b * compas))
        seg = x[a:uno + int(round((b + 1) * compas))].copy()
        if previo is not None and b != previo + 1 and len(trozos[-1]) > xf:
            # Empalme: lo que sonaba se apaga mientras entra el compás nuevo (con su principio de verdad).
            k = np.linspace(0, 1, xf)[:, None]
            seguia = x[uno + int(round((previo + 1) * compas)):][:xf]
            seg[:len(seguia)] = seg[:len(seguia)] * k[:len(seguia)] + seguia * (1 - k[:len(seguia)])
        trozos.append(seg)
        previo = b
    trozos.append(cola)
    salida = np.concatenate(trozos)
    # Si quedó algo corta (frases enteras), se estira hasta un 6 % sin cambiar el tono, para acabar con el vídeo.
    if n * 0.94 <= len(salida) < n:
        salida = _estirar(salida, len(salida) / n, ffmpeg)
    corta = len(salida) > n   # solo si el vídeo es más corto que cuatro compases y la entrada
    if len(salida) < n:
        salida = np.concatenate([salida, np.zeros((n - len(salida), 2), np.float32)])
    salida = salida[:n]
    izq, der = salida[:, 0].astype(np.float64), salida[:, 1].astype(np.float64)
    try:
        from .orquesta import golpe
        triangulo = golpe("triangulo", ffmpeg)
        for t in cambios_s:
            pulso = uno_s + round((t - uno_s) / negra) * negra
            a = int(pulso * SR)
            if 0 < a < n - SR:
                trozo = triangulo[: n - a] * 0.1
                izq[a:a + len(trozo)] += trozo
                der[a:a + len(trozo)] += trozo
    except (OSError, KeyError, subprocess.CalledProcessError):
        pass   # sin el banco, la pista va sin triángulos
    # Sin fundido propio: la pista ya termina como termina; solo se suaviza si el vídeo corta antes.
    return _escribir(destino, izq, der, normalizar=False, fundido=corta)
