"""The example project of the README: «Garden», a static web page that grows over nine pull requests.

    python examples/garden/construir.py [folder] [--lang en|es]     (default: ./garden, in English)
    cronica garden

    python examples/garden/construir.py huerto --lang es            (the same history, in Spanish)
    cronica huerto --lang es

Every pull request changes something you can see: a new screen, dark mode, a redesign. Dates and authors are
fixed, so the repository, its hashes and the film come out the same every time.
"""
import argparse
import os
import shutil
import stat
import subprocess
from pathlib import Path

# ---------------------------------------------------------------- drawings

DIBUJOS = {
    "tomate": '<circle cx="32" cy="38" r="20" fill="#E0442E"/><path d="M32 14l4 8 8-2-6 6 6 4-9-1-3 7-3-7-9 1 6-4-6-6 8 2z" fill="#3E8E41"/>',
    "lechuga": '<ellipse cx="32" cy="40" rx="24" ry="16" fill="#7CC36A"/><ellipse cx="32" cy="34" rx="16" ry="13" fill="#9BD67E"/><ellipse cx="32" cy="30" rx="8" ry="8" fill="#C4EAA0"/>',
    "zanahoria": '<path d="M24 22l16 0-8 36z" fill="#F08A24"/><path d="M28 22c-4-8-2-12 0-14 2 4 3 8 4 14m0 0c0-8 3-12 6-13 0 5-2 9-4 13" fill="none" stroke="#3E8E41" stroke-width="3"/>',
    "pimiento": '<path d="M18 26c0-6 28-6 28 0 0 14-4 30-14 30S18 40 18 26z" fill="#2F9E44"/><path d="M32 20v-8" stroke="#2B6A2E" stroke-width="4"/>',
    "fresa": '<path d="M14 26c0-6 36-6 36 0 0 14-10 28-18 28S14 40 14 26z" fill="#E03A4E"/><path d="M20 22l6-6 6 6 6-6 6 6" fill="#3E8E41"/><g fill="#FFE08A"><circle cx="24" cy="32" r="1.6"/><circle cx="34" cy="30" r="1.6"/><circle cx="40" cy="38" r="1.6"/><circle cx="28" cy="42" r="1.6"/></g>',
    "cebolla": '<path d="M32 18c14 8 18 18 18 24a18 14 0 0 1-36 0c0-6 4-16 18-24z" fill="#B0628E"/><path d="M32 18c-2-6 0-10 2-12" stroke="#3E8E41" stroke-width="3" fill="none"/>',
    "calabacin": '<rect x="10" y="26" width="44" height="16" rx="8" fill="#3F7D3A" transform="rotate(-20 32 34)"/><circle cx="50" cy="22" r="3" fill="#7A5A2A"/>',
    "albahaca": '<ellipse cx="22" cy="34" rx="10" ry="16" fill="#4CAF50" transform="rotate(-30 22 34)"/><ellipse cx="42" cy="34" rx="10" ry="16" fill="#66BB6A" transform="rotate(30 42 34)"/><path d="M32 58V26" stroke="#2E7D32" stroke-width="3"/>',
}
# drawing, kind, sowing month (1-12), harvest month
PLANTAS = [("tomate", 0, 3, 8), ("lechuga", 1, 2, 5), ("zanahoria", 2, 3, 7), ("pimiento", 0, 3, 9),
           ("fresa", 0, 2, 6), ("cebolla", 2, 1, 6), ("calabacin", 0, 4, 8), ("albahaca", 1, 4, 9)]

# ---------------------------------------------------------------- the words, in each language

