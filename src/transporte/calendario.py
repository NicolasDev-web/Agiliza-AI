"""Dias úteis da regra do site: segunda a sexta, menos feriados nacionais."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import RAW

# fuso de cada UF (o resto do Brasil usa Brasília, UTC-3)
FUSO_UF = {
    "AC": "America/Rio_Branco",
    "AM": "America/Manaus", "RO": "America/Manaus", "RR": "America/Manaus",
    "MT": "America/Cuiaba", "MS": "America/Campo_Grande",
}


def fuso(uf: str) -> str:
    return FUSO_UF.get(uf, "America/Sao_Paulo")


def feriados() -> pd.DataFrame:
    return pd.read_csv(RAW / "feriados.csv", parse_dates=["data"])


def feriados_nacionais() -> np.ndarray:
    f = feriados()
    return f.loc[f["abrangencia"] == "nacional", "data"].values.astype("datetime64[D]")


def dias_uteis_entre(inicio, fim, hol: np.ndarray | None = None) -> np.ndarray:
    """Dias úteis em (inicio, fim], sem contar o dia de início.

    É a conta do site: o primeiro dia útil depois do pedido é o dia 1.
    Devolve 0 se fim <= inicio.
    """
    hol = feriados_nacionais() if hol is None else hol
    a = np.asarray(inicio, dtype="datetime64[D]")
    b = np.asarray(fim, dtype="datetime64[D]")
    um = np.timedelta64(1, "D")
    n = np.busday_count(a + um, b + um, holidays=hol)
    return np.where(b > a, n, 0)


def somar_dias_uteis(inicio, n, hol: np.ndarray | None = None) -> np.ndarray:
    """Data do dia útil número n depois de `inicio` (dia 1 = primeiro dia útil seguinte)."""
    hol = feriados_nacionais() if hol is None else hol
    a = np.asarray(inicio, dtype="datetime64[D]")
    # 'backward' leva um pedido de sábado para a sexta, e o dia 1 passa a ser a segunda
    return np.busday_offset(a, np.asarray(n), roll="backward", holidays=hol)
