"""Frente 3: a melhor rota de cada envio novo.

A promessa ao cliente já foi feita no checkout. Então a escolha certa é a transportadora que
custa menos somando o frete com o custo esperado de chegar atrasado, usando o histórico real
de entregas daquela transportadora naquela região.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..propostas import custo_esperado_atraso
from .contexto import ctx


def _historico(c, transportadora: str, uf: str, cep3: str) -> tuple[np.ndarray, str]:
    """Dias úteis que a transportadora levou nessa região. Usa o prefixo; se for pouco, a UF."""
    ent = c.medidas[(c.medidas["status"] == "entregue") & (c.medidas["transportadora"] == transportadora)]
    no_prefixo = ent.loc[ent["cep3"] == cep3, "prazo_real_du"].dropna().to_numpy()
    if len(no_prefixo) >= 20:
        return no_prefixo, f"prefixo {cep3}"
    na_uf = ent.loc[ent["uf"] == uf, "prazo_real_du"].dropna().to_numpy()
    if len(na_uf) >= 20:
        return na_uf, f"estado {uf}"
    return ent["prazo_real_du"].dropna().to_numpy(), "todas as regiões"


def avaliar(envio_id: str) -> dict:
    """Compara as transportadoras que atendem o envio e devolve o ranking com o motivo."""
    c = ctx()
    env = c.envios[c.envios["envio_id"] == envio_id]
    if env.empty:
        return {"erro": f"envio {envio_id} não encontrado"}
    e = env.iloc[0]
    cot = c.cotacoes[c.cotacoes["envio_id"] == envio_id]
    if cot.empty:
        return {"erro": f"sem cotação para o envio {envio_id}"}

    padrao = c.regras.loc[c.regras["cep3"] == e["cep3"], "transportadora_padrao"]
    padrao = padrao.iloc[0] if len(padrao) else None
    prazo_prometido = float(e["prazo_exibido_dias_uteis"])
    valor = float(e["valor_pedido"])

    linhas = []
    for _, q in cot.iterrows():
        hist, base = _historico(c, q["transportadora"], e["uf"], e["cep3"])
        if len(hist) == 0:
            continue
        atrasos = np.maximum(hist - prazo_prometido, 0)
        custo_atraso = float(np.mean(custo_esperado_atraso(np.full(len(hist), valor), atrasos)))
        linhas.append({
            "transportadora": q["transportadora"],
            "frete": round(float(q["valor_cotado"]), 2),
            "prazo_contratado": int(q["prazo_transportadora_dias_uteis"]),
            "entregas_no_prazo": round(float(np.mean(hist <= prazo_prometido)), 4),
            "prazo_9_em_10": float(np.ceil(np.percentile(hist, 92))),
            "custo_atraso_esperado": round(custo_atraso, 2),
            "custo_total_esperado": round(float(q["valor_cotado"]) + custo_atraso, 2),
            "base_do_historico": base,
            "entregas_no_historico": int(len(hist)),
            "e_a_padrao_da_regiao": bool(q["transportadora"] == padrao),
            "foi_a_escolhida_no_erp": bool(q["selecionada"] == 1),
        })
    if not linhas:
        return {"erro": f"sem histórico para avaliar o envio {envio_id}"}
    linhas.sort(key=lambda x: x["custo_total_esperado"])
    melhor, atual = linhas[0], next((x for x in linhas if x["foi_a_escolhida_no_erp"]), None)
    economia = round(atual["custo_total_esperado"] - melhor["custo_total_esperado"], 2) if atual else None
    return {
        "envio_id": envio_id,
        "destino": f"{e['cidade']}/{e['uf']}",
        "prefixo_cep": e["cep3"],
        "peso_g": int(e["peso_g"]),
        "valor_pedido": round(valor, 2),
        "prazo_prometido_ao_cliente": prazo_prometido,
        "data_prometida": str(e["data_prometida"].date()),
        "transportadora_padrao_da_regiao": padrao,
        "ja_postado": bool(pd.notna(e["data_postagem"])),
        "melhor_rota": melhor["transportadora"],
        "economia_vs_escolha_atual": economia,
        "candidatas": linhas,
    }


def envios_para_rotear(uf: str | None = None, limite: int = 20) -> pd.DataFrame:
    """Envios novos que ainda não foram postados: são os que o analista pode rotear."""
    c = ctx()
    nao_postados = c.envios[c.envios["data_postagem"].isna()]
    if uf:
        nao_postados = nao_postados[nao_postados["uf"] == uf.upper()]
    return nao_postados.sort_values("data_pedido", ascending=False).head(limite)


def lote(uf: str | None = None, limite: int = 12) -> dict:
    """Avalia um lote de envios não postados e separa os que valem trocar de transportadora."""
    alvos = envios_para_rotear(uf, limite)
    avaliados = [avaliar(i) for i in alvos["envio_id"]]
    bons = [a for a in avaliados if "erro" not in a]
    def muda(a):
        atual = next((x["transportadora"] for x in a["candidatas"] if x["foi_a_escolhida_no_erp"]), None)
        return a["melhor_rota"] != atual and (a["economia_vs_escolha_atual"] or 0) > 0.5

    trocar = [a for a in bons if muda(a)]
    return {
        "envios_avaliados": len(bons),
        "envios_que_valem_trocar": len(trocar),
        "economia_total_estimada": round(sum(a["economia_vs_escolha_atual"] or 0 for a in trocar), 2),
        "detalhe": trocar[:limite],
    }
