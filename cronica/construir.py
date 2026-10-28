"""Construye y fotografía cada hito sobre un clon propio, sin tocar la carpeta del usuario.

trabajo/
  clon/                 git clone --shared del proyecto (aquí se hace checkout, install y build)
  hitos/<sha12>/        estado.json + las fotos de ese hito
  logs/<sha12>-*.log    salida de install / build / dev
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from . import detectar, fotos, historia
from .servidor import Servidor

T_INSTALAR = 20 * 60
T_CONSTRUIR = 15 * 60
T_DEV = 120
ENTORNO = {
    "BROWSER": "none", "STORYBOOK_DISABLE_TELEMETRY": "1", "NG_CLI_ANALYTICS": "false", "NEXT_TELEMETRY_DISABLED": "1",
    "ASTRO_TELEMETRY_DISABLED": "1", "GATSBY_TELEMETRY_DISABLED": "1", "npm_config_fund": "false",
    "npm_config_audit": "false", "npm_config_update_notifier": "false", "FORCE_COLOR": "0", "NO_COLOR": "1",
    "BROWSERSLIST_IGNORE_OLD_DATA": "1", "DISABLE_OPENCOLLECTIVE": "1", "ADBLOCK": "1", "HUSKY": "0",
}


def preparar_clon(origen: Path, trabajo: Path) -> Path:
    clon = trabajo / "clon"
    if not (clon / ".git").exists():
        trabajo.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout", str(origen), str(clon)],
                           capture_output=True, text=True)
        if r.returncode:
            raise historia.ErrorGit(r.stderr.strip())
        historia.git(clon, "config", "core.autocrlf", "false")
        historia.git(clon, "config", "core.longpaths", "true")
    else:
        historia.git(clon, "fetch", "--quiet", "--force", "origin", "+refs/heads/*:refs/remotes/origin/*")
    return clon


def _comando(cmd: list[str]) -> list[str]:
    """npm/pnpm/yarn/npx por su ruta real (en Windows son .cmd); pnpm y yarn por corepack si no están."""
    exe = shutil.which(cmd[0])
    if exe:
        return [exe, *cmd[1:]]
    if cmd[0] in ("pnpm", "yarn") and shutil.which("corepack"):
        return [shutil.which("corepack"), *cmd]
    return cmd


def _entorno(extra: dict | None = None) -> dict:
    env = {**os.environ, **ENTORNO, **(extra or {})}
    env.pop("CI", None)  # con CI=1, create-react-app convierte los avisos en errores
    return env


def _correr(cmd: list[str], cwd: Path, log: Path, limite: int, extra_env: dict | None = None) -> bool:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8", errors="replace") as f:
        f.write(f"\n$ {' '.join(cmd)}   (en {cwd})\n")
        f.flush()
        try:
            p = subprocess.Popen(_comando(cmd), cwd=cwd, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 env=_entorno(extra_env), **_grupo())
        except OSError as error:
            f.write(f"no se pudo lanzar: {error}\n")
            return False
        try:
            return p.wait(timeout=limite) == 0
        except subprocess.TimeoutExpired:
            _matar(p)
            f.write(f"\n[cronica] tiempo agotado ({limite} s)\n")
            return False


def _grupo() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _matar(p: subprocess.Popen) -> None:
    if p.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _borrar_node_modules(clon: Path) -> None:
    for nm in list(clon.glob("node_modules")) + list(clon.glob("*/node_modules")) + list(clon.glob("*/*/node_modules")):
        shutil.rmtree(nm, ignore_errors=True)


def _huella_dependencias(clon: Path, receta: detectar.Receta) -> str:
    h = hashlib.sha1(receta.gestor.encode() if receta.gestor else b"")
    if receta.lock and (clon / receta.lock).exists():
        h.update((clon / receta.lock).read_bytes())
    else:
        for pj in sorted(clon.glob("**/package.json")):
            if "node_modules" not in pj.parts:
                h.update(pj.read_bytes())
    return h.hexdigest()


def _instalar(clon: Path, receta: detectar.Receta, trabajo: Path, log: Path) -> bool:
    huella = _huella_dependencias(clon, receta)
    marca = trabajo / "instalado.txt"
    if marca.exists() and marca.read_text() == huella:
        return True
    _borrar_node_modules(clon)
    marca.unlink(missing_ok=True)
    donde = Path(receta.lock).parent.as_posix() if receta.lock else receta.dir
    cwd = clon / donde if donde not in ("", ".") else clon
    g = receta.gestor or "npm"
    intentos = {
        "npm": [["npm", "ci"], ["npm", "install", "--no-save", "--legacy-peer-deps"]],
        "pnpm": [["pnpm", "install", "--frozen-lockfile"], ["pnpm", "install", "--no-frozen-lockfile"]],
        "yarn": [["yarn", "install", "--frozen-lockfile", "--non-interactive"], ["yarn", "install", "--non-interactive"]],
    }[g]
    if g == "npm" and not receta.lock:
        intentos = intentos[1:]
    for cmd in intentos:
        if _correr(cmd, cwd, log, T_INSTALAR):
            marca.write_text(huella)
            return True
    return False


def _resultado(clon: Path, receta: detectar.Receta, desde: float) -> Path | None:
    """La carpeta construida más reciente que tenga index.html (y, en Storybook, su índice)."""
    candidatas: list[Path] = []
    for rel in receta.salidas:
        base = clon / rel
        if not base.is_dir():
            continue
        candidatas += [p.parent for p in [base / "index.html", *base.glob("*/index.html"), *base.glob("*/*/index.html")]
                       if p.is_file()]
    if receta.tipo == "storybook":
        candidatas += [p.parent for p in clon.glob("**/storybook-static/index.html") if "node_modules" not in p.parts]
        candidatas = [c for c in candidatas if (c / "iframe.html").exists()]
    candidatas = [c for c in candidatas if (c / "index.html").stat().st_mtime >= desde - 2]
    return max(candidatas, key=lambda c: (c / "index.html").stat().st_mtime, default=None)


def _necesita_openssl_legacy(log: Path) -> bool:
    try:
        return "ERR_OSSL_EVP_UNSUPPORTED" in log.read_text(encoding="utf-8", errors="replace")[-20000:]
    except OSError:
        return False


def _construir(clon: Path, receta: detectar.Receta, log: Path) -> Path | None:
    cwd = clon / receta.dir if receta.dir else clon
    for cmd in receta.construir:
        desde = time.time()
        ok = _correr(cmd, cwd, log, T_CONSTRUIR)
        if not ok and _necesita_openssl_legacy(log):
            ok = _correr(cmd, cwd, log, T_CONSTRUIR, {"NODE_OPTIONS": "--openssl-legacy-provider"})
        salida = _resultado(clon, receta, desde)
        if salida:  # algunos builds terminan con error pero dejan el resultado (una story rota, un aviso)
            return salida
    return None


def _dev(clon: Path, receta: detectar.Receta, log: Path, fotografiar) -> dict | None:
    """Arranca el servidor de desarrollo, espera a su URL y fotografía en vivo."""
    cwd = clon / receta.dir if receta.dir else clon
    log.parent.mkdir(parents=True, exist_ok=True)
    f = log.open("a", encoding="utf-8", errors="replace")
    f.write(f"\n$ {' '.join(receta.dev)}   (en {cwd})\n")
    try:
        p = subprocess.Popen(_comando(receta.dev), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, env=_entorno(), text=True, encoding="utf-8",
                             errors="replace", **_grupo())
    except OSError as error:
        f.write(f"no se pudo lanzar: {error}\n")
        f.close()
        return None
    urls: list[str] = []

    def leer():
        for linea in p.stdout:
            f.write(linea)
            limpia = re.sub(r"\x1b\[[0-9;]*m", "", linea)
            m = re.search(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]):\d+[^\s]*", limpia)
            if m and not urls:
                urls.append(m.group(0).replace("0.0.0.0", "127.0.0.1").rstrip("/"))

    hilo = threading.Thread(target=leer, daemon=True)
    hilo.start()
    try:
        limite = time.time() + T_DEV
        while time.time() < limite and p.poll() is None:
            if urls and _responde(urls[0]):
                return fotografiar(urls[0])
            time.sleep(1)
        return None
    finally:
        _matar(p)
        f.close()


def _responde(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status < 500
    except Exception:
        return False


def procesar(hito: historia.Commit, receta: detectar.Receta, clon: Path, trabajo: Path, navegador,
             previos: set[str]) -> dict:
    """Construye y fotografía un hito. Devuelve el estado (también queda en hitos/<sha12>/estado.json)."""
    corto = hito.sha[:12]
    dir_hito = trabajo / "hitos" / corto
    log = trabajo / "logs" / f"{corto}.log"
    log.unlink(missing_ok=True)
    estado = {"sha": hito.sha, "receta": receta.a_dict(), "ok": False, "motivo": ""}

    historia.git(clon, "checkout", "--quiet", "--detach", "--force", hito.sha)
    historia.git(clon, "clean", "-qffdx", "-e", "node_modules")

    def foto(base: str) -> dict | None:
        if receta.tipo == "storybook":
            return fotos.storybook(navegador, base, dir_hito, previos)
        return fotos.web(navegador, base, dir_hito, previos)

    datos = None
    if receta.tipo == "estatico":
        with Servidor(clon / receta.dir if receta.dir else clon) as s:
            datos = foto(s.url)
        estado["motivo"] = "" if datos else "la página sale vacía"
    elif not _instalar(clon, receta, trabajo, log):
        estado["motivo"] = "falla la instalación de dependencias"
    else:
        salida = _construir(clon, receta, log) if receta.construir else None
        if salida:
            with Servidor(salida) as s:
                datos = foto(s.url)
            estado["motivo"] = "" if datos else "el build se abre vacío"
        if not datos and receta.tipo == "web" and receta.dev:
            datos = _dev(clon, receta, log, foto)
            estado["motivo"] = "" if datos else "ni el build ni el servidor de desarrollo dan una página"
        elif not salida and not estado["motivo"]:
            estado["motivo"] = "el build no deja resultado"

    if datos and datos.get("fichas"):
        estado.update(ok=True, fotos=datos)
    elif datos:
        estado["motivo"] = "sin nada que fotografiar"
    estado["log"] = str(log)
    dir_hito.mkdir(parents=True, exist_ok=True)
    (dir_hito / "estado.json").write_text(json.dumps(estado, indent=1, ensure_ascii=False), encoding="utf-8")
    return estado
