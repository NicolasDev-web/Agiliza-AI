"""Roda a primeira parte do projeto de ponta a ponta.

    python scripts/01_processar.py

Lê data/raw, mede as entregas pelos portais, calcula o desempenho por transportadora e prefixo de CEP,
gera as propostas de prazo e escreve:
  data/processed/*.csv      tabelas para análise
  dashboard/data.js         dados da interface (window.DADOS)
"""
from __future__ import annotations

import json
import sys

for _f in (sys.stdout, sys.stderr):   # Windows: o console padrão não é UTF-8 e acento vira "?"
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from transporte import desempenho, entregas, geo, portais, propostas  # noqa: E402
from transporte.config import DASHBOARD, DATA_REFERENCIA, PROCESSED  # noqa: E402


def _limpa(obj):
    """NaN e tipos do numpy viram JSON válido."""
    if isinstance(obj, dict):
        return {k: _limpa(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_limpa(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return None if np.isnan(obj) else round(float(obj), 4)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    eventos = portais.carregar_eventos()
    qualidade = portais.relatorio_qualidade(eventos)
    envios = entregas.carregar_envios()
    qualidade["data_prometida_confere_com_regra"] = entregas.conferir_data_prometida(envios)
    d = entregas.medir_entregas(envios, eventos)
    qualidade["status_dos_envios"] = d["status"].value_counts().to_dict()

    transp = desempenho.por_transportadora(d)
    prefixos = desempenho.por_prefixo(d)
    ufs = desempenho.por_uf(d)
    props = propostas.gerar(d)
    cid = geo.tabela_cidades(props.rename(columns={"cidade_referencia": "cidade"}))
    props = props.merge(cid[["cidade", "uf", "latitude", "longitude"]].rename(columns={"cidade": "cidade_referencia"}),
                        on=["cidade_referencia", "uf"], how="left")

    d.drop(columns=["rastreio"]).to_csv(PROCESSED / "envios_medidos.csv", index=False, encoding="utf-8")
    transp.to_csv(PROCESSED / "desempenho_transportadora.csv", index=False, encoding="utf-8")
    prefixos.to_csv(PROCESSED / "desempenho_prefixo.csv", index=False, encoding="utf-8")
    ufs.to_csv(PROCESSED / "desempenho_uf.csv", index=False, encoding="utf-8")
    props.to_csv(PROCESSED / "propostas_prazo.csv", index=False, encoding="utf-8")
    (PROCESSED / "qualidade_dados.json").write_text(json.dumps(_limpa(qualidade), ensure_ascii=False, indent=2), encoding="utf-8")

    # resumo por UF para o mapa
    pu = props.copy()
    pu["peso"] = pu["envios_medidos"]
    por_uf = {}
    for uf, g in pu.groupby("uf"):
        w = g["peso"].sum()
        por_uf[uf] = {
            "envios": int(w),
            "cumprimento": float(np.average(g["cumprimento_hoje"].fillna(0), weights=g["peso"])) if w else None,
            "prefixos": int(len(g)),
            "aumentar": int((g["acao"] == "aumentar").sum()),
            "reduzir": int((g["acao"] == "reduzir").sum()),
            "impacto": float(g["impacto_custo_atraso_rs"].sum()),
        }
    m = d[d["medido"]]
    cump_uf_transp = {
        f"{r.uf}|{r.transportadora}": {"envios": int(r.envios), "cumprimento": float(r.cumprimento)}
        for r in ufs.itertuples() if r.envios >= 1
    }
    dados = {
        "meta": {
            "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "fonte_geografia": "municípios do IBGE (reais); pedidos, prazos e transportadoras são fictícios do desafio",
            "data_referencia": DATA_REFERENCIA,
            "envios_medidos": int(len(m)),
            "periodo": [str(d.loc[d["medido"], "dia_pedido"].min().date()), str(d.loc[d["medido"], "dia_pedido"].max().date())],
            "meta_cumprimento": 0.92,
            "cumprimento_geral": float(m["no_prazo"].mean()),
            "prefixos_abaixo_da_meta": int((props["cumprimento_hoje"] < 0.92).sum()),
            "propostas_aumentar": int((props["acao"] == "aumentar").sum()),
            "propostas_reduzir": int((props["acao"] == "reduzir").sum()),
            "impacto_total": float(props["impacto_custo_atraso_rs"].sum()),
        },
        "qualidade": qualidade,
        "transportadoras": transp.to_dict("records"),
        "ufs": por_uf,
        "uf_transportadora": cump_uf_transp,
        "prefixos": props.to_dict("records"),
    }
    DASHBOARD.mkdir(exist_ok=True)
    (DASHBOARD / "data.js").write_text(
        "window.DADOS = " + json.dumps(_limpa(dados), ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"ok: {len(m):,} envios medidos, {len(props)} prefixos, "
          f"{dados['meta']['propostas_aumentar']} para aumentar e {dados['meta']['propostas_reduzir']} para reduzir")


if __name__ == "__main__":
    main()