TEXTOS = {
    "en": {
        "app": "Garden", "lang": "en",
        "plantas": ["Tomato", "Lettuce", "Carrot", "Pepper", "Strawberry", "Onion", "Courgette", "Basil"],
        "tipos": ["Fruit", "Leaf", "Root"], "todas": "All",
        "meses": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(),
        "dias": "Mon Tue Wed Thu Fri Sat Sun".split(),
        "ficheros": {"plantas": "plants.html", "calendario": "calendar.html", "riego": "watering.html",
                     "ajustes": "settings.html"},
        "menu": {"inicio": "Home", "plantas": "Plants", "calendario": "Calendar", "riego": "Watering",
                 "ajustes": "Settings"},
        "mi": "My garden", "titulo_plantas": "Plants", "titulo_calendario": "Sowing calendar",
        "titulo_riego": "Watering", "titulo_ajustes": "Settings",
        "siembra_en": "sow in {m}", "buscar": "Search a plant…", "ninguna": "No plant has that name.",
        "planta": "Plant", "siembra": "sowing", "cosecha": "harvest",
        "antes": "← Previous week", "luego": "Next week →", "semana": "Week", "litros": "litres",
        "litros_dia": "Litres per day, for the whole garden.",
        "tareas": ["Water the tomatoes", "Tie up the pepper", "Sow basil", "Harvest the lettuce"],
        "hecho": "Done", "deshacer": "Undo", "hoy": "Today", "tiempo": "Weather",
        "prevision": "Sun all morning. No rain until Thursday: time to water.", "humedad": "Humidity 41 % · Wind 9 km/h",
        "ajustes": ["Watering units", "Warn before a frost", "Daily watering reminder", "Reminder time"],
        "unidades": ["Litres", "Gallons"],
        "primero": "First page: the list of plants",
        "prs": ["A header and the garden's colours", "Plant cards with their drawing", "Sowing and harvest calendar",
                "Dark mode", "Filters by kind and a plant search", "The watering chart, week by week",
                "A home page with the weather and today's tasks", "A new typeface and rounded cards",
                "Settings for units and frost alerts"],
    },
    "es": {
        "app": "Huerto", "lang": "es",
        "plantas": ["Tomate", "Lechuga", "Zanahoria", "Pimiento", "Fresa", "Cebolla", "Calabacín", "Albahaca"],
        "tipos": ["Fruto", "Hoja", "Raíz"], "todas": "Todas",
        "meses": "Ene Feb Mar Abr May Jun Jul Ago Sep Oct Nov Dic".split(),
        "dias": "Lun Mar Mié Jue Vie Sáb Dom".split(),
        "ficheros": {"plantas": "plantas.html", "calendario": "calendario.html", "riego": "riego.html",
                     "ajustes": "ajustes.html"},
        "menu": {"inicio": "Inicio", "plantas": "Plantas", "calendario": "Calendario", "riego": "Riego",
                 "ajustes": "Ajustes"},
        "mi": "Mi huerto", "titulo_plantas": "Plantas", "titulo_calendario": "Calendario de siembra",
        "titulo_riego": "Riego", "titulo_ajustes": "Ajustes",
        "siembra_en": "siembra en {m}", "buscar": "Buscar una planta…", "ninguna": "Ninguna planta se llama así.",
        "planta": "Planta", "siembra": "siembra", "cosecha": "cosecha",
        "antes": "← Semana anterior", "luego": "Semana siguiente →", "semana": "Semana", "litros": "litros",
        "litros_dia": "Litros por día, de todo el huerto.",
        "tareas": ["Regar los tomates", "Atar el pimiento", "Sembrar albahaca", "Cosechar lechugas"],
        "hecho": "Hecho", "deshacer": "Deshacer", "hoy": "Hoy", "tiempo": "El tiempo",
        "prevision": "Sol toda la mañana. Sin lluvia hasta el jueves: toca regar.", "humedad": "Humedad 41 % · Viento 9 km/h",
        "ajustes": ["Unidades de riego", "Avisar antes de una helada", "Recordatorio diario de riego", "Hora del recordatorio"],
        "unidades": ["Litros", "Galones"],
        "primero": "Primera página: la lista de plantas",
        "prs": ["Una cabecera y los colores del huerto", "Fichas de plantas con su dibujo", "Calendario de siembra y cosecha",
                "Modo oscuro", "Filtros por tipo y buscador de plantas", "La gráfica del riego, semana a semana",
                "Portada con el tiempo y las tareas de hoy", "Letra nueva y tarjetas redondeadas",
                "Ajustes de unidades y avisos de helada"],
    },
}
T = TEXTOS["en"]


