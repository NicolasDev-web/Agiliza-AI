"""Base SQLite do projeto: um arquivo só, vem com o Python, sem instalar nada.

Os 40 MB de CSV viram tabelas com índice. O agente consulta com SQL e só o resultado resumido
chega ao modelo, então gasta pouquíssimo token. Reconstruir: python scripts/02_base_de_dados.py
"""
from __future__ import annotations

import sqlite3
import threading

import pandas as pd

from . import desempenho, entregas, geo, propostas
from .concorrentes import prazo_concorrentes_por_prefixo
from .config import PROCESSED, RAW
from .portais import carregar_eventos

CAMINHO = PROCESSED / "transporte.db"
_trava = threading.RLock()

INDICES = [
    "create index if not exists ix_env_id on envios(envio_id)",
    "create index if not exists ix_env_cep3 on envios(cep3, transportadora)",
    "create index if not exists ix_env_uf on envios(uf, data_postagem)",
    "create index if not exists ix_env_rastreio on envios(rastreio)",
    "create index if not exists ix_cot_envio on cotacoes(envio_id)",
    "create index if not exists ix_ev_rastreio on eventos(rastreio)",
    "create index if not exists ix_cham_envio on chamados(envio_id)",
    "create index if not exists ix_oco_envio on ocorrencias(envio_id)",
    "create index if not exists ix_conv_cep on conversao(prefixo_cep3)",
    "create index if not exists ix_cid on cidades(cidade, uf)",
]


def _texto(df: pd.DataFrame) -> pd.DataFrame:
    """SQLite não guarda Timestamp: vira texto ISO."""
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


def construir(verbose: bool = False) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    tmp = CAMINHO.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)

    def gravar(nome: str, df: pd.DataFrame) -> None:
        _texto(df).to_sql(nome, con, index=False, if_exists="replace")
        if verbose:
            print(f"  {nome}: {len(df):,} linhas")

    eventos = carregar_eventos()
    envios = entregas.carregar_envios()
    medidas = entregas.medir_entregas(envios, eventos)
    cidades = geo.tabela_cidades(envios)

    gravar("envios", medidas)
    gravar("eventos", eventos)
    gravar("cidades", cidades)
    gravar("desempenho_transportadora", desempenho.por_transportadora(medidas))
    gravar("desempenho_uf", desempenho.por_uf(medidas))
    gravar("desempenho_prefixo", desempenho.por_prefixo(medidas))
    props = propostas.gerar(medidas)
    ref = cidades.rename(columns={"cidade": "cidade_referencia"})
    props = props.merge(ref[["cidade_referencia", "uf", "latitude", "longitude"]], on=["cidade_referencia", "uf"], how="left")
    gravar("propostas", props)
    gravar("regras", propostas.regras_atuais())
    gravar("concorrentes_prefixo", prazo_concorrentes_por_prefixo())
    gravar("cotacoes", pd.read_csv(RAW / "cotacoes_frete.csv"))
    gravar("chamados", pd.read_csv(RAW / "chamados_transportadoras.csv"))
    gravar("ocorrencias", pd.read_csv(RAW / "ocorrencias_entrega.csv"))
    gravar("indenizacoes", pd.read_csv(RAW / "indenizacoes.csv"))
    gravar("conversao", pd.read_csv(RAW / "checkout_conversao.csv", dtype={"prefixo_cep3": str}))
    gravar("politicas", pd.read_csv(RAW / "politicas.csv"))
    gravar("feriados", pd.read_csv(RAW / "feriados.csv"))
    gravar("cobertura", pd.read_csv(RAW / "transportadoras_cobertura_sla.csv"))
    for ddl in INDICES:
        con.execute(ddl)
    con.commit()
    con.close()
    tmp.replace(CAMINHO)


_con: sqlite3.Connection | None = None


def conexao() -> sqlite3.Connection:
    """Abre a base (e constrói na primeira vez). Uma conexão só, protegida por trava."""
    global _con
    with _trava:
        if _con is None:
            if not CAMINHO.exists():
                construir()
            _con = sqlite3.connect(f"file:{CAMINHO}?mode=ro", uri=True, check_same_thread=False)
    return _con


def sql(consulta: str, parametros: tuple | dict = ()) -> pd.DataFrame:
    """Roda uma consulta só de leitura e devolve um DataFrame."""
    with _trava:
        return pd.read_sql_query(consulta, conexao(), params=parametros)
