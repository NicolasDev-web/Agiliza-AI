"""Dados carregados uma vez e compartilhados pelas ferramentas do agente."""
from __future__ import annotations

import functools

import pandas as pd

from .. import desempenho, entregas, propostas
from ..concorrentes import prazo_concorrentes_por_prefixo
from ..config import RAW


@functools.lru_cache(maxsize=1)
class Contexto:
    """Carrega tudo na primeira vez que é usado e guarda em memória."""

    def __init__(self) -> None:
        self.envios = entregas.carregar_envios()
        self.medidas = entregas.medir_entregas(self.envios)
        self.por_transportadora = desempenho.por_transportadora(self.medidas)
        self.por_prefixo = desempenho.por_prefixo(self.medidas)
        self.por_uf = desempenho.por_uf(self.medidas)
        self.propostas = propostas.gerar(self.medidas)
        self.concorrentes = prazo_concorrentes_por_prefixo()
        self.regras = propostas.regras_atuais()

    @functools.cached_property
    def cotacoes(self) -> pd.DataFrame:
        return pd.read_csv(RAW / "cotacoes_frete.csv")

    @functools.cached_property
    def chamados(self) -> pd.DataFrame:
        c = pd.read_csv(RAW / "chamados_transportadoras.csv", parse_dates=["aberto_em"])
        return c.merge(self.envios[["envio_id", "uf", "cep3", "cidade"]], on="envio_id", how="left")

    @functools.cached_property
    def ocorrencias(self) -> pd.DataFrame:
        o = pd.read_csv(RAW / "ocorrencias_entrega.csv", parse_dates=["data_hora"])
        return o.merge(self.envios[["envio_id", "uf", "cep3", "cidade", "valor_pedido"]], on="envio_id", how="left")

    @functools.cached_property
    def indenizacoes(self) -> pd.DataFrame:
        return pd.read_csv(RAW / "indenizacoes.csv")

    @functools.cached_property
    def cobertura(self) -> pd.DataFrame:
        return pd.read_csv(RAW / "transportadoras_cobertura_sla.csv")

    @functools.cached_property
    def politicas(self) -> pd.DataFrame:
        return pd.read_csv(RAW / "politicas.csv")

    @functools.cached_property
    def conversao(self) -> pd.DataFrame:
        return pd.read_csv(RAW / "checkout_conversao.csv", dtype={"prefixo_cep3": str}, parse_dates=["data"])

    @functools.cached_property
    def concorrentes_bruto(self) -> pd.DataFrame:
        c = pd.read_csv(RAW / "concorrentes_prazos.csv", dtype={"cep": str}, parse_dates=["data_coleta"])
        c["cep3"] = c["cep"].str.replace(r"\D", "", regex=True).str.zfill(8).str[:3]
        return c


def ctx() -> Contexto:
    return Contexto()