def dibujo(clave: str, tam: int = 64) -> str:
    return f'<svg viewBox="0 0 64 64" width="{tam}" height="{tam}" aria-hidden="true">{DIBUJOS[clave]}</svg>'


# ---------------------------------------------------------------- styles, from worst to best

CSS_0 = "\nbody{font-family:Georgia,serif;margin:24px}\nli{margin:4px 0}\n"

CSS_1 = """
:root{--fondo:#F7F4EC;--tinta:#22301F;--suave:#5C6B57;--verde:#2F6B3A;--claro:#E5EEDC;--borde:#D3DCC8;--tarjeta:#fff}
*{box-sizing:border-box} body{font-family:Georgia,serif;font-size:22px;margin:0;background:var(--fondo);color:var(--tinta)}
header{background:var(--verde);color:#fff;padding:14px 32px;display:flex;align-items:center;gap:32px}
header b{font-size:30px} nav a{color:#E5EEDC;margin-right:24px;text-decoration:none;font-size:22px}
main{padding:32px 40px} h1{margin:0 0 22px;font-size:44px}
ul.lista li{font-size:26px;margin:8px 0}
.rejilla{display:grid;grid-template-columns:repeat(4,1fr);gap:20px}
.ficha{background:var(--tarjeta);border:1px solid var(--borde);padding:14px;text-align:center}.ficha h3{font-size:26px}
.ficha h3{margin:8px 0 4px} .ficha small{color:var(--suave)}
.cal{border-collapse:collapse;width:100%;background:var(--tarjeta)} .cal td,.cal th{border:1px solid var(--borde);padding:10px 4px;text-align:center;font-size:19px}
.cal th:first-child,.cal td:first-child{text-align:left;padding-left:12px;width:200px}
.s{background:#9BD67E} .c{background:#F0A35A}
button,.chip{font:inherit;font-size:20px;border:1px solid var(--verde);background:var(--tarjeta);color:var(--verde);padding:6px 14px;cursor:pointer}
.chip.si{background:var(--verde);color:#fff}
input[type=search],select{font:inherit;font-size:20px;padding:7px 10px;border:1px solid var(--borde);background:var(--tarjeta);color:var(--tinta)}
.barras{display:flex;align-items:flex-end;gap:14px;height:420px;padding:16px;background:var(--tarjeta);border:1px solid var(--borde)}
.barras div{flex:1;background:#4F9BD9;position:relative} .barras span{position:absolute;bottom:-26px;left:0;right:0;text-align:center;font-size:19px;color:var(--suave)}
.panel{display:grid;grid-template-columns:1.2fr 1fr;gap:20px} .caja{background:var(--tarjeta);border:1px solid var(--borde);padding:20px}
.tarea{display:flex;justify-content:space-between;align-items:center;padding:14px 0;border-bottom:1px solid var(--borde);font-size:24px}
.tarea.hecha span{text-decoration:line-through;color:var(--suave)}
.tiempo{font-size:84px;margin:4px 0} .ajuste{display:flex;justify-content:space-between;align-items:center;padding:20px 0;border-bottom:1px solid var(--borde);font-size:24px}
"""

CSS_OSCURO = """
@media (prefers-color-scheme: dark){:root{--fondo:#141A13;--tinta:#E3EADB;--suave:#9AA893;--verde:#7CC36A;--claro:#24301F;--borde:#2E3A2A;--tarjeta:#1C241A}
header{background:#1C2A1A} nav a{color:#B9D9A8} .s{background:#3F7D3A} .c{background:#9A5A1E} .chip.si{color:#141A13}}
"""

