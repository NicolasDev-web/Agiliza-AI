"""Geografia real (municípios do IBGE) sobre os pedidos fictícios do desafio."""
from __future__ import annotations

import functools
import math
import unicodedata

import pandas as pd

from .config import ROOT

REF = ROOT / "data" / "ref"

# código IBGE da UF -> sigla
UF_POR_CODIGO = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE",
    24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP",
    41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
}
# CDs do desafio (cds.csv): Fortaleza/CE e Extrema/MG
CDS = {"CD1": ("Fortaleza", "CE"), "CD2": ("Extrema", "MG")}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("'", " ").replace("-", " ").split())


@functools.lru_cache(maxsize=1)
def municipios() -> pd.DataFrame:
    m = pd.read_csv(REF / "municipios_ibge.csv")
    m["uf"] = m["codigo_uf"].map(UF_POR_CODIGO)
    m["chave"] = m["nome"].map(_norm) + "|" + m["uf"]
    return m.drop_duplicates("chave").set_index("chave")


def coordenada(cidade: str, uf: str) -> tuple[float, float] | None:
    m = municipios()
    chave = f"{_norm(cidade)}|{uf}"
    if chave in m.index:
        r = m.loc[chave]
        return float(r["latitude"]), float(r["longitude"])
    return None


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Distância em linha reta entre dois pontos, em km."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def cd_coordenada(cd: str) -> tuple[float, float]:
    cidade, uf = CDS[cd]
    c = coordenada(cidade, uf)
    assert c, f"sem coordenada para o {cd}"
    return c


def tabela_cidades(pares: pd.DataFrame) -> pd.DataFrame:
    """Para cada (cidade, uf) devolve latitude e longitude, e as distâncias até os dois CDs."""
    linhas = []
    cd = {k: cd_coordenada(k) for k in CDS}
    for cidade, uf in pares[["cidade", "uf"]].drop_duplicates().itertuples(index=False):
        c = coordenada(cidade, uf)
        lat, lon = c if c else (None, None)
        linhas.append({
            "cidade": cidade, "uf": uf, "latitude": lat, "longitude": lon,
            "km_cd1": round(haversine_km(*cd["CD1"], lat, lon)) if c else None,
            "km_cd2": round(haversine_km(*cd["CD2"], lat, lon)) if c else None,
        })
    return pd.DataFrame(linhas)
