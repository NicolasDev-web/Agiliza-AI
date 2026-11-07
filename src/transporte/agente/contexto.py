"""Acesso do agente aos dados: tudo vem da base SQLite (src/transporte/base.py).

Nada é carregado na partida. Cada ferramenta faz uma consulta com índice e devolve só o resumo,
então o servidor sobe na hora e o modelo recebe poucos tokens.
"""
from __future__ import annotations

import functools

import pandas as pd

from .. import base


def sql(consulta: str, parametros: tuple | dict = ()) -> pd.DataFrame:
    return base.sql(consulta, parametros)


def tabela(nome: str) -> pd.DataFrame:
    """Tabelas pequenas (uma linha por prefixo, estado ou transportadora)."""
    return _tabela_cache(nome).copy()


@functools.lru_cache(maxsize=16)
def _tabela_cache(nome: str) -> pd.DataFrame:
    assert nome.replace("_", "").isalnum(), "nome de tabela inválido"
    return base.sql(f"select * from {nome}")


def aquecer() -> None:
    """Abre a base (e a constrói se faltar) para a primeira pergunta não esperar."""
    base.conexao()