CSS_2 = """
body{font-family:"Segoe UI",system-ui,sans-serif}
header{padding:16px 40px;box-shadow:0 2px 12px #0002} header b{font-size:28px;letter-spacing:.5px}
nav a{padding:6px 14px;border-radius:999px;margin-right:6px;font-size:21px} nav a:hover{background:#ffffff22}
main{padding:36px 40px} h1{font-weight:650;letter-spacing:-.5px}
.ficha,.caja,.barras,.cal{border-radius:18px;border:none;box-shadow:0 1px 3px #0001,0 8px 24px #2F6B3A14}
.cal{border-collapse:separate;border-spacing:0;overflow:hidden}
.ficha{padding:22px;transition:transform .2s} .ficha:hover{transform:translateY(-3px)}
button,.chip{border-radius:999px} input[type=search],select{border-radius:12px}
.barras div{border-radius:10px 10px 4px 4px;background:linear-gradient(#6FB4EA,#3D86C6)}
"""


def pagina(titulo: str, cuerpo: str, css: str, nav: list[tuple[str, str]], js: str = "") -> str:
    enlaces = "\n".join(f'<a href="{h}">{t}</a>' for h, t in nav)
    cabecera = f"<header><b>🌱 {T['app']}</b><nav>{enlaces}</nav></header>" if nav else ""
    guion = f"<script>{js}</script>\n" if js else ""
    return (f"<!doctype html>\n<html lang='{T['lang']}'>\n<head>\n<meta charset='utf-8'>\n"
            f"<title>{titulo} · {T['app']}</title>\n"
            f"<style>{css}</style>\n</head>\n<body>\n{cabecera}\n<main>\n<h1>{titulo}</h1>\n{cuerpo}\n</main>\n"
            f"{guion}</body>\n</html>\n")


# ---------------------------------------------------------------- screens

def plantas():
    return [(n, d, T["tipos"][t], s, c) for n, (d, t, s, c) in zip(T["plantas"], PLANTAS)]


def lista() -> str:
    return "<ul class='lista'>" + "\n".join(f"<li>{p[0]}</li>" for p in plantas()) + "</ul>"


def fichas(filtros: bool) -> str:
    cartas = "\n".join(f"<div class='ficha' data-tipo='{t}' data-nombre='{n.lower()}'>{dibujo(d, 110)}<h3>{n}</h3>"
                       f"<small>{t} · {T['siembra_en'].format(m=T['meses'][s - 1].lower())}</small></div>"
                       for n, d, t, s, _ in plantas())
    if not filtros:
        return f"<div class='rejilla'>{cartas}</div>"
    chips = "\n".join(f"<button class='chip{' si' if t == T['todas'] else ''}' data-f='{t}'>{t}</button> "
                      for t in (T["todas"], *T["tipos"]))
    return (f"<p>{chips} &nbsp; <input type='search' placeholder='{T['buscar']}'></p>"
            f"<p id='vacio' hidden>{T['ninguna']}</p><div class='rejilla'>{cartas}</div>")


def js_filtros() -> str:
    return f"""
let tipo='{T["todas"]}', texto='';
const pintar=()=>{{let n=0;document.querySelectorAll('.ficha').forEach(f=>{{const ok=(tipo==='{T["todas"]}'||f.dataset.tipo===tipo)&&f.dataset.nombre.includes(texto);f.hidden=!ok;n+=ok}});document.getElementById('vacio').hidden=n>0}};
document.querySelectorAll('.chip').forEach(b=>b.onclick=()=>{{tipo=b.dataset.f;document.querySelectorAll('.chip').forEach(c=>c.classList.toggle('si',c===b));pintar()}});
document.querySelector('input[type=search]').oninput=e=>{{texto=e.target.value.toLowerCase();pintar()}};
"""


