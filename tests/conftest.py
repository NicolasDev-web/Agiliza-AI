"""Cada teste usa o seu próprio estado.db, para nunca sujar o da demonstração.

Os testes também não leem o .env real: com token e número de WhatsApp lá, eles chamariam a IA e
o WhatsApp de verdade. Quem precisa de uma variável a define no próprio teste (monkeypatch.setenv)."""
import os

import pytest

os.environ["TRANSPORTE_SEM_ENV"] = "1"
os.environ["AUTONOMO_PAUSA_S"] = "0"   # o piloto pausa entre passos só para a tela acompanhar
for _chave in ("AI_PROXY_TOKEN", "WHATSAPP_DESTINO", "WHATSAPP_SIMULAR", "WHATSAPP_PONTE"):
    os.environ.pop(_chave, None)

from transporte import estado  # noqa: E402


@pytest.fixture(autouse=True)
def estado_isolado(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSPORTE_ESTADO", str(tmp_path / "estado.db"))
    estado.con()
    yield
