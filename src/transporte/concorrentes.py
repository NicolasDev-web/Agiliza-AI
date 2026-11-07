"""Frente 5: como o nosso prazo se compara ao dos concorrentes no mesmo CEP."""
from __future__ import annotations

import pandas as pd

from .config import RAW


def prazo_concorrentes_por_prefixo() -> pd.DataFrame:
    """Prazo mediano dos concorrentes por prefixo de 3 dígitos.

    Linhas com produto esgotado ficam de fora: o site mostra "1 dia" para o que não tem estoque,
    e isso não é prazo de entrega de verdade.
    """
    c = pd.read_csv(RAW / "concorrentes_prazos.csv", dtype={"cep": str})
    c = c[c["estoque_exibido"] == "disponivel"].copy()
    c["cep3"] = c["cep"].str.replace(r"\D", "", regex=True).str.zfill(8).str[:3]
    por_conc = c.groupby(["cep3", "concorrente"]).agg(
        prazo=("prazo_dias_uteis", "median"), frete=("frete", "median")).reset_index()
    return por_conc.groupby("cep3").agg(
        concorrentes=("concorrente", "nunique"),
        prazo_conc_melhor=("prazo", "min"),
        prazo_conc_mediana=("prazo", "median"),
        prazo_conc_pior=("prazo", "max"),
        frete_conc_mediana=("frete", "median"),
    ).reset_index()


def posicao(nosso: float, melhor: float, mediana: float) -> str:
    """Rótulo simples para o gestor: melhor, igual ou pior que os concorrentes."""
    if pd.isna(mediana):
        return "sem dado"
    if nosso <= melhor:
        return "melhor"
    if nosso <= mediana + 0.5:
        return "igual"
    if nosso <= mediana + 2:
        return "um pouco pior"
    return "muito pior"