def calendario() -> str:
    cab = f"<tr><th>{T['planta']}</th>" + "\n".join(f"<th>{m}</th>" for m in T["meses"]) + "</tr>"
    filas = ""
    for n, d, _, s, c in plantas():
        celdas = "\n".join(f"<td class='{'s' if s <= m < s + 2 else 'c' if c <= m < c + 2 else ''}'></td>"
                           for m in range(1, 13))
        filas += f"<tr><td>{dibujo(d, 30)} {n}</td>{celdas}</tr>"
    return (f"<p><span class='s'>&nbsp;&nbsp;&nbsp;&nbsp;</span> {T['siembra']} &nbsp; "
            f"<span class='c'>&nbsp;&nbsp;&nbsp;&nbsp;</span> {T['cosecha']}</p>"
            f"<table class='cal'>{cab}{filas}</table>")


RIEGO = [[12, 18, 9, 22, 15, 6, 20], [8, 10, 14, 11, 19, 21, 7], [16, 6, 12, 20, 9, 14, 18]]


def riego() -> str:
    barras = "\n".join(f"<div style='height:{v * 4}%'><span>{d}</span></div>" for v, d in zip(RIEGO[0], T["dias"]))
    return (f"<p><button id='antes'>{T['antes']}</button> <button id='luego'>{T['luego']}</button> "
            "&nbsp; <b id='total'></b></p>"
            f"<div class='barras'>{barras}</div><p style='margin-top:40px'>{T['litros_dia']}</p>")


def js_riego() -> str:
    return f"""
const S={RIEGO};let i=0;
const pintar=()=>{{document.querySelectorAll('.barras div').forEach((b,k)=>b.style.height=S[i][k]*4+'%');
document.getElementById('total').textContent='{T["semana"]} '+(i+1)+': '+S[i].reduce((a,b)=>a+b)+' {T["litros"]}'}};
document.getElementById('antes').onclick=()=>{{i=(i+2)%3;pintar()}};document.getElementById('luego').onclick=()=>{{i=(i+1)%3;pintar()}};pintar();
"""


def portada() -> str:
    filas = "\n".join(f"<div class='tarea'><span>{dibujo(d, 40)} {t}</span><button>{T['hecho']}</button></div>"
                      for t, d in zip(T["tareas"], ("tomate", "pimiento", "albahaca", "lechuga")))
    return (f"<div class='panel'><div class='caja'><h2>{T['hoy']}</h2>" + filas + "</div>"
            f"<div class='caja'><h2>{T['tiempo']}</h2><div class='tiempo'>☀️ 24°</div>"
            f"<p>{T['prevision']}</p><p>{T['humedad']}</p></div></div>")


def js_tareas() -> str:
    return ("document.querySelectorAll('.tarea button').forEach(b=>b.onclick=()=>{b.parentElement.classList.toggle('hecha');"
            f"b.textContent=b.parentElement.classList.contains('hecha')?'{T['deshacer']}':'{T['hecho']}'}});")


def ajustes() -> str:
    u = "".join(f"<option>{x}</option>" for x in T["unidades"])
    controles = [f"<select>{u}</select>", "<input type='checkbox' checked>", "<input type='checkbox'>",
                 "<select><option>08:00</option><option>20:00</option></select>"]
    return "<div class='caja'>" + "\n".join(f"<div class='ajuste'><span>{t}</span>{c}</div>"
                                            for t, c in zip(T["ajustes"], controles)) + "</div>"


# ---------------------------------------------------------------- the history

