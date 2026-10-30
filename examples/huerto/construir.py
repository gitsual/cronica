"""El proyecto de ejemplo del README: «Huerto», una web estática que crece en diez PR.

    python examples/huerto/construir.py [carpeta]      (por defecto, ./huerto)
    cronica huerto

Cada PR cambia algo que se ve: una pantalla nueva, el modo oscuro, un rediseño. Las fechas y los autores son
fijos, así que el vídeo sale igual cada vez.
"""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------- dibujos

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

PLANTAS = [  # nombre, dibujo, tipo, siembra (mes 1-12), cosecha
    ("Tomate", "tomate", "Fruto", 3, 8),
    ("Lechuga", "lechuga", "Hoja", 2, 5),
    ("Zanahoria", "zanahoria", "Raíz", 3, 7),
    ("Pimiento", "pimiento", "Fruto", 3, 9),
    ("Fresa", "fresa", "Fruto", 2, 6),
    ("Cebolla", "cebolla", "Raíz", 1, 6),
    ("Calabacín", "calabacin", "Fruto", 4, 8),
    ("Albahaca", "albahaca", "Hoja", 4, 9),
]
MESES = "Ene Feb Mar Abr May Jun Jul Ago Sep Oct Nov Dic".split()


def dibujo(clave: str, tam: int = 64) -> str:
    return f'<svg viewBox="0 0 64 64" width="{tam}" height="{tam}" aria-hidden="true">{DIBUJOS[clave]}</svg>'


# ---------------------------------------------------------------- estilos, de peor a mejor

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
.cal th:first-child,.cal td:first-child{text-align:left;padding-left:12px;width:190px}
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


def pagina(titulo: str, cuerpo: str, css: str, nav: list[str], js: str = "") -> str:
    enlaces = "\n".join(f'<a href="{h}">{t}</a>' for h, t in nav)
    cabecera = f"<header><b>🌱 Huerto</b><nav>{enlaces}</nav></header>" if nav else ""
    guion = f"<script>{js}</script>\n" if js else ""
    return (f"<!doctype html>\n<html lang='es'>\n<head>\n<meta charset='utf-8'>\n<title>{titulo} · Huerto</title>\n"
            f"<style>{css}</style>\n</head>\n<body>\n{cabecera}\n<main>\n<h1>{titulo}</h1>\n{cuerpo}\n</main>\n"
            f"{guion}</body>\n</html>\n")


# ---------------------------------------------------------------- pantallas

def lista() -> str:
    return "<ul class='lista'>" + "\n".join(f"<li>{p[0]}</li>" for p in PLANTAS) + "</ul>"


def fichas(filtros: bool) -> str:
    cartas = "\n".join(f"<div class='ficha' data-tipo='{t}' data-nombre='{n.lower()}'>{dibujo(d, 110)}<h3>{n}</h3>"
                     f"<small>{t} · siembra en {MESES[s - 1].lower()}</small></div>" for n, d, t, s, _ in PLANTAS)
    if not filtros:
        return f"<div class='rejilla'>{cartas}</div>"
    chips = "\n".join(f"<button class='chip{' si' if t == 'Todas' else ''}' data-f='{t}'>{t}</button> "
                    for t in ("Todas", "Fruto", "Hoja", "Raíz"))
    return (f"<p>{chips} &nbsp; <input type='search' placeholder='Buscar una planta…'></p>"
            f"<p id='vacio' hidden>Ninguna planta se llama así.</p><div class='rejilla'>{cartas}</div>")


JS_FILTROS = """
let tipo='Todas', texto='';
const pintar=()=>{let n=0;document.querySelectorAll('.ficha').forEach(f=>{const ok=(tipo==='Todas'||f.dataset.tipo===tipo)&&f.dataset.nombre.includes(texto);f.hidden=!ok;n+=ok});document.getElementById('vacio').hidden=n>0};
document.querySelectorAll('.chip').forEach(b=>b.onclick=()=>{tipo=b.dataset.f;document.querySelectorAll('.chip').forEach(c=>c.classList.toggle('si',c===b));pintar()});
document.querySelector('input[type=search]').oninput=e=>{texto=e.target.value.toLowerCase();pintar()};
"""


