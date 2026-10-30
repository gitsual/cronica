"""Rótulos de cada hito: del mensaje del commit o de la PR, y opcionalmente reescritos por un modelo local.

La IA solo habla con un servidor en esta máquina (Ollama o uno compatible con OpenAI, como LM Studio):
nada del proyecto sale fuera.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

from .historia import Commit
from .i18n import _

LARGO = 64
CLAVE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")


def pr_y_titulo(c: Commit) -> tuple[int | None, str]:
    """El número de PR (si lo hay) y el título legible de un commit o merge."""
    asunto, cuerpo = c.asunto, c.cuerpo
    primera = next((l.strip() for l in cuerpo.splitlines() if l.strip()), "")
    m = re.match(r"Merge pull request #(\d+) from \S+", asunto)            # GitHub
    if m:
        return int(m.group(1)), primera or asunto
    m = re.match(r"(?:Merged )?PR (\d+): (.*)", asunto)                     # Azure DevOps
    if m:
        return int(m.group(1)), m.group(2)
    m = re.match(r"Pull request #(\d+): (.*)", asunto)                      # Bitbucket
    if m:
        return int(m.group(1)), m.group(2)
    m = re.match(r"Merge branch '([^']+)' into '[^']+'", asunto)            # GitLab
    if m:
        mr = re.search(r"See merge request \S*!(\d+)", cuerpo)
        return (int(mr.group(1)) if mr else None), (primera if primera and not primera.startswith("See merge") else m.group(1))
    m = re.match(r"(.*) \(#(\d+)\)$", asunto)                               # squash de GitHub
    if m:
        return int(m.group(2)), m.group(1)
    m = re.match(r"Merge branch '([^']+)'", asunto)
    if m:
        return None, m.group(1)
    return None, asunto


def clave(c: Commit) -> str | None:
    m = CLAVE.search(c.asunto) or CLAVE.search(c.cuerpo[:300])
    return m.group(0) if m else None


def limpiar(titulo: str) -> str:
    partes = [p.strip() for p in titulo.split("|") if p.strip()]
    t = partes[-1] if partes else titulo
    t = re.sub(r"^(?:feature|feat|fix|bugfix|hotfix|chore|release)/", "", t, flags=re.I)
    t = CLAVE.sub("", t)
    t = re.sub(r"\s*[(\[]\s*[)\]]", "", t)                        # «(TIENDA-482)» deja «()»
    t = re.sub(r"^\s*\w+(?:\([^)]*\))?!?:\s*", "", t)          # feat(x): …
    if " " not in t.strip():                                    # un nombre de rama: add-login-page
        t = re.sub(r"[-_]+", " ", t.split("/")[-1])
    t = re.sub(r"\s{2,}", " ", t).strip(" -:·")
    t = t[:1].upper() + t[1:]
    if len(t) > LARGO:
        t = t[:LARGO].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return t or "Sin título"


def chip(c: Commit) -> str:
    pr, _titulo = pr_y_titulo(c)
    partes = [f"#{pr}"] if pr else []
    k = clave(c)
    if k:
        partes.append(k)
    partes += c.tags[:1]
    partes.append(c.sha[:7])
    return " · ".join(partes)


# ---------------------------------------------------------------- IA local

def llm(prompt: str, modelo: str | None, ai: dict | None = None, json_mode: bool = True, timeout: float = 600) -> str:
    """Una pregunta al modelo. `ai` es la sección de los ajustes ({backend, url, model, key}); sin ella, Ollama
    en :11434 o lo que diga CRONICA_LLM."""
    if ai is None:
        url_env = os.environ.get("CRONICA_LLM", "http://127.0.0.1:11434")
        compatible = "/v1" in url_env or url_env.rstrip("/").endswith(":1234")
        ai = {"backend": "openai" if compatible else "ollama", "url": url_env, "model": "", "key": ""}
    from .ajustes import base as base_de
    base = base_de(ai)
    cab = {"Content-Type": "application/json"}
    if ai.get("backend") == "openai":                                 # compatible con OpenAI (LM Studio, llama-server, LiteLLM…)
        url = base if base.endswith("/chat/completions") else base + ("" if base.endswith("/v1") else "/v1") + "/chat/completions"
        cuerpo = {"model": modelo or ai.get("model") or "local", "temperature": 0.3,
                  "messages": [{"role": "user", "content": prompt}]}
        if ai.get("key"):
            cab["Authorization"] = f"Bearer {ai['key']}"
        leer = lambda d: d["choices"][0]["message"]["content"]
    else:                                                             # Ollama
        url = base + "/api/chat"
        cuerpo = {"model": modelo or ai.get("model") or _modelo_ollama(base), "stream": False,
                  "options": {"temperature": 0.3, "num_ctx": 16384}, "messages": [{"role": "user", "content": prompt}]}
        if json_mode:
            cuerpo["format"] = "json"
        leer = lambda d: d["message"]["content"]
    req = urllib.request.Request(url, json.dumps(cuerpo).encode(), cab)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return leer(json.loads(r.read()))


def _modelo_ollama(base: str) -> str:
    with urllib.request.urlopen(base + "/api/tags", timeout=5) as r:
        modelos = [m["name"] for m in json.loads(r.read()).get("models", [])]
    if not modelos:
        raise RuntimeError(_("Ollama no tiene modelos"))
    preferidos = ("qwen3", "qwen2.5", "llama3", "gemma", "mistral")
    return next((m for p in preferidos for m in modelos if m.startswith(p) and "embed" not in m), modelos[0])


def con_ia(nombre: str, hitos: list[dict], modelo: str | None, idioma: str = "en", ai: dict | None = None) -> dict:
    """{'titulo', 'cierre', 'rotulos': {nn: texto}} escrito por el modelo; lanza si no responde bien."""
    bloques = []
    for h in hitos:
        nuevos = ", ".join(h["nuevas"][:12]) or "—"
        commits = "\n".join(f"    - {s}" for s in h["commits"][:25])
        bloques.append(f"[{h['nn']}] {h['fecha']} · original title: {h['titulo']}\n  appears: {nuevos}\n  commits:\n{commits}")
    lengua, ejemplos = {
        "es": ("Spanish from Spain", "«Llega la tabla de tracks», «Modo oscuro en todas las pantallas»"),
        "en": ("English", "«The tracks table arrives», «Dark mode on every screen»"),
    }.get(idioma, (idioma, ""))
    prompt = f"""Write the headlines of a film that shows how the interface of the project «{nombre}» evolved.
