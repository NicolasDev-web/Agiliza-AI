"""Dicas do agente para o analista: o que valeria pedir à Marina agora, pelos dados.

Pega as regiões em que o prazo do site mais custa em atraso e que ainda não estão na fila nem foram aprovadas.
"""
from __future__ import annotations

from . import estado
from .agente import ferramentas as F


def _pct(x) -> str:
    return "–" if x is None else f"{round(x * 100)}%"


def dicas_de_prazo(quantas: int = 3) -> list[dict]:
    ocupados: set[str] = set()
    for a in estado.listar_aprovacoes(None):
        if a["situacao"] in ("pendente", "aprovada", "ajustada"):
            ocupados.update(str(p) for p in (a.get("prefixos") or []))
    ocupados.update(estado.prazos_vigentes())
    linhas = F.ver_propostas_de_prazo(acao="aumentar", top=quantas + len(ocupados) + 2)["linhas"]
    saida = []
    for l in linhas:
        if l["cep3"] in ocupados:
            continue
        saida.append({
            "cep3": l["cep3"], "cidade": l["cidade_referencia"], "uf": l["uf"], "hoje": int(l["prazo_site_hoje"]),
            "proposto": int(l["prazo_proposto"]), "no_prazo": l["cumprimento_hoje"], "impacto": l["impacto_custo_atraso_rs"],
            "motivo": f"A {l['transportadora']} entrega {_pct(l['cumprimento_hoje'])} no prazo ali; o site promete {int(l['prazo_site_hoje'])} dias.",
            "pedido": f"Peça à Marina para mudar o prazo de {l['cidade_referencia']} para {int(l['prazo_proposto'])} dias",
        })
        if len(saida) == quantas:
            break
    return saida
