"""Frente 2: quanto cada transportadora cumpre o prazo, por cabeça de CEP (3 primeiros dígitos)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import MIN_ENVIOS_PREFIXO


def _p(q: float):
    return lambda s: float(np.nanpercentile(s, q)) if s.notna().any() else np.nan


def medir_por(df: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    """Cumprimento de prazo e prazo realmente levado, agrupados pelas `chaves`.

    - cumprimento: dos envios com desfecho conhecido, quantos chegaram até a data prometida
      (extravio, devolução e pedido ainda aberto e já vencido contam como não cumprido)
    - prazo_real_pXX: dias úteis que o pedido levou da compra à entrega (mesma contagem do site)
    """
    m = df[df["medido"]]
    g = m.groupby(chaves)
    ent = m[m["status"] == "entregue"].groupby(chaves)
    out = pd.DataFrame({
        "envios": g.size(),
        "no_prazo": g["no_prazo"].sum(),
        "cumprimento": g["no_prazo"].mean(),
        "atraso_medio_du": ent["atraso_du"].apply(lambda s: s[s > 0].mean() if (s > 0).any() else 0.0),
        "extravios": g["status"].apply(lambda s: (s == "extraviado").sum()),
        "devolucoes": g["status"].apply(lambda s: (s == "devolvido").sum()),
        "prazo_real_p50": ent["prazo_real_du"].apply(_p(50)),
        "prazo_real_p80": ent["prazo_real_du"].apply(_p(80)),
        "prazo_real_p92": ent["prazo_real_du"].apply(_p(92)),
        "prazo_exibido_medio": g["prazo_exibido_dias_uteis"].mean(),
        "frete_custo_medio": g["custo_frete_cotado"].mean(),
    }).reset_index()
    out["amostra_suficiente"] = out["envios"] >= MIN_ENVIOS_PREFIXO
    out["abaixo_da_meta"] = out["cumprimento"] < 0.92
    return out


def por_transportadora(df: pd.DataFrame) -> pd.DataFrame:
    return medir_por(df, ["transportadora"])


def por_prefixo(df: pd.DataFrame) -> pd.DataFrame:
    return medir_por(df, ["cep3", "uf", "transportadora"])


def por_uf(df: pd.DataFrame) -> pd.DataFrame:
    return medir_por(df, ["uf", "transportadora"])