def construir(raiz: Path, lang: str = "en") -> None:
    global T
    T = TEXTOS[lang]
    if raiz.exists():
        # On Windows git leaves its objects read-only.
        shutil.rmtree(raiz, onerror=lambda f, ruta, _: (os.chmod(ruta, stat.S_IWRITE), f(ruta)))
    raiz.mkdir(parents=True)

    def git(*args: str, fecha: str = "2026-03-01", autor: str = "Ana") -> None:
        env = {**os.environ, "GIT_AUTHOR_DATE": f"{fecha}T10:00:00", "GIT_COMMITTER_DATE": f"{fecha}T10:00:00",
               "GIT_AUTHOR_NAME": autor, "GIT_AUTHOR_EMAIL": f"{autor.lower()}@example.com",
               "GIT_COMMITTER_NAME": autor, "GIT_COMMITTER_EMAIL": f"{autor.lower()}@example.com"}
        subprocess.run(["git", "-C", str(raiz), *args], check=True, capture_output=True, env=env)

    def escribir(ficheros: dict[str, str]) -> None:
        for ruta, texto in ficheros.items():
            (raiz / ruta).write_text(texto, encoding="utf-8")

    git("init", "-q", "-b", "main")
    git("config", "commit.gpgsign", "false")

    css, nav, estado = CSS_0, [], {"filtros": False}
    F = T["ficheros"]

    def todo() -> dict[str, str]:
        f = {"index.html": pagina(T["mi"], portada() if "portada" in estado else lista(), css, nav,
                                  js_tareas() if "portada" in estado else "")}
        if "plantas" in estado:
            f[F["plantas"]] = pagina(T["titulo_plantas"], fichas(estado["filtros"]), css, nav,
                                     js_filtros() if estado["filtros"] else "")
        if "calendario" in estado:
            f[F["calendario"]] = pagina(T["titulo_calendario"], calendario(), css, nav)
        if "riego" in estado:
            f[F["riego"]] = pagina(T["titulo_riego"], riego(), css, nav, js_riego())
        if "ajustes" in estado:
            f[F["ajustes"]] = pagina(T["titulo_ajustes"], ajustes(), css, nav)
        return f

    def menu() -> list[tuple[str, str]]:
        return [("index.html", T["menu"]["inicio"])] + [(F[k], T["menu"][k]) for k in F if k in estado]

    escribir(todo())
    git("add", "-A", fecha="2026-03-02")
    git("commit", "-q", "-m", T["primero"], fecha="2026-03-02")

    def pr(n: int, rama: str, fecha: str, autor: str, cambio) -> None:
        nonlocal nav
        titulo = T["prs"][n - 1]
        git("switch", "-q", "-c", rama)
        cambio()
        nav = menu()
        escribir(todo())
        git("add", "-A")
        git("commit", "-q", "-m", titulo, fecha=fecha, autor=autor)
        git("switch", "-q", "main")
        git("merge", "-q", "--no-ff", rama, "-m", f"Merge pull request #{n} from garden/{rama}\n\n{titulo}",
            fecha=fecha, autor=autor)

    def poner_css(nuevo: str):
        def cambio():
            nonlocal css
            css = nuevo
        return cambio

    def activar(*claves: str):
        return lambda: estado.update({k: True for k in claves})

    pr(1, "colours", "2026-03-09", "Ana", poner_css(CSS_1))
    pr(2, "cards", "2026-03-20", "Luis", activar("plantas"))
    pr(3, "calendar", "2026-04-03", "Marta", activar("calendario"))
    pr(4, "dark-mode", "2026-04-15", "Luis", poner_css(CSS_1 + CSS_OSCURO))
    pr(5, "filters", "2026-04-28", "Ana", activar("filtros"))
    pr(6, "watering", "2026-05-12", "Marta", activar("riego"))
    pr(7, "home", "2026-05-26", "Ana", activar("portada"))
    pr(8, "redesign", "2026-06-09", "Luis", poner_css(CSS_1 + CSS_2 + CSS_OSCURO))
    pr(9, "settings", "2026-06-23", "Marta", activar("ajustes"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Builds the example repository of the README.")
    ap.add_argument("carpeta", nargs="?", metavar="folder")
    ap.add_argument("--lang", choices=tuple(TEXTOS), default="en")
    args = ap.parse_args()
    destino = Path(args.carpeta or ("garden" if args.lang == "en" else "huerto")).resolve()
    construir(destino, args.lang)
    print(f"{destino}: 10 versions on main, 9 pull requests ({args.lang})")
