"""Frente 4: prazo do site por região. Propõe o prazo que vende sem quebrar o SLA.

O agente PROPÕE; quem aprova é o gerente de logística (politicas.csv: toda mudança regional de
prazo exibido passa por aprovação). Aqui só se calcula a proposta e a evidência.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .concorrentes import posicao, prazo_concorrentes_por_prefixo
from .config import META_CUMPRIMENTO, MIN_ENVIOS_PREFIXO, RAW

CONTATO_RS = 9.0
LOGISTICA_REVERSA_RS = 12.0
MARGEM_PRODUTO = 0.55


def _prob_contato(atraso):
    return np.select([atraso >= 6, atraso >= 3, atraso >= 1], [0.85, 0.60, 0.35], 0.0)


def _prob_cancel(atraso):
    return np.select([atraso > 10, atraso >= 6, atraso >= 3, atraso >= 1], [0.40, 0.22, 0.10, 0.04], 0.0)


def custo_esperado_atraso(valor_pedido, atraso_du) -> np.ndarray:
    """Custo esperado, em R$, de entregar `atraso_du` dias úteis depois do prometido (parametros.md)."""
    valor = np.asarray(valor_pedido, dtype=float)
    a = np.asarray(atraso_du, dtype=float)
    contato = _prob_contato(a) * CONTATO_RS
    cancel = _prob_cancel(a) * (MARGEM_PRODUTO * valor + LOGISTICA_REVERSA_RS)
    return contato + cancel


def regras_atuais() -> pd.DataFrame:
    r = pd.read_csv(RAW / "regras_site_prazo_frete_por_prefixo.csv", dtype={"prefixo_cep3": str})
    return r.rename(columns={"prefixo_cep3": "cep3"})


def _frase(acao, atual, seguro, cump, n, transp):
    if acao == "sem evidência":
        return f"Poucos envios medidos ({n}) para a {transp}. Manter o prazo e continuar medindo."
    base = f"Com a {transp}, 9 em cada 10 entregas chegam em até {seguro:g} dias úteis."
    if acao == "aumentar":
        return (f"{base} O site mostra {atual:g}, então hoje só {cump:.0%} chegam no prazo "
                f"(meta {META_CUMPRIMENTO:.0%}). Sugerimos mostrar {seguro:g}.")
    if acao == "reduzir":
        return (f"{base} O site mostra {atual:g}: há folga. Dá para mostrar {seguro:g} e ficar "
                f"mais competitivo sem quebrar a meta.")
    return f"{base} O prazo atual ({atual:g}) está certo. Manter."


def gerar(df: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por prefixo de CEP, com o prazo proposto, o motivo e o que fazer com ele."""
    regras = regras_atuais()
    conc = prazo_concorrentes_por_prefixo()
    linhas = []
    medidos = df[df["medido"]]
    for _, r in regras.iterrows():
        d = medidos[(medidos["cep3"] == r["cep3"]) & (medidos["transportadora"] == r["transportadora_padrao"])]
        ent = d[d["status"] == "entregue"]
        n = len(d)
        atual = float(r["prazo_exibido_dias_uteis"])
        piso = float(r["sla_contratual_dias_uteis"]) + 1  # 1 dia de separação + SLA do contrato
        seguro = np.nan

        def cumpre(prazo):  # parte dos envios que chegaria no prazo se o site mostrasse `prazo`
            return float(((d["status"] == "entregue") & (d["prazo_real_du"] <= prazo)).mean()) if n else np.nan

        cump = cumpre(atual)
        if n >= MIN_ENVIOS_PREFIXO and len(ent):
            seguro = float(math.ceil(np.nanpercentile(ent["prazo_real_du"], META_CUMPRIMENTO * 100)))
            seguro = max(seguro, 2.0)  # mínimo absoluto de 2 dias úteis (politicas.csv)
        if np.isnan(seguro):
            acao, novo = "sem evidência", atual
        elif atual < seguro:
            acao, novo = "aumentar", seguro
        elif atual > seguro + 1:
            acao, novo = "reduzir", seguro
        else:
            acao, novo = "manter", atual
        # o que mudaria em custo de atraso se o prazo do site fosse `novo`
        impacto = 0.0
        if n and acao in ("aumentar", "reduzir"):
            real = ent["prazo_real_du"].to_numpy()
            falhas = d[d["status"] != "entregue"]
            c_atual = custo_esperado_atraso(ent["valor_pedido"], np.maximum(real - atual, 0)).sum()
            c_novo = custo_esperado_atraso(ent["valor_pedido"], np.maximum(real - novo, 0)).sum()
            impacto = float(c_atual - c_novo)  # positivo = economiza; negativo = custa
        linhas.append({
            "cep3": r["cep3"], "uf": r["uf"], "cidade_referencia": r["cidade_referencia"],
            "localidade": r["localidade"], "transportadora": r["transportadora_padrao"],
            "envios_medidos": n, "cumprimento_hoje": cump, "cumprimento_proposto": cumpre(novo),
            "prazo_site_hoje": atual, "prazo_seguro": seguro, "prazo_proposto": novo,
            "acao": acao, "abaixo_do_contrato": bool(novo < piso),
            "impacto_custo_atraso_rs": round(impacto, 2),
            "resumo": _frase(acao, atual, novo, cump, n, r["transportadora_padrao"]),
        })
    out = pd.DataFrame(linhas).merge(conc, on="cep3", how="left")
    out["posicao_hoje"] = [posicao(a, m, md) for a, m, md in
                           zip(out["prazo_site_hoje"], out["prazo_conc_melhor"], out["prazo_conc_mediana"])]
    out["posicao_proposta"] = [posicao(a, m, md) for a, m, md in
                               zip(out["prazo_proposto"], out["prazo_conc_melhor"], out["prazo_conc_mediana"])]
    # toda mudança regional passa pelo gerente (politicas.csv); sem mudança, não há o que aprovar
    out["requer_aprovacao"] = out["acao"].isin(["aumentar", "reduzir"])
    out["aprovador"] = np.where(out["requer_aprovacao"], "gerente de logística", "")
    return out.sort_values(["requer_aprovacao", "impacto_custo_atraso_rs"], ascending=[False, False]).reset_index(drop=True)
