"""Las piezas de cronica, tocadas por la orquesta: cada una sabe durar lo que dure el vídeo y acentuar las escenas.

- ascensor (por defecto): la bossa de ascensor como marco (guitarra de nailon, Rhodes, contrabajo, batería suave)
  y, por secciones, los colores: vibráfono a lo menú de consola, acordeón con contramelodía de clarinete, clarinete
  con fagot y pizzicatos una tercera abajo, y flauta con vibráfono sobre cuerdas.
- vals: un vals de café en re menor, acordeón con «um-pa-pa» de contrabajo y violines en pizzicato.
- taller: canción de taller de inventor en la bemol, fagot, acordeón a contratiempo, clarinete y glockenspiel.
- cuento: de noche, arpa y caja de música en ostinato, chelos, flauta y oboe, celesta en cada escena.

Todas devuelven una Mezcla; musica.generar() la normaliza, le pone el fundido y la escribe.
"""
from __future__ import annotations

from . import Instrumento, Mezcla, golpe
from .armonia import acorde, conducir, guias


# Cada compás de 4/4 (ocho corcheas): uno o dos acordes (dos = medio compás cada uno) y la melodía.
A = [
    (["Fmaj9"], [(0, 72, 2), (2, 76, 2), (4, 79, 3), (7, 81, 1)]),
    (["Dm9"], [(0, 81, 4), (4, 79, 2), (6, 77, 2)]),
    (["Gm9"], [(0, 77, 3), (3, 74, 1), (4, 81, 4)]),
    (["C13sus4", "C7b9"], [(0, 79, 4), (4, 76, 2), (6, 73, 2)]),
    (["Am7"], [(0, 72, 2), (2, 76, 2), (4, 79, 3), (7, 76, 1)]),
    (["D7b9"], [(0, 78, 4), (4, 75, 2), (6, 72, 2)]),
    (["Gm9"], [(0, 74, 2), (2, 77, 2), (4, 81, 3), (7, 79, 1)]),
    (["C9sus4"], [(0, 79, 6), (7, 72, 1)]),
]
A2 = [
    (["Fmaj9"], [(0, 76, 3), (3, 77, 1), (4, 79, 4)]),
    (["F13"], [(0, 75, 4), (4, 74, 2), (6, 72, 2)]),
    (["Bbmaj9"], [(0, 77, 2), (2, 81, 2), (4, 84, 4)]),
    (["Bbm6/9"], [(0, 84, 3), (3, 79, 1), (4, 77, 2), (6, 73, 2)]),
    (["Am7"], [(0, 76, 4), (4, 74, 2), (6, 72, 2)]),
    (["Abmaj7#11"], [(0, 74, 3), (3, 75, 1), (4, 79, 4)]),
    (["Gm9", "C13"], [(0, 81, 2), (2, 77, 2), (4, 76, 2), (6, 74, 2)]),
    (["F6/9"], [(0, 79, 6)]),
]
B = [
    (["Dmaj9"], [(0, 73, 2), (2, 76, 2), (4, 81, 4)]),
    (["Bm9"], [(0, 85, 3), (3, 81, 1), (4, 78, 4)]),
    (["Em9"], [(0, 78, 2), (2, 79, 2), (4, 83, 3), (7, 81, 1)]),
    (["A13sus4"], [(0, 86, 4), (4, 83, 4)]),
    (["Dmaj9"], [(0, 81, 3), (3, 76, 1), (4, 73, 4)]),
    (["F#m7", "B7b9"], [(0, 76, 3), (3, 73, 1), (4, 75, 2), (6, 72, 2)]),
    (["Em9"], [(0, 71, 2), (2, 74, 2), (4, 78, 4)]),
    (["A7(13)"], [(0, 79, 3), (3, 78, 1), (4, 76, 4)]),
    (["Gm9"], [(0, 74, 2), (2, 77, 2), (4, 81, 4)]),
    (["C13sus4", "C7b9"], [(0, 79, 4), (4, 76, 2), (6, 73, 2)]),
]
INTRO = [(["Fmaj9"], []), (["Dm9"], []), (["Gm9"], []), (["C13sus4", "C7b9"], [])]
# La forma: (sección, compases, quién canta)
FORMA = [("intro", INTRO, None), ("wii", A, "vibrafono"), ("layton", A2, "acordeon"),
         ("taller", B, "clarinete"), ("final", A2, "flauta")]


