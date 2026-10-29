from cronica.cli import _carpeta_y_rama


def test_rama_con_barras(tmp_path):
    repo = tmp_path / "mi-proyecto"
    repo.mkdir()
    assert _carpeta_y_rama(f"{repo}@feat/x/y") == (repo.resolve(), "feat/x/y")
    assert _carpeta_y_rama(f"{repo}@main") == (repo.resolve(), "main")
    assert _carpeta_y_rama(str(repo)) == (repo.resolve(), None)


def test_arroba_en_la_ruta(tmp_path):
    repo = tmp_path / "a@b"
    repo.mkdir()
    assert _carpeta_y_rama(str(repo)) == (repo.resolve(), None)
    assert _carpeta_y_rama(f"{repo}@dev") == (repo.resolve(), "dev")
