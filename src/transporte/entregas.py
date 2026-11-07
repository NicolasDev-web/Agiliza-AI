"""Cruza os envios do ERP com os eventos dos portais: quando cada pedido foi realmente entregue."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import calendario as cal
from .config import DATA_REFERENCIA, RAW
from .portais import carregar_eventos


def normalizar_cep(serie: pd.Series) -> pd.Series:
    """CEP como digitado (com hífen ou sem o zero à esquerda) -> 8 dígitos."""
    return serie.astype(str).str.replace(r"\D", "", regex=True).str.zfill(8)


def carregar_envios() -> pd.DataFrame:
    e = pd.read_csv(RAW / "envios.csv", dtype={"cep": str, "codigo_rastreio": str, "nota_fiscal": str})
    e["cep8"] = normalizar_cep(e["cep"])
    e["cep3"] = e["cep8"].str[:3]
    e["cep5"] = e["cep8"].str[:5]
    e["data_pedido"] = pd.to_datetime(e["data_pedido"])
    e["dia_pedido"] = e["data_pedido"].dt.normalize()
    e["data_prometida"] = pd.to_datetime(e["data_prometida"])
    e["data_postagem"] = pd.to_datetime(e["data_postagem"])
    e["rastreio"] = e["codigo_rastreio"].str.strip().str.upper()
    return e


def _resumo_eventos(ev: pd.DataFrame, envios: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por rastreio: data/hora da entrega e o pior desfecho."""
    uf = envios.drop_duplicates("rastreio").set_index("rastreio")["uf"]
    ev = ev.merge(uf.rename("uf_destino"), left_on="rastreio", right_index=True, how="inner")
    # Correio Ágil manda em UTC: converte para o horário do destino
    for tz, g in ev[ev["quando_eh_utc"]].groupby(ev["uf_destino"].map(cal.fuso)):
        idx = g.index
        ev.loc[idx, "quando"] = (
            g["quando"].dt.tz_localize("UTC").dt.tz_convert(tz).dt.tz_localize(None)
        )
    g = ev.groupby("rastreio")
    out = pd.DataFrame({
        "primeiro_evento": g["quando"].min(),
        "entregue_em": ev[ev["tipo"] == "entregue"].groupby("rastreio")["quando"].min(),
        "teve_tentativa": ev[ev["tipo"] == "tentativa"].groupby("rastreio").size() > 0,
        "devolvido": ev[ev["tipo"] == "devolvido"].groupby("rastreio").size() > 0,
        "extraviado": ev[ev["tipo"] == "extraviado"].groupby("rastreio").size() > 0,
    })
    for c in ["teve_tentativa", "devolvido", "extraviado"]:
        out[c] = out[c].fillna(False).astype(bool)
    return out


def medir_entregas(envios: pd.DataFrame | None = None, eventos: pd.DataFrame | None = None) -> pd.DataFrame:
    """Devolve os envios com o desfecho de cada um e se cumpriu a data prometida."""
    envios = carregar_envios() if envios is None else envios
    eventos = carregar_eventos() if eventos is None else eventos
    r = _resumo_eventos(eventos, envios)
    d = envios.merge(r, left_on="rastreio", right_index=True, how="left")
    d["data_entrega"] = d["entregue_em"].dt.normalize()
    ref = pd.Timestamp(DATA_REFERENCIA)

    tem_evento = d["primeiro_evento"].notna()
    d["status"] = np.select(
        [
            d["rastreio"].isna(),
            d["entregue_em"].notna(),
            d["extraviado"].fillna(False).astype(bool),
            d["devolvido"].fillna(False).astype(bool),
            ~tem_evento,
            d["data_prometida"] < ref,
        ],
        ["sem_rastreio", "entregue", "extraviado", "devolvido", "sem_dados_portal", "em_aberto_atrasado"],
        default="em_aberto_no_prazo",
    )
    # só entra no cumprimento de prazo quem tem desfecho conhecido
    d["medido"] = d["status"].isin(["entregue", "extraviado", "devolvido", "em_aberto_atrasado"])
    d["no_prazo"] = (d["status"] == "entregue") & (d["data_entrega"] <= d["data_prometida"])
    d["atraso_du"] = 0
    ent = d["status"] == "entregue"
    d.loc[ent, "atraso_du"] = cal.dias_uteis_entre(d.loc[ent, "data_prometida"], d.loc[ent, "data_entrega"])
    # prazo realmente levado, no mesmo jeito de contar do prazo exibido (dia 1 = útil seguinte ao pedido)
    d["prazo_real_du"] = np.nan
    d.loc[ent, "prazo_real_du"] = cal.dias_uteis_entre(d.loc[ent, "dia_pedido"], d.loc[ent, "data_entrega"])
    return d


def conferir_data_prometida(envios: pd.DataFrame) -> float:
    """Refaz a data prometida pela regra oficial e devolve a % que bate com o ERP."""
    ref = cal.somar_dias_uteis(envios["dia_pedido"], envios["prazo_exibido_dias_uteis"].astype(int))
    return float((pd.to_datetime(ref) == envios["data_prometida"]).mean())