def calendario() -> str:
    cab = "<tr><th>Planta</th>" + "\n".join(f"<th>{m}</th>" for m in MESES) + "</tr>"
    filas = ""
    for n, d, _, s, c in PLANTAS:
        celdas = "\n".join(f"<td class='{'s' if s <= m < s + 2 else 'c' if c <= m < c + 2 else ''}'></td>"
                         for m in range(1, 13))
        filas += f"<tr><td>{dibujo(d, 30)} {n}</td>{celdas}</tr>"
    return ("<p><span class='s'>&nbsp;&nbsp;&nbsp;&nbsp;</span> siembra &nbsp; "
            "<span class='c'>&nbsp;&nbsp;&nbsp;&nbsp;</span> cosecha</p>"
            f"<table class='cal'>{cab}{filas}</table>")


RIEGO = [[12, 18, 9, 22, 15, 6, 20], [8, 10, 14, 11, 19, 21, 7], [16, 6, 12, 20, 9, 14, 18]]


def riego() -> str:
    dias = "Lun Mar Mié Jue Vie Sáb Dom".split()
    barras = "\n".join(f"<div style='height:{v * 4}%'><span>{d}</span></div>" for v, d in zip(RIEGO[0], dias))
    return ("<p><button id='antes'>← Semana anterior</button> <button id='luego'>Semana siguiente →</button> "
            "&nbsp; <b id='total'></b></p>"
            f"<div class='barras'>{barras}</div><p style='margin-top:40px'>Litros por día, de todo el huerto.</p>")


JS_RIEGO = f"""
const S={RIEGO};let i=0;
const pintar=()=>{{document.querySelectorAll('.barras div').forEach((b,k)=>b.style.height=S[i][k]*4+'%');
document.getElementById('total').textContent='Semana '+(i+1)+': '+S[i].reduce((a,b)=>a+b)+' litros'}};
document.getElementById('antes').onclick=()=>{{i=(i+2)%3;pintar()}};document.getElementById('luego').onclick=()=>{{i=(i+1)%3;pintar()}};pintar();
"""


def portada() -> str:
    tareas = [("Regar los tomates", "tomate"), ("Atar el pimiento", "pimiento"),
              ("Sembrar albahaca", "albahaca"), ("Cosechar lechugas", "lechuga")]
    filas = "\n".join(f"<div class='tarea'><span>{dibujo(d, 40)} {t}</span><button>Hecho</button></div>"
                    for t, d in tareas)
    return ("<div class='panel'><div class='caja'><h2>Hoy</h2>" + filas + "</div>"
            "<div class='caja'><h2>El tiempo</h2><div class='tiempo'>☀️ 24°</div>"
            "<p>Sol toda la mañana. Sin lluvia hasta el jueves: toca regar.</p>"
            "<p>Humedad 41 % · Viento 9 km/h</p></div></div>")


JS_TAREAS = "document.querySelectorAll('.tarea button').forEach(b=>b.onclick=()=>{b.parentElement.classList.toggle('hecha');b.textContent=b.parentElement.classList.contains('hecha')?'Deshacer':'Hecho'});"


def ajustes() -> str:
    filas = [("Unidades de riego", "<select><option>Litros</option><option>Galones</option></select>"),
             ("Avisar antes de una helada", "<input type='checkbox' checked>"),
             ("Recordatorio diario de riego", "<input type='checkbox'>"),
             ("Hora del recordatorio", "<select><option>08:00</option><option>20:00</option></select>")]
    return "<div class='caja'>" + "\n".join(f"<div class='ajuste'><span>{t}</span>{c}</div>" for t, c in filas) + "</div>"


# ---------------------------------------------------------------- la historia

