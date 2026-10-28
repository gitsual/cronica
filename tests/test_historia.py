import json

from cronica import detectar, historia
from tests.conftest import pagina


def test_con_merges_los_hitos_son_las_pr(repo):
    primero = repo.commit("inicio", {"index.html": pagina("Inicio")})
    shas = [repo.pr(n, f"rama{n}", f"PR {n}", {f"p{n}.html": pagina(f"P{n}")}) for n in range(1, 5)]
    todos = historia.commits(repo.raiz, "main")
    cands = historia.candidatos(todos)
    assert [x.sha for x in cands] == [primero, *shas]
    assert all(x.merge for x in cands[1:])
    assert cands[1].churn > 0  # el merge cuenta lo que trae la rama


def test_sin_merges_todos_son_candidatos_y_se_muestrea_por_cambio(repo):
    for n in range(10):
        # El commit 5 es enorme: el muestreo debe dejarlo dentro.
        repo.commit(f"c{n}", {"index.html": pagina(f"v{n}", cuerpo="x\n" * (500 if n == 5 else 2))})
    todos = historia.commits(repo.raiz, "main")
    elegidos = historia.muestrear(historia.candidatos(todos), 4, todos)
    assert len(elegidos) == 4
    assert elegidos[0] is todos[0] and elegidos[-1] is todos[-1]
    assert todos[5] in elegidos


def test_cifras_git(repo):
    repo.commit("uno", {"a.txt": "1\n2\n3\n", "package-lock.json": "{}\n" * 50}, autor="Ana")
    sha = repo.commit("dos", {"b.txt": "4\n"}, autor="Bea")
    assert historia.cifras_git(repo.raiz, sha) == {"ficheros": 3, "lineas": 4, "commits": 2, "autores": 2}


def test_detectar_tipos(repo):
    s1 = repo.commit("estático", {"docs/index.html": pagina("Docs")})
    r = detectar.detectar(repo.raiz, s1)
    assert (r.tipo, r.dir) == ("estatico", "docs")

    s2 = repo.commit("vite", {"package.json": json.dumps({"scripts": {"dev": "vite", "build": "vite build"},
                                                          "devDependencies": {"vite": "5"}}),
                              "pnpm-lock.yaml": "lockfileVersion: 9"})
    r = detectar.detectar(repo.raiz, s2)
    assert (r.tipo, r.gestor, r.construir, r.dev) == ("web", "pnpm", [["pnpm", "run", "build"]], ["pnpm", "run", "dev"])

    (repo.raiz / "pnpm-lock.yaml").unlink()
    s3 = repo.commit("storybook en un workspace", {
        "package.json": json.dumps({"workspaces": ["apps/*"], "scripts": {"storybook:build": "npm -w sb run build"}}),
        "package-lock.json": "{}",
        "apps/sb/package.json": json.dumps({"scripts": {"build": "storybook build -o ../../out/sb"}}),
    })
    r = detectar.detectar(repo.raiz, s3)
    # Manda el script de la raíz, que orquesta el workspace.
    assert (r.tipo, r.dir, r.gestor, r.lock) == ("storybook", "", "npm", "package-lock.json")
    assert r.construir == [["npm", "run", "storybook:build"]]
    assert "apps/sb/storybook-static" in r.salidas
    assert detectar.detectar(repo.raiz, s2, "storybook") is None
    assert detectar.detectar(repo.raiz, s1, "storybook") is None


def test_nada_que_fotografiar(repo):
    sha = repo.commit("una librería", {"src/lib.py": "x = 1\n", "README.md": "hola"})
    assert detectar.detectar(repo.raiz, sha) is None


def test_cifras_del_ecosistema_por_fecha(tmp_path):
    """Varios repositorios juntos, tal como estaban cada día: lo que se extrae de uno sigue contando en otro."""
    from tests.conftest import Repo
    a, b = Repo(tmp_path / "a"), Repo(tmp_path / "b")
    a.commit("uno", {"x.txt": "1\n2\n"}, autor="Ana")            # día 2
    b.dia = 3
    b.commit("dos", {"y.txt": "3\n"}, autor="Bea")               # día 4
    eco = [(a.raiz, "main"), (b.raiz, "main")]
    assert historia.cifras_ecosistema(eco, "2026-01-04") == {"ficheros": 1, "lineas": 2, "commits": 1, "autores": 1}
    assert historia.cifras_ecosistema(eco, "2026-01-05") == {"ficheros": 2, "lineas": 3, "commits": 2, "autores": 2}
