"""Los idiomas de cronica: inglés por defecto, español con --lang es (o CRONICA_LANG=es).

Los textos se escriben en español en el código y `_()` los traduce: la tabla va de la plantilla en español
a la inglesa. Lo que lee el reproductor (palabras del vídeo, fechas, el lapso del cierre) se calcula aquí y
viaja en datos.json, así que una estética propia sale traducida sin saber de idiomas.
"""
from __future__ import annotations

import os
from datetime import date

IDIOMAS = ("en", "es")
idioma = os.environ.get("CRONICA_LANG", "en") if os.environ.get("CRONICA_LANG") in IDIOMAS else "en"


def poner(nuevo: str) -> None:
    global idioma
    if nuevo not in IDIOMAS:
        raise ValueError(f"unknown language: {nuevo} ({', '.join(IDIOMAS)})")
    idioma = nuevo


def _(texto: str, **kw) -> str:
    plantilla = texto if idioma == "es" else EN.get(texto, texto)
    return plantilla.format(**kw) if kw else plantilla


# ---------------------------------------------------------------- fechas

MESES = {"es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(),
         "en": "January February March April May June July August September October November December".split()}
CORTOS = {"es": "ENE FEB MAR ABR MAY JUN JUL AGO SEP OCT NOV DIC".split(),
          "en": "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()}
DIAS = {"es": "lunes martes miércoles jueves viernes sábado domingo".split(),
        "en": "Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split()}


def _d(f: str) -> date:
    return date.fromisoformat(f[:10])


def fecha_corta(f: str) -> str:
    """«9 JUN 2026»."""
    d = _d(f)
    return f"{d.day} {CORTOS[idioma][d.month - 1]} {d.year}"


def fecha_sin_dia(f: str) -> str:
    """«9 de junio de 2026» / «June 9, 2026»."""
    d = _d(f)
    mes = MESES[idioma][d.month - 1]
    return f"{d.day} de {mes} de {d.year}" if idioma == "es" else f"{mes} {d.day}, {d.year}"


def fecha_larga(f: str) -> str:
    """«Martes, 9 de junio de 2026» / «Tuesday, June 9, 2026»."""
    return f"{DIAS[idioma][_d(f).weekday()].capitalize()}, {fecha_sin_dia(f)}"


def rango(a: str, b: str) -> str:
    """«Del 2 de marzo al 23 de junio de 2026» / «From March 2 to June 23, 2026»."""
    da, db = _d(a), _d(b)
    if da == db:
        return ("El " if idioma == "es" else "On ") + fecha_sin_dia(b)
    if idioma == "es":
        ini = f"{da.day} de {MESES['es'][da.month - 1]}" + (f" de {da.year}" if da.year != db.year else "")
        return f"Del {ini} al {fecha_sin_dia(b)}"
    ini = f"{MESES['en'][da.month - 1]} {da.day}" + (f", {da.year}" if da.year != db.year else "")
    return f"From {ini} to {fecha_sin_dia(b)}"


_NUMEROS = {"es": ["", "Un", "Dos", "Tres", "Cuatro", "Cinco", "Seis", "Siete", "Ocho", "Nueve", "Diez", "Once", "Doce"],
            "en": ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve"]}
_UNIDADES = {"es": {"dia": ("día", "días"), "semana": ("semana", "semanas"), "mes": ("mes", "meses"), "ano": ("año", "años")},
             "en": {"dia": ("day", "days"), "semana": ("week", "weeks"), "mes": ("month", "months"), "ano": ("year", "years")}}


def lapso(a: str, b: str) -> str:
    """«Tres semanas», «Un mes», «Four months»… entre dos fechas AAAA-MM-DD."""
    dias = max(1, (_d(b) - _d(a)).days)
    unidad, n = (("dia", dias) if dias < 14 else ("semana", round(dias / 7)) if dias < 60
                 else ("mes", round(dias / 30.4)) if dias < 730 else ("ano", round(dias / 365)))
    sing, plur = _UNIDADES[idioma][unidad]
    palabra = _NUMEROS[idioma][n] if n <= 12 else str(n)
    if idioma == "es" and n == 1 and unidad == "semana":
        palabra = "Una"
    return f"{palabra} {sing if n == 1 else plur}"


def reproductor() -> dict:
    """Las palabras del vídeo, para datos.json. {i}, {n}, {p}… se rellenan en el reproductor."""
    claves = ("Noticiario del proyecto", "Crónica de {p}", "Núm. {i} de {n}", "NÚM. {i}", "Edición en directo",
              "EN DIRECTO", "Nuevo", "Cambia", "Foto", "En cifras", "Hemeroteca", "Última edición", "Fin",
              "{n} número", "{n} números", "{lapso} de {p}", "Acto", "{n} cambios en la interfaz",
              "líneas", "ficheros", "líneas al llegar", "ficheros al llegar",
              "{a} de los {b} ficheros llegan idénticos", "{n} líneas que ya existían", "{n} líneas extraídas",
              "{n} fichero…", "{n} ficheros…")
    return {"lang": idioma, "locale": "es-ES" if idioma == "es" else "en-US", "t": {k: _(k) for k in claves}}


# ---------------------------------------------------------------- de la plantilla en español a la inglesa

EN = {
    # el vídeo
    "Noticiario del proyecto": "Project newsreel",
    "Crónica de {p}": "The {p} Chronicle",
    "Núm. {i} de {n}": "No. {i} of {n}",
    "NÚM. {i}": "NO. {i}",
    "Edición en directo": "Live edition",
    "EN DIRECTO": "LIVE",
    "Nuevo": "New",
    "Cambia": "Changed",
    "Foto": "Photo",
    "En cifras": "By the numbers",
    "Hemeroteca": "Archive",
    "Última edición": "Final edition",
    "Fin": "The End",
    "{n} número": "{n} issue",
    "{n} números": "{n} issues",
    "{lapso} de {p}": "{lapso} of {p}",
    "Acto": "Act",
    "{n} cambios en la interfaz": "{n} interface changes",
    "líneas": "lines",
    "ficheros": "files",
    "líneas al llegar": "lines on arrival",
    "ficheros al llegar": "files on arrival",
    "{a} de los {b} ficheros llegan idénticos": "{a} of the {b} files arrive unchanged",
    "{n} líneas que ya existían": "{n} lines that already existed",
    "{n} líneas extraídas": "{n} lines extracted",
    "{n} fichero…": "{n} file…",
    "{n} ficheros…": "{n} files…",
    "Componentes": "Components",
    "Stories": "Stories",
    "Ficheros": "Files",
    "Líneas": "Lines",
    "Commits": "Commits",
    "Pantallas": "Screens",
    "Autores": "Authors",
    "Marco": "Frame",
    "inicio": "home",
    "estatico": "static",
    "el Storybook": "the Storybook",
    "la interfaz": "the interface",
    "Extracción: {que} se muda a {a}": "Extraction: {que} moves to {a}",
    "Todo junto: {n} componentes": "All together: {n} components",
    "{n} componentes · {p}": "{n} components · {p}",
    # la consola
    "  Falta el Chromium de Playwright; lo descargo (una sola vez, ~150 MB)…":
        "  Playwright's Chromium is missing; downloading it (once, ~150 MB)…",
    "\nInterrumpido. Lo hecho queda en caché: al relanzar sigue donde lo dejó.":
        "\nInterrupted. What was done stays cached: run it again and it carries on from there.",
    "\nPulsa Intro para cerrar…": "\nPress Enter to close…",
    "Uso: cronica <carpeta del proyecto> [<carpeta del repositorio al que se mudó> …]\n"
    "     (o arrastra la carpeta sobre cronica.exe)":
        "Usage: cronica <project folder> [<folder of the repository it moved to> …]\n"
        "       (or drag the folder onto cronica.exe)",
    "«{c}» no es una carpeta con un repositorio git.": "«{c}» is not a folder with a git repository.",
    "Falta ffmpeg. En Windows: winget install Gyan.FFmpeg · en Linux: el paquete ffmpeg.":
        "ffmpeg is missing. On Windows: winget install Gyan.FFmpeg · on Linux: the ffmpeg package.",
    "  Hacen falta al menos dos hitos que se puedan fotografiar. Mira los logs de arriba.":
        "  At least two milestones that can be photographed are needed. See the logs above.",
    "\n  {n} fotogramas en {d}": "\n  {n} frames in {d}",
    "  rótulos editables: {f}": "  editable headlines: {f}",
    "  {n} escenas, {s} s de vídeo": "  {n} scenes, {s} s of film",
    "\nHecho en {m} min: {f}": "\nDone in {m} min: {f}",
    "  Para cambiar los textos, edita {f} y relanza (todo lo demás sale de la caché).":
        "  To change the headlines, edit {f} and run again (everything else comes from the cache).",
    "  La rama no tiene commits.": "  The branch has no commits.",
    "  {n} commits en {r} ({a} → {b})": "  {n} commits on {r} ({a} → {b})",
    "  No encuentro una interfaz que fotografiar: ni Storybook, ni una app web con build o servidor de\n"
    "  desarrollo, ni un index.html. cronica solo hace vídeos de proyectos con interfaz.":
        "  No interface to photograph: no Storybook, no web app with a build or a dev server, and no\n"
        "  index.html. cronica only films projects with an interface.",
    "  tipo: {t}{d} · {n} hitos elegidos de {c} candidatos": "  type: {t}{d} · {n} milestones chosen from {c} candidates",
    " en ": " in ",
    "(regrabado, {s} s)": "(re-recorded, {s} s)",
    "(caché)": "(cached)",
    "        · sin foto: {a}": "        · no photo: {a}",
    "\n  paseo por {n} componentes…": "\n  walk through {n} components…",
    "  --demo: no encuentro el build «{s}»": "  --demo: cannot find the build «{s}»",
    "\n  demo de {n} paradas…": "\n  demo with {n} stops…",
    "salta: {m} (log: {l})": "skipped: {m} (log: {l})",
    "sin cambios a la vista: no sale": "nothing changes on screen: no page",
    "{n} nuevas": "{n} new",
    "{n} cambian": "{n} changed",
    "arranque": "first look",
    "ok, {p}; en uso: {f} ({s} s)": "ok, {p}; in use: {f} ({s} s)",
    "  escribiendo los rótulos con el modelo local…": "  writing the headlines with the local model…",
    "no ha podido ({e}); uso los títulos de los commits": "it could not ({e}); using the commit titles",
    "\r  grabando {p} %": "\r  recording {p} %",
    "\r  grabando 100 %": "\r  recording 100 %",
    "ffmpeg falló al codificar el vídeo": "ffmpeg failed to encode the film",
    "ffmpeg falló al poner la música: {e}": "ffmpeg failed to add the music: {e}",
    # motivos (también los de cachés viejas, que se guardaron en español)
    "la página sale vacía": "the page comes out empty",
    "falla la instalación de dependencias": "installing the dependencies fails",
    "el build se abre vacío": "the build opens empty",
    "ni el build ni el servidor de desarrollo dan una página": "neither the build nor the dev server gives a page",
    "el build no deja resultado": "the build leaves no output",
    "sin nada que fotografiar": "nothing to photograph",
    "Ollama no tiene modelos": "Ollama has no models",
    "el modelo devolvió pocos rótulos": "the model returned too few headlines",
    "no se pudo lanzar: {e}\n": "could not start: {e}\n",
    "\n[cronica] tiempo agotado ({s} s)\n": "\n[cronica] timed out ({s} s)\n",
    # la ayuda
    "Hace el vídeo de cómo evolucionó la interfaz de un proyecto git, hito a hito.":
        "Makes the film of how the interface of a git project evolved, milestone by milestone.",
    "la carpeta del proyecto (un repositorio git); si se mudó a otro repositorio, también esa, en orden. "
    "«carpeta@rama» elige la rama de cada una":
        "the project folder (a git repository); if it moved to another repository, that one too, in order. "
        "«folder@branch» picks the branch of each",
    "idioma de la consola y del vídeo: en (por defecto) o es": "language of the console and the film: en (default) or es",
    "el mp4 (por defecto, <carpeta>-evolucion.mp4 al lado del proyecto)":
        "the mp4 (by default, <folder>-evolution.mp4 next to the project)",
    "escenas como mucho (30)": "scenes at most (30)",
    "la rama que se recorre (por defecto, la que está activa)": "the branch to walk (by default, the active one)",
    "qué se fotografía; auto = Storybook si lo hay, si no la app, si no un index.html":
        "what is photographed; auto = Storybook if there is one, else the app, else an index.html",
    "rótulos escritos por un modelo (el de los ajustes; si no, Ollama en :11434 o CRONICA_LLM=http://…/v1)":
        "headlines written by a model (the one in the settings; otherwise Ollama on :11434 or CRONICA_LLM=http://…/v1)",
    "abre la redacción: la ventana donde se eligen el idioma, el modelo de IA, la música y la estética":
        "opens the newsroom: the window where you choose the language, the AI model, the music and the look",
    "La redacción está en {u} (cierra la ventana para terminar).":
        "The newsroom is at {u} (close the window to finish).",
    "Pulsa Intro cuando hayas terminado…": "Press Enter when you are done…",
    "la música: un estilo generado (console, por defecto; newsreel; ambient) o un fichero de audio propio":
        "the music: a generated style (console, the default; newsreel; ambient) or an audio file of your own",
    "sin música": "no music",
    "segundos como mucho de app en uso por hito (6)": "seconds of app in use per milestone, at most (6)",
    "no graba el vídeo: deja fotogramas sueltos para revisar": "no film: leaves single frames to review",
    "vuelve a construir los hitos que fallaron": "builds again the milestones that failed",
    "vuelve a grabar la app en uso desde los sitios ya construidos (sin build)":
        "records the app in use again from the sites already built (no build)",
    "borra la caché de este proyecto antes de empezar": "deletes this project's cache before starting",
    "carpeta de trabajo (por defecto, en la caché del usuario)": "working folder (by default, in the user's cache)",
    "orden que se ejecuta tras instalar y antes de construir («repo=orden» para uno solo)":
        "command run after installing and before building («repo=command» for just one)",
    "un repositorio que no sale en pantalla pero cuenta en las cifras (carpeta o carpeta@rama)":
        "a repository that is not on screen but counts in the figures (folder or folder@branch)",
    "al final, un paseo por todos los componentes cambiando los temas de la barra (60 s)":
        "at the end, a walk through every component switching the toolbar's themes (60 s)",
    "al final, una demo guiada de Storybook: paradas, acciones y segundos de cada una":
        "at the end, a guided Storybook demo: stops, actions and seconds for each",
    "el nombre con el que sale un repositorio en el vídeo (p. ej. si se ha renombrado)":
        "the name a repository appears under in the film (e.g. if it was renamed)",
    "una cifra que no sale en el vídeo (se puede repetir): p. ej. --hide lines":
        "a figure that does not appear in the film (repeatable): e.g. --hide lines",
    "cómo se ve el vídeo: newspaper (por defecto) o classic, o la ruta de un .html propio":
        "how the film looks: newspaper (default) or classic, or the path of your own .html",
    "--look: «{e}» no es newspaper ni classic ni un .html que exista":
        "--look: «{e}» is not newspaper, classic or an existing .html",
    "--music: «{e}» no es console, newsreel ni ambient ni un fichero que exista":
        "--music: «{e}» is not console, newsreel, ambient or an existing file",
    "--hide: «{e}» no es una cifra ({c})": "--hide: «{e}» is not a figure ({c})",
}