def construir(raiz: Path) -> None:
    if raiz.exists():
        # En Windows git deja sus objetos de solo lectura.
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

    # el estado que se va construyendo
    css, nav, js_plantas = CSS_0, [], ""
    estado = {"filtros": False}

    def todo() -> dict[str, str]:
        f = {"index.html": pagina("Mi huerto", lista() if "portada" not in estado else portada(), css, nav,
                                  JS_TAREAS if "portada" in estado else "")}
        if "plantas" in estado:
            f["plantas.html"] = pagina("Plantas", fichas(estado["filtros"]), css, nav, js_plantas)
        if "calendario" in estado:
            f["calendario.html"] = pagina("Calendario de siembra", calendario(), css, nav)
        if "riego" in estado:
            f["riego.html"] = pagina("Riego", riego(), css, nav, JS_RIEGO)
        if "ajustes" in estado:
            f["ajustes.html"] = pagina("Ajustes", ajustes(), css, nav)
        return f

    def menu() -> list[tuple[str, str]]:
        orden = [("index.html", "Inicio", True), ("plantas.html", "Plantas", "plantas" in estado),
                 ("calendario.html", "Calendario", "calendario" in estado), ("riego.html", "Riego", "riego" in estado),
                 ("ajustes.html", "Ajustes", "ajustes" in estado)]
        return [(h, t) for h, t, si in orden if si]

    escribir(todo())
    git("add", "-A", fecha="2026-03-02")
    git("commit", "-q", "-m", "Primera página: la lista de plantas", fecha="2026-03-02")

    def pr(n: int, rama: str, titulo: str, fecha: str, autor: str, cambio) -> None:
        nonlocal css, nav, js_plantas
        git("switch", "-q", "-c", rama)
        cambio()
        nav = menu()
        escribir(todo())
        git("add", "-A")
        git("commit", "-q", "-m", titulo, fecha=fecha, autor=autor)
        git("switch", "-q", "main")
        git("merge", "-q", "--no-ff", rama, "-m", f"Merge pull request #{n} from huerto/{rama}\n\n{titulo}",
            fecha=fecha, autor=autor)

    def colores():
        nonlocal css
        css = CSS_1

    def con_plantas():
        estado["plantas"] = True

    def con_calendario():
        estado["calendario"] = True

    def oscuro():
        nonlocal css
        css = CSS_1 + CSS_OSCURO

    def filtros():
        nonlocal js_plantas
        estado["filtros"] = True
        js_plantas = JS_FILTROS

    def con_riego():
        estado["riego"] = True

    def con_portada():
        estado["portada"] = True

    def rediseno():
        nonlocal css
        css = CSS_1 + CSS_2 + CSS_OSCURO

    def con_ajustes():
        estado["ajustes"] = True

    pr(1, "colores", "Una cabecera y los colores del huerto", "2026-03-09", "Ana", colores)
    pr(2, "fichas", "Fichas de plantas con su dibujo", "2026-03-20", "Luis", con_plantas)
    pr(3, "calendario", "Calendario de siembra y cosecha", "2026-04-03", "Marta", con_calendario)
    pr(4, "oscuro", "Modo oscuro", "2026-04-15", "Luis", oscuro)
    pr(5, "filtros", "Filtros por tipo y buscador de plantas", "2026-04-28", "Ana", filtros)
    pr(6, "riego", "La gráfica del riego, semana a semana", "2026-05-12", "Marta", con_riego)
    pr(7, "portada", "Portada con el tiempo y las tareas de hoy", "2026-05-26", "Ana", con_portada)
    pr(8, "rediseno", "Rediseño: letra nueva y tarjetas redondeadas", "2026-06-09", "Luis", rediseno)
    pr(9, "ajustes", "Ajustes: unidades y avisos de helada", "2026-06-23", "Marta", con_ajustes)


if __name__ == "__main__":
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else "huerto").resolve()
    construir(destino)
    print(f"{destino}: 10 versiones en main, 9 PR")
