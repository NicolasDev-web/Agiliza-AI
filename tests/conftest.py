"""Cada teste usa o seu próprio estado.db, para nunca sujar o da demonstração."""
import pytest

from transporte import estado


@pytest.fixture(autouse=True)
def estado_isolado(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSPORTE_ESTADO", str(tmp_path / "estado.db"))
    estado.con()
    yield
