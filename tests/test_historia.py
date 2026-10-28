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
    assert (r.tipo, r.dir, r.gestor, r.lock) == ("storybook", "apps/sb", "npm", "package-lock.json")
    assert r.salidas == ["out/sb"]
    assert detectar.detectar(repo.raiz, s2, "storybook") is None
    assert detectar.detectar(repo.raiz, s1, "storybook") is None


def test_nada_que_fotografiar(repo):
    sha = repo.commit("una librería", {"src/lib.py": "x = 1\n", "README.md": "hola"})
    assert detectar.detectar(repo.raiz, sha) is None