Each scene is a milestone of its git history. For each milestone you have its original title, the components or
screens that appear for the first time and the commits since the previous milestone.

Rules for each headline:
- in {lengua}, 3 to 9 words and at most 55 characters;
- say what changes in what you see or in what the project can now do; concrete, no marketing adjectives;
- no ticket keys, PR numbers, hashes or prefixes like «feat:»;
- as a noun phrase or in the present tense ({ejemplos}).

Also write "titulo" (the project's name or a phrase of 2 to 5 words) and "cierre" (a short sentence that sums up
the journey, without figures), both in {lengua}.

Answer ONLY with JSON: {{"titulo": "...", "cierre": "...", "rotulos": {{"<nn>": "..."}}}}

MILESTONES
{chr(10).join(bloques)}"""
    texto = llm(prompt, modelo, ai)
    m = re.search(r"\{.*\}", texto, re.S)
    datos = json.loads(m.group(0) if m else texto)
    rot = {str(k): str(v).strip() for k, v in (datos.get("rotulos") or {}).items() if str(v).strip()}
    if len(rot) < len(hitos) // 2:
        raise RuntimeError(_("el modelo devolvió pocos rótulos"))
    return {"titulo": str(datos.get("titulo") or nombre)[:60], "cierre": str(datos.get("cierre") or "")[:90],
            "rotulos": {k: (v if len(v) <= LARGO + 6 else limpiar(v)) for k, v in rot.items()}}