def _bajo(pc: int) -> int:
    b = 36 + (pc - 36) % 12
    return b - 12 if b > 45 else b


def ascensor(segundos: float, cambios: list[float], ffmpeg: str = "ffmpeg") -> Mezcla:
    I = {k: Instrumento(k, ffmpeg=ffmpeg, **kw) for k, kw in {
        "guitarra_nylon": dict(suelta=0.15, gan=0.9), "rhodes": dict(suelta=0.4, gan=0.75),
        "bajo_acustico": dict(suelta=0.12), "vibrafono": dict(suelta=0.6, gan=0.8),
        "acordeon": dict(ataque=0.03, suelta=0.12, gan=0.85), "clarinete": dict(ataque=0.05, suelta=0.15, gan=0.85),
        "flauta": dict(ataque=0.06, suelta=0.2), "fagot_stac": dict(suelta=0.12, gan=0.7),
        "violines_pizz": dict(suelta=0.2, gan=0.7), "cuerdas_lentas": dict(ataque=0.5, suelta=0.8, gan=0.6),
        "glock": dict(suelta=0.6, gan=0.4)}.items()}
    bat = {n: golpe(n, ffmpeg) for n in ("bombo", "aro", "charles", "shaker", "triangulo", "campana_ride")}
    m = Mezcla(segundos)
    negra = 60 / 112
    corchea, compas = negra / 2, 4 * negra
    compases = []
    while len(compases) * compas < segundos + 2:
        for nombre, sec, voz in (FORMA if not compases else FORMA[1:]):
            compases += [(nombre, c, voz) for c in sec]
    trozos = [(k, j, s) for k, (_n, (acs, _m), _v) in enumerate(compases) for j, s in enumerate(acs)]
    voicings = conducir([s for _k, _j, s in trozos], centro=64)
    voz_de = {(k, j): v for (k, j, _s), v in zip(trozos, voicings)}
    linea = guias([acs[0] for _n, (acs, _m), _v in compases], [mel for _n, (_a, mel), _v in compases])

    for k, (sec, (acs, mel), voz) in enumerate(compases):
        t0 = k * compas
        if t0 > segundos:
            break
        par = k % 2 == 0
        # ---- el marco: la sección rítmica de bossa, siempre igual de pulida
        for j, s in enumerate(acs):
            ta = t0 + j * 4 * corchea * (2 // len(acs))
            mitad = len(acs) > 1
            raiz = acorde(s)[0]
            b = _bajo(raiz)
            quinta = b + 7 if b + 7 <= 47 else b - 5
            # Bajo de bossa: 1 (con puntillo) y la quinta en el «y» del 2; lo mismo en el 3 y el 4.
            golpes = [(0, b, 3), (3, quinta, 1)] if mitad else [(0, b, 3), (3, quinta, 1), (4, b, 3), (7, quinta, 1)]
            if not mitad and k + 1 < len(compases):
                sig = _bajo(acorde(compases[k + 1][1][0][0])[0])
                golpes[-1] = (7, sig + (1 if sig < b else -1), 1)   # aproximación cromática al siguiente
            for c, n, larg in golpes:
                m.poner(ta + c * corchea, I["bajo_acustico"].nota(n, larg * corchea * 0.9, 0.9), 0.55, -0.05)
            v = voz_de[(k, j)]
            # Rhodes: el voicing entero, tumbado, al empezar cada acorde.
            for q, n in enumerate(v):
                m.poner(ta + 0.008 * q, I["rhodes"].nota(n, (2 if mitad else 4) * negra * 0.95, 0.45), 0.4, -0.3 + 0.15 * q)
            # Guitarra de nailon: el patrón de bossa (dos compases), acordes cortos a contratiempo.
            patron = ([0, 2, 5, 7] if par else [1, 4, 6]) if not mitad else ([1, 3] if j == 0 else [0, 2])
            for c in patron:
                for q, n in enumerate(v[1:]):
                    m.poner(ta + c * corchea + 0.012 * q, I["guitarra_nylon"].nota(n, corchea * 0.9, 0.55), 0.45, 0.3 - 0.05 * q)
        # Batería: aro en la clave de bossa, charles en corcheas, bombo suave, maraca.
        for c in ([0, 3, 6] if par else [2, 4]):
            m.poner(t0 + c * corchea, bat["aro"][: int(0.25 * 44100)], 0.22, -0.2)
        for c in range(8):
            m.poner(t0 + c * corchea, bat["charles"][: int(0.12 * 44100)], 0.10 if c % 2 else 0.06, 0.35)
            m.poner(t0 + c * corchea + corchea / 2, bat["shaker"][: int(0.15 * 44100)], 0.05, 0.5)
        for c in (0, 3, 4):
            m.poner(t0 + c * corchea, bat["bombo"], 0.2 if c != 3 else 0.12, 0)
        if k % 8 == 0 and sec != "intro":
            m.poner(t0, bat["campana_ride"][: int(1.5 * 44100)], 0.07, 0.4)

        # ---- los colores, por secciones
        if voz:
            inst = I[voz]
            baja = 12 if voz == "clarinete" else 0
            for c, nota, larg in mel:
                dur = larg * corchea * (0.95 if larg > 1 else 0.75)
                m.poner(t0 + c * corchea, inst.nota(nota - baja, dur, 0.85), 0.9, 0.05)
                if sec == "final":     # flauta y vibráfono al unísono
                    m.poner(t0 + c * corchea, I["vibrafono"].nota(nota, dur, 0.6), 0.45, -0.15)
        # Layton: el clarinete contesta con las notas guía; Dark Chronicle: el acordeón hace lo mismo.
        if sec in ("layton", "taller") and mel:
            g = I["clarinete"] if sec == "layton" else I["acordeon"]
            m.poner(t0 + 2 * negra, g.nota(linea[k], negra * 1.8, 0.55), 0.5, -0.3)
        # Dark Chronicle: fagot staccato con el bajo y pizzicatos de violín en el 2 y el 4.
        if sec == "taller":
            raiz = acorde(acs[0])[0]
            for c, n in ((0, _bajo(raiz) + 12), (4, _bajo(raiz) + 19)):
                m.poner(t0 + c * corchea, I["fagot_stac"].nota(n, corchea * 0.9, 0.6), 0.45, -0.35)
            for c in (2, 6):
                for q, n in enumerate(voz_de[(k, 0 if c == 2 else len(acs) - 1)][1:]):
                    m.poner(t0 + c * corchea, I["violines_pizz"].nota(n + 12, corchea * 0.8, 0.5), 0.28, 0.45 - 0.1 * q)
        # El final, lujoso: colchón de cuerdas con el voicing una octava arriba.
        if sec == "final":
            for j in range(len(acs)):
                for q, n in enumerate(voz_de[(k, j)]):
                    m.poner(t0 + j * 2 * negra, I["cuerdas_lentas"].nota(n + 12, (4 // len(acs)) * negra, 0.4), 0.3,
                            -0.4 + 0.25 * q, humano=0)
        # Cierre de frase: el glockenspiel arpegia el acorde que suena.
        if mel and k % 4 == 3:
            v = voz_de[(k, len(acs) - 1)]
            for d, n in enumerate(v[::-1][:3]):
                m.poner(t0 + 6 * corchea + d * corchea / 2, I["glock"].nota(n + 24, 0.4, 0.5), 0.3, 0.3)
    # Cambio de escena: el acorde que suena, en arpegio de vibráfono y glockenspiel, y el triángulo.
    for t in cambios:
        k = min(int(t / compas), len(compases) - 1)
        v = voz_de[(k, 0)]
        m.poner(t, bat["triangulo"], 0.12, 0.4, humano=0)
        for d, n in enumerate(v):
            m.poner(t + d * 0.055, I["vibrafono"].nota(n + 12, 0.8, 0.6), 0.4, -0.2 + 0.15 * d, humano=0)
            m.poner(t + d * 0.055, I["glock"].nota(n + 24, 0.5, 0.5), 0.25, 0.3, humano=0)
    m.sala(1.3, 0.2, 7000)
    return m



# ---------------------------------------------------------------- vals (Layton)

D, E, F, G, A, Bb, C, Cs = 62, 64, 65, 67, 69, 70, 72, 73
# Acorde: bajo (MIDI) y notas del acompañamiento (registro medio).
VALS_ACORDES = {
    "Dm": (38, (57, 62, 65)), "Dm/C": (36, (57, 62, 65)), "Gm": (43, (58, 62, 67)), "Gm/Bb": (46, (58, 62, 67)),
    "Gm6": (43, (58, 64, 67)), "A7": (45, (57, 61, 67)), "Bbmaj7": (46, (57, 62, 65)), "Em7b5": (40, (58, 62, 67)),
    "F": (41, (57, 60, 65)), "C7/E": (40, (58, 60, 64)), "Fmaj7": (41, (57, 60, 64)), "Bb": (46, (58, 62, 65)),
    "Gm7": (43, (58, 62, 65)), "C7": (36, (58, 60, 64)), "F/A": (45, (57, 60, 65)), "Bbm6": (46, (58, 61, 67)),
    "F/C": (36, (57, 60, 65)),
}
# Cada compás: acorde y melodía como (corchea 0-5, nota, corcheas).
VALS_A = [
    ("Dm", [(0, 74, 2), (2, 76, 2), (4, 77, 2)]), ("Dm", [(0, 81, 5), (5, 79, 1)]),
    ("Gm", [(0, 82, 2), (2, 81, 2), (4, 79, 2)]), ("A7", [(0, 76, 4), (4, 73, 2)]),
    ("Dm", [(0, 74, 2), (2, 76, 2), (4, 77, 2)]), ("Dm/C", [(0, 84, 4), (4, 82, 1), (5, 81, 1)]),
    ("Bbmaj7", [(0, 81, 2), (2, 79, 2), (4, 77, 2)]), ("Em7b5", [(0, 79, 3), (3, 77, 1), (4, 76, 2)]),
    ("A7", [(0, 73, 2), (2, 76, 2), (4, 79, 2)]), ("A7", [(0, 82, 4), (4, 81, 2)]),
    ("Dm", [(0, 77, 2), (2, 76, 2), (4, 74, 2)]), ("Gm/Bb", [(0, 79, 4), (4, 77, 1), (5, 76, 1)]),
    ("Gm6", [(0, 76, 2), (2, 77, 2), (4, 79, 2)]), ("A7", [(0, 73, 4), (4, 69, 2)]),
    ("Dm", [(0, 74, 6)]), ("A7", [(4, 69, 1), (5, 73, 1)]),
]
VALS_B = [
    ("F", [(0, 81, 2), (2, 84, 2), (4, 81, 2)]), ("C7/E", [(0, 79, 6)]),
    ("Fmaj7", [(0, 76, 2), (2, 77, 2), (4, 81, 2)]), ("Bb", [(0, 86, 5), (5, 84, 1)]),
    ("Gm7", [(0, 82, 2), (2, 81, 2), (4, 79, 2)]), ("C7", [(0, 76, 3), (3, 79, 1), (4, 82, 2)]),
    ("F", [(0, 81, 4), (4, 77, 2)]), ("A7", [(0, 76, 2), (2, 73, 2), (4, 69, 2)]),
    ("Dm", [(0, 74, 2), (2, 77, 2), (4, 81, 2)]), ("Bbmaj7", [(0, 86, 4), (4, 84, 2)]),
    ("Gm7", [(0, 82, 2), (2, 79, 2), (4, 76, 2)]), ("C7", [(0, 79, 4), (4, 76, 2)]),
    ("F/A", [(0, 77, 2), (2, 76, 2), (4, 77, 2)]), ("Bbm6", [(0, 77, 3), (3, 73, 1), (4, 70, 2)]),
    ("F/C", [(0, 72, 2), (2, 76, 2), (4, 79, 2)]), ("A7", [(0, 79, 2), (2, 76, 2), (4, 73, 1), (5, 69, 1)]),
]


def vals(segundos: float, cambios: list[float], ffmpeg: str = "ffmpeg") -> Mezcla:
    I = {k: Instrumento(k, ffmpeg=ffmpeg, **kw) for k, kw in {
        "acordeon": dict(ataque=0.03, suelta=0.12, gan=0.9), "clarinete": dict(ataque=0.04, suelta=0.15),
        "contrabajo_pizz": dict(suelta=0.3), "violines_pizz": dict(suelta=0.25, gan=0.8),
        "violines": dict(ataque=0.35, suelta=0.6, gan=0.5), "glock": dict(suelta=0.6, gan=0.5),
        "celesta": dict(suelta=0.5, gan=0.6)}.items()}
    m = Mezcla(segundos)
    negra = 60 / 162
    corchea, compas = negra / 2, 3 * negra
    intro = [(a, []) for a, _ in VALS_A[:4]]
    forma = [("A", VALS_A, "acordeon"), ("A2", VALS_A, "acordeon"), ("B", VALS_B, "clarinete"), ("A", VALS_A, "acordeon")]
    compases = [("intro", c, None) for c in intro]
    while len(compases) * compas < segundos + 2:
        for nombre, sec, voz in forma:
            compases += [(nombre, c, voz) for c in sec]
    for k, (sec, (acorde, melodia), voz) in enumerate(compases):
        t0 = k * compas
        if t0 > segundos:
            break
        bajo, notas = VALS_ACORDES[acorde]
        # Um-pa-pa: contrabajo en el uno (fundamental o quinta, un compás sí y otro no), pizzicato en el dos y el tres.
        b = bajo if k % 2 == 0 or acorde.endswith(("/C", "/Bb", "/E", "/A")) else bajo + 7 - (12 if bajo + 7 > 50 else 0)
        m.poner(t0, I["contrabajo_pizz"].nota(b, negra * 1.6, 0.95), 0.9, -0.1)
        for pulso in (1, 2):
            for q, n in enumerate(notas):
                m.poner(t0 + pulso * negra + 0.004 * q, I["violines_pizz"].nota(n, negra * 0.5, 0.6 if pulso == 1 else 0.5), 0.45, 0.35 - 0.1 * q)
        # Cuerdas que sostienen el acorde en la segunda A y en la B: el colchón.
        if sec in ("A2", "B"):
            for q, n in enumerate(notas):
                m.poner(t0, I["violines"].nota(n + 12, compas * 1.02, 0.35), 0.35, -0.4 + 0.3 * q, humano=0)
        if voz:
            for c, nota, largo in melodia:
                dur = largo * corchea * 0.96
                m.poner(t0 + c * corchea, I[voz].nota(nota - (12 if voz == "clarinete" else 0), dur, 0.85), 0.95, 0.05)
                # En la segunda A, el glockenspiel dobla las notas largas una octava arriba.
                if sec == "A2" and largo >= 4:
                    m.poner(t0 + c * corchea, I["glock"].nota(nota + 12, 0.4, 0.5), 0.5, 0.25)
            # En la B, el acordeón contesta con la tercera de abajo en las notas largas.
            if sec == "B":
                for c, nota, largo in melodia:
                    if largo >= 3:
                        m.poner(t0 + c * corchea, I["acordeon"].nota(nota - 3, largo * corchea, 0.5), 0.45, -0.25)
    for t in cambios:
        for d, n in enumerate((86, 89, 93, 98)):
            m.poner(t + d * 0.06, I["celesta"].nota(n, 0.5, 0.6), 0.45, 0.3, humano=0)
    m.sala(1.6, 0.28, 5500)
    return m


# ---------------------------------------------------------------- taller (Dark Chronicle)

TALLER_ACORDES = {
    "Ab": (44, (60, 63, 68)), "Fm": (41, (60, 65, 68)), "Db": (49, (61, 65, 68)), "Eb7": (39, (61, 63, 67)),
    "C7": (48, (58, 64, 67)), "Bbm7": (46, (61, 65, 68)), "Dbm": (49, (61, 64, 68)), "F7": (41, (60, 63, 69)),
    "Ab/C": (48, (60, 63, 68)),
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


def taller(segundos: float, cambios: list[float], ffmpeg: str = "ffmpeg") -> Mezcla:
    I = {k: Instrumento(k, ffmpeg=ffmpeg, **kw) for k, kw in {
        "acordeon": dict(ataque=0.025, suelta=0.1), "clarinete_stac": dict(suelta=0.12),
        "clarinete": dict(ataque=0.03, suelta=0.12), "fagot_stac": dict(suelta=0.15),
        "contrabajo_pizz": dict(suelta=0.25), "violines_pizz": dict(suelta=0.2, gan=0.8),
        "glock": dict(suelta=0.5, gan=0.5)}.items()}
    claves = golpe("claves", ffmpeg)
    shaker = golpe("maraca", ffmpeg)
    m = Mezcla(segundos)
    negra = 60 / 104
    corchea, compas, swing = negra / 2, 4 * negra, 0.58
    cs = lambda k: (k // 2) * negra + (swing * negra if k % 2 else 0)
    intro = [(a, []) for a, _ in TALLER_A[:2]]
    compases = [("intro", c) for c in intro]
    while len(compases) * compas < segundos + 2:
        for nombre, sec in (("A", TALLER_A), ("A2", TALLER_A), ("B", TALLER_B), ("A", TALLER_A)):
            compases += [(nombre, c) for c in sec]
    for k, (sec, (acordes, melodia)) in enumerate(compases):
        t0 = k * compas
        if t0 > segundos:
            break
        por = 4 // len(acordes)
        for j, nombre in enumerate(acordes):
            bajo, notas = TALLER_ACORDES[nombre]
            ta = t0 + j * por * negra
            linea = [bajo, bajo + 7, bajo + 12, bajo + 6][:por] if por == 4 else [bajo, bajo + 7]
            for b, n in enumerate(linea):
                m.poner(ta + b * negra, I["contrabajo_pizz"].nota(n - 12 if n > 47 else n, negra * 0.9, 0.9), 0.8, -0.1)
                m.poner(ta + b * negra, I["fagot_stac"].nota(n + (12 if n < 40 else 0), negra * 0.5, 0.7), 0.5, -0.3)
            # El acordeón hace el acorde a contratiempo (charlestón de taberna), los pizzicatos en 2 y 4.
            for q, n in enumerate(notas):
                for g in ((0.5, 0.55), (2.5, 0.45))[: (2 if por == 4 else 1)]:
                    m.poner(ta + g[0] * negra + (swing - 0.5) * negra, I["acordeon"].nota(n, negra * 0.35, g[1]), 0.35, 0.2 + 0.1 * q)
                for b in (1, 3)[: por // 2]:
                    m.poner(ta + b * negra, I["violines_pizz"].nota(n + 12, negra * 0.4, 0.45), 0.3, 0.4)
        voz = "acordeon" if sec in ("A", "intro") else "clarinete"
        for c, nota, largo in melodia:
            dur = largo * corchea * (0.9 if largo > 1 else 0.6)
            inst = I["clarinete_stac"] if voz == "clarinete" and largo == 1 else I[voz]
            m.poner(t0 + cs(c), inst.nota(nota - (12 if voz == "clarinete" else 0), dur, 0.85), 0.9, 0.0)
        if melodia and k % 2 == 1:
            n = melodia[-1][1]
            for d, s in enumerate((0, 7, 12)):
                m.poner(t0 + 3 * negra + d * corchea / 2, I["glock"].nota(n + 12 + s, 0.3, 0.5), 0.4, 0.3)
        for b in (1, 3):
            m.poner(t0 + b * negra, claves, 0.25, -0.35)
        for c in range(8):
            m.poner(t0 + cs(c), shaker, 0.06 if c % 2 == 0 else 0.1, 0.45)
    for t in cambios:
        for d, n in enumerate((80, 84, 87, 92)):
            m.poner(t + d * 0.05, I["glock"].nota(n + 12, 0.4, 0.5), 0.45, 0.3, humano=0)
    m.sala(1.2, 0.22, 6000)
    return m


# ---------------------------------------------------------------- cuento (Spirit King)

CUENTO_ACORDES = {"Cm": (48, (0, 3, 7)), "Ab": (44, (0, 4, 7)), "Fm": (41, (0, 3, 7)), "G7": (43, (0, 4, 7, 10)),
                  "Eb": (51, (0, 4, 7)), "G": (43, (0, 4, 7)), "Bb": (46, (0, 4, 7))}
CUENTO_FORMA = ["Cm", "Cm", "Ab", "Ab", "Fm", "Fm", "G7", "G7", "Cm", "Cm", "Eb", "Bb", "Fm", "Ab", "G", "G"]
CUENTO_FLAUTA = [
    [(0, 75, 6), (6, 74, 2)], [(0, 72, 8)], [(0, 72, 4), (4, 75, 4)], [(0, 80, 6), (6, 79, 2)],
    [(0, 77, 4), (4, 80, 4)], [(0, 84, 6), (6, 82, 2)], [(0, 83, 4), (4, 79, 4)], [(0, 77, 4), (4, 74, 4)],
    [(0, 75, 3), (3, 74, 1), (4, 72, 4)], [(0, 67, 8)], [(0, 70, 4), (4, 75, 4)], [(0, 74, 6), (6, 77, 2)],
    [(0, 77, 4), (4, 80, 4)], [(0, 84, 4), (4, 82, 2), (6, 80, 2)], [(0, 79, 8)], [(0, 74, 4), (4, 71, 4)],
]


def cuento(segundos: float, cambios: list[float], ffmpeg: str = "ffmpeg") -> Mezcla:
    I = {k: Instrumento(k, ffmpeg=ffmpeg, **kw) for k, kw in {
        "arpa": dict(suelta=0.45), "caja_musica": dict(suelta=0.8, gan=0.8), "chelos": dict(ataque=0.5, suelta=0.8, gan=0.7),
        "flauta": dict(ataque=0.08, suelta=0.3), "celesta": dict(suelta=0.8), "oboe": dict(ataque=0.06, suelta=0.25)}.items()}
    m = Mezcla(segundos)
    negra = 60 / 117
    corchea, compas = negra / 2, 4 * negra
    k = 0
    while k * compas < segundos:
        t0 = k * compas
        vuelta, j = divmod(k - 4, 16) if k >= 4 else (-1, k)
        raiz, ints = CUENTO_ACORDES[CUENTO_FORMA[j]]
        r = raiz + 12 if raiz < 48 else raiz
        giro = [0, 7, ints[1] + 12, 7, 12, 7, ints[1], 7] if j % 2 == 0 else [12, ints[1] + 12, 7, ints[1], 0, 7, 12, 19]
        for q, s in enumerate(giro):
            m.poner(t0 + q * corchea, I["arpa"].nota(r + s, corchea * 1.3, 0.75 if q % 2 == 0 else 0.6), 0.75, -0.25 + 0.1 * (q % 3))
            if vuelta >= 0 and vuelta % 2 == 1:
                m.poner(t0 + q * corchea, I["caja_musica"].nota(r + s + 12, corchea * 1.3, 0.5), 0.2, 0.35)
        if j % 2 == 0:
            m.poner(t0, I["chelos"].nota(raiz - 12, 2 * compas, 0.6), 0.55, -0.1, humano=0)
            m.poner(t0, I["chelos"].nota(raiz - 5, 2 * compas, 0.45), 0.35, 0.15, humano=0)
        if vuelta >= 0:
            voz = I["flauta"] if vuelta % 2 == 0 else I["oboe"]
            for c, nota, largo in CUENTO_FLAUTA[j]:
                m.poner(t0 + c * corchea, voz.nota(nota, largo * corchea * 0.97, 0.75), 0.75, 0.1)
        k += 1
    for t in [0.0, *cambios]:
        for d, n in enumerate((84, 91, 96)):
            m.poner(t + d * 0.09, I["celesta"].nota(n, 1.2, 0.6), 0.4, 0.2 - 0.2 * d, humano=0)
    m.sala(2.0, 0.27, 4200)
    return m
