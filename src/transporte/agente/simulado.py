"""Roteiro local, para quando a API do evento não está à mão.

Chama as MESMAS ferramentas e emite os MESMOS eventos do agente com IA; o que muda é quem
decide a sequência: aqui é um roteiro por palavra-chave, não um modelo. A interface mostra isso
com todas as letras, para ninguém confundir uma coisa com a outra.
"""
from __future__ import annotations

import re
import time
import unicodedata
from typing import Iterator

from . import ferramentas as F
from .loop import _evento, rotulo_da_ferramenta

PAUSA = 0.12


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c))


def _lugar_na_pergunta(t: str) -> tuple[str | None, str | None]:
    """Acha uma cidade do painel na frase e devolve (uf, prefixo)."""
    from .contexto import tabela
    s = _sem_acento(t)
    achado = (None, None)
    for r in tabela("regras").itertuples():
        nome = _sem_acento(r.cidade_referencia)
        if len(nome) >= 5 and nome in s:
            achado = (r.uf, r.cep3)
            break
    return achado


def _uf_na_pergunta(t: str) -> str | None:
    """A UF citada na frase. Nomes com acento são conferidos com acento, para 'para' (preposição)
    não virar Pará."""
    ufs = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB",
           "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]
    com_acento = {"pará": "PA", "paraná": "PR", "ceará": "CE", "goiás": "GO", "amapá": "AP",
                  "maranhão": "MA", "piauí": "PI", "espírito santo": "ES"}
    sem_acento = {"sao paulo": "SP", "rio de janeiro": "RJ", "minas gerais": "MG", "minas": "MG",
                  "bahia": "BA", "pernambuco": "PE", "brasilia": "DF", "belem": "PA", "manaus": "AM",
                  "fortaleza": "CE", "salvador": "BA", "recife": "PE", "curitiba": "PR",
                  "porto alegre": "RS", "rio grande do sul": "RS", "santa catarina": "SC"}
    baixo = t.lower()
    for nome, uf in com_acento.items():
        if nome in baixo:
            return uf
    s = _sem_acento(t)
    for nome, uf in sem_acento.items():
        if nome in s:
            return uf
    for uf in ufs:
        if f" {uf.lower()} " in f" {s} ":
            return uf
    return None


def _transportadora_na_pergunta(t: str) -> str | None:
    s = _sem_acento(t)
    for nome in ["Expressa Já", "TransNorte", "Rápido Sul", "ViaLog", "Correio Ágil"]:
        if _sem_acento(nome) in s:
            return nome
    return None


REGIOES = {
    "nordeste": ["MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA"],
    "norte": ["AC", "AP", "AM", "PA", "RO", "RR", "TO"],
    "sudeste": ["SP", "RJ", "MG", "ES"],
    "sul": ["PR", "SC", "RS"],
    "centro oeste": ["DF", "GO", "MT", "MS"],
}


def _regiao_na_pergunta(t: str) -> tuple[str | None, list[str]]:
    """'Nordeste', 'Sul'... Os nomes das transportadoras (TransNorte, Rápido Sul) não contam como região."""
    s = _sem_acento(t).replace("transnorte", " ").replace("rapido sul", " ").replace("-", " ")
    for nome, ufs in REGIOES.items():
        if re.search(rf"\b{nome}\b", s):
            return nome, ufs
    return None, []


def _cep_na_pergunta(t: str) -> tuple[str | None, str | None, bool]:
    """CEP escrito na frase -> (uf, prefixo medido, aproximado). Se o prefixo exato não é medido, usa o mais próximo."""
    from .contexto import tabela
    m = re.search(r"(?<!\d)(\d{5})(?:-?\d{3})?(?!\d)|cep\s*(\d{3,5})", _sem_acento(t))
    if not m:
        return None, None, False
    cep3 = (m.group(1) or m.group(2))[:3].zfill(3)
    regras = tabela("regras")
    exato = regras[regras["cep3"].astype(str).str.zfill(3) == cep3]
    if len(exato):
        return exato.iloc[0]["uf"], cep3, False
    alvo = int(cep3)
    prox = min(regras.itertuples(), key=lambda r: abs(int(r.cep3) - alvo))
    return prox.uf, str(prox.cep3).zfill(3), True


def _cidade_do_prefixo(prefixo: str | None) -> str | None:
    if not prefixo:
        return None
    from .contexto import tabela
    r = tabela("regras")
    r = r[r["cep3"].astype(str).str.zfill(3) == prefixo]
    return f"{r.iloc[0]['cidade_referencia']}/{r.iloc[0]['uf']}" if len(r) else None


SAUDACAO = re.compile(r"(oi+|ola|opa|e ai|hey|hello|bom dia|boa tarde|boa noite|ajuda|help|o que (voce )?(faz|sabe fazer)|quem (e )?voce)[ !.?]*")


def _rodar(sessao, nome: str, args: dict) -> Iterator[dict]:
    yield _evento("ferramenta", nome=nome, argumentos=args,
                  tipo_ferramenta=F.POR_NOME[nome].tipo, rotulo=rotulo_da_ferramenta(nome, args))
    time.sleep(PAUSA)
    res = F.executar(nome, args, sessao.papel, sessao.diario)
    yield _evento("resultado", nome=nome, resultado=res, recusado=bool(res.get("recusado")), custo=sessao.diario.custo)
    time.sleep(0.04)
    sessao._ultimo = res


def _fim(sessao, texto: str) -> dict:
    nota = getattr(sessao, "_nota", None)
    if nota:
        texto, sessao._nota = f"{nota}\n\n{texto}", None
    return _evento("resposta", texto=texto, diario=sessao.diario.acoes, custo=sessao.diario.custo)


def _pct(x) -> str:
    return "–" if x is None else f"{round(x * 100)}%"


def _brl(x) -> str:
    return "–" if x is None else f"R$ {x:,.0f}".replace(",", ".")


# --------------------------------------------------------------------------- roteiros
def _problemas(sessao, uf, local=None) -> Iterator[dict]:
    passos = list(_rodar(sessao, "consultar_problemas", {"agrupar_por": "transportadora", **({"uf": uf} if uf else {})}))
    yield from passos
    por_transp = sessao._ultimo.get("linhas", [])
    yield from _rodar(sessao, "consultar_problemas", {"agrupar_por": "motivo", **({"uf": uf} if uf else {})})
    por_motivo = sessao._ultimo.get("linhas", [])
    yield from _rodar(sessao, "consultar_problemas", {"agrupar_por": "uf" if not uf else "prefixo_cep", "top": 5, **({"uf": uf} if uf else {})})
    por_lugar = sessao._ultimo.get("linhas", [])

    pior = por_transp[0] if por_transp else {}
    m1 = por_motivo[0] if por_motivo else {}
    def _lugar(l):
        taxa = l.get("chamados_por_100_envios")
        onde = l.get("uf") or l.get("cep3")
        return f"{onde} ({taxa} por 100 envios)" if taxa else f"{onde} ({int(l.get('chamados', 0))} chamados)"

    lugares = ", ".join(_lugar(l) for l in por_lugar[:3])
    texto = (
        f"Olhei os chamados e as ocorrências{' de ' + local if local else ''}, de 03/09 a 02/11.\n\n"
        f"*Quem mais dá trabalho:* {pior.get('transportadora')}, com {pior.get('chamados_por_100_envios')} chamados "
        f"a cada 100 envios ({int(pior.get('chamados', 0))} chamados e {int(pior.get('extravios', 0))} extravios).\n"
        f"*O que mais aparece:* {str(m1.get('motivo', '')).replace('_', ' ')} ({int(m1.get('chamados', 0))} chamados), "
        f"respondidos em cerca de {round(m1.get('horas_ate_resposta') or 0)} horas.\n"
        f"*Onde dói mais:* {lugares}.\n\n"
        "Atraso na entrega é o motivo campeão, e é justamente o que o prazo do site resolve. "
        "Quer que eu monte a proposta de prazo dessas regiões?"
    )
    yield _fim(sessao, texto)


def _rota(sessao, uf, pergunta) -> Iterator[dict]:
    achado = re.search(r"\bENV\s?(\d{7})\b", pergunta, re.I)
    envio = f"ENV{achado.group(1)}" if achado else None
    if envio:
        yield from _rodar(sessao, "escolher_melhor_rota", {"envio_id": envio})
        r = sessao._ultimo
        if "erro" in r:
            yield _fim(sessao, f"Não achei esse envio: {r['erro']}")
            return
        melhor = r["candidatas"][0]
        atual = next((c for c in r["candidatas"] if c["foi_a_escolhida_no_erp"]), None)
        linhas = "\n".join(
            f"{'✅' if c['transportadora'] == r['melhor_rota'] else '▫️'} {c['transportadora']}: frete "
            f"R$ {c['frete']:.2f}, {_pct(c['entregas_no_prazo'])} no prazo, custo total R$ {c['custo_total_esperado']:.2f}"
            for c in r["candidatas"][:4])
        texto = (f"*{r['envio_id']} → {r['destino']}* ({r['peso_g']} g, prometido em {int(r['prazo_prometido_ao_cliente'])} dias úteis)\n\n"
                 f"{linhas}\n\n*Melhor rota: {r['melhor_rota']}.* "
                 + (f"Hoje está na {atual['transportadora']}; trocar economiza R$ {r['economia_vs_escolha_atual']:.2f}."
                    if atual and atual["transportadora"] != r["melhor_rota"] else "Já é a que está no pedido.")
                 + "\n\nConta o frete mais o custo esperado de atraso, pelo histórico da transportadora nessa região.")
        yield _fim(sessao, texto)
        return

    yield from _rodar(sessao, "escolher_melhor_rota", {"limite": 15, **({"uf": uf} if uf else {})})
    lote = sessao._ultimo
    yield from _rodar(sessao, "rotear_envios", {"limite": 15, **({"uf": uf} if uf else {})})
    feito = sessao._ultimo
    exemplos = "\n".join(f"• {f['envio_id']} {f['destino']}: {f['de']} → *{f['para']}* (economiza R$ {f['economia_estimada']:.2f})"
                         for f in feito.get("roteados", [])[:5])
    barrados = feito.get("nao_roteados", [])
    texto = (f"Avaliei {lote.get('envios_avaliados', 0)} envios novos{' de ' + uf if uf else ''} que ainda não foram coletados.\n\n"
             f"Troquei a transportadora de *{len(feito.get('roteados', []))}* deles, economia estimada de "
             f"*{_brl(feito.get('economia_total'))}*:\n{exemplos or '• nenhum valia a troca'}\n")
    if barrados:
        texto += f"\nDeixei {len(barrados)} de fora: {barrados[0]['motivo']}"
    texto += "\n\nEssa parte é minha, faço sem aprovação. Mudar a transportadora padrão da região já seria proposta para a Marina."
    if feito.get("gerente_avisado"):
        texto += "\nA Marina já recebeu o alerta financeiro: frete, atraso evitado e saldo dessas trocas."
    yield _fim(sessao, texto)


def _lugares_na_pergunta(t: str) -> list[dict]:
    """Todas as cidades do painel citadas na frase, na ordem em que aparecem, cada uma com o prazo que a pessoa pediu
    logo depois do nome ("Marabá para 18"), se houver."""
    from .contexto import tabela
    s = _sem_acento(t)
    achados = []
    for r in tabela("regras").itertuples():
        nome = _sem_acento(r.cidade_referencia)
        if len(nome) < 5:
            continue
        m = re.search(rf"\b{re.escape(nome)}\b", s)
        if m and all(a["cep3"] != r.cep3 for a in achados):
            achados.append({"cep3": r.cep3, "uf": r.uf, "cidade": r.cidade_referencia, "pos": m.start(), "fim": m.end()})
    # "Vitória" dentro de "Vitória da Conquista" não conta: vale o nome mais longo
    achados = [a for a in achados if not any(o is not a and o["pos"] <= a["pos"] and a["fim"] <= o["fim"] and (o["fim"] - o["pos"]) > (a["fim"] - a["pos"]) for o in achados)]
    achados.sort(key=lambda a: a["pos"])
    for i, a in enumerate(achados):
        limite = achados[i + 1]["pos"] if i + 1 < len(achados) else len(s)
        n = re.search(r"\b(?:para|pra|em|ficar|fique|seja|->|=|de)?\s*(\d{1,2})\s*(?:dias|d\b|du\b)?", s[a["fim"]:limite])
        a["valor"] = int(n.group(1)) if n else None
    return achados


def _quantos(s: str) -> int | None:
    """"as 3 maiores", "as cinco principais", "todas": quantas regiões a pessoa quer."""
    m = re.search(r"\b(\d{1,2}|dois|duas|tres|quatro|cinco)\s+(?:maiores|principais|primeiras|regioes|regiao|prazos|mudancas|pedidos)", s)
    if m:
        return {"dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5}.get(m.group(1)) or int(m.group(1))
    return 5 if re.search(r"\b(todas|todos|tudo|varias|varios|multiplas)\b", s) else None


def _propor_uma(sessao, p: dict, valor=None) -> Iterator[dict]:
    """Mede, compara, propõe e leva à Marina uma região. Deixa o resumo em sessao._resumo_pedido."""
    yield from _rodar(sessao, "medir_desempenho", {"prefixo_cep": p["cep3"]})
    yield from _rodar(sessao, "consultar_concorrentes", {"prefixo_cep": p["cep3"]})
    conc = (sessao._ultimo.get("linhas") or [{}])[0]
    novo = int(valor) if valor else int(p["prazo_proposto"])
    verbo = "Subir" if novo > p["prazo_site_hoje"] else "Baixar"
    evidencia = (f"Prefixo {p['cep3']} ({p['cidade_referencia']}/{p['uf']}), {p['transportadora']}, "
                 f"03/09 a 02/11: {int(p['envios_medidos'])} envios medidos, {_pct(p['cumprimento_hoje'])} no prazo "
                 f"(meta 92%). Prazo do site {int(p['prazo_site_hoje'])} dias; 9 em cada 10 entregas levam até "
                 f"{int(p['prazo_proposto'])}. Impacto estimado: {_brl(p['impacto_custo_atraso_rs'])}.")
    yield from _rodar(sessao, "propor_mudanca", {"tipo": "prazo_exibido", "prefixos_cep": [p["cep3"]],
                                                 "valor_novo": novo, "evidencia": evidencia,
                                                 "impacto_estimado_reais": p["impacto_custo_atraso_rs"]})
    proposta = sessao._ultimo
    resumo = (f"{verbo} o prazo do site de {int(p['prazo_site_hoje'])} para {novo} dias úteis no "
              f"prefixo {p['cep3']} ({p['cidade_referencia']}/{p['uf']}).")
    yield from _rodar(sessao, "solicitar_aprovacao", {"resumo": resumo, "evidencia": evidencia, "proposta_id": proposta.get("proposta_id")})
    sessao._resumo_pedido = {"p": p, "novo": novo, "verbo": verbo, "conc": conc, "erro": sessao._ultimo.get("erro"),
                             "repetido": "já estava na fila" in str(sessao._ultimo.get("situacao", ""))}


def _prazo(sessao, uf, pergunta) -> Iterator[dict]:
    s = _sem_acento(pergunta)
    lugares = _lugares_na_pergunta(pergunta)
    quer = _quantos(s)
    filtro = {"uf": uf} if uf else {}
    if lugares or quer:   # um ou vários pedidos de uma vez
        # cidades citadas: o filtro de estado atrapalharia (Juazeiro existe em mais de um estado, e a frase pode misturar estados)
        yield from _rodar(sessao, "ver_propostas_de_prazo", {"top": 200, **({} if lugares else filtro)})
        todas = sessao._ultimo.get("linhas", [])
        if lugares:
            por_cep = {l["cep3"]: l for l in todas}
            alvos = [(por_cep[l["cep3"]], l["valor"]) for l in lugares if l["cep3"] in por_cep]
        else:
            yield from _rodar(sessao, "ver_propostas_de_prazo", {"acao": "aumentar", "top": quer, **filtro})
            alvos = [(l, None) for l in sessao._ultimo.get("linhas", [])]
        if not alvos:
            yield _fim(sessao, "Não achei região com proposta de prazo nesse filtro.")
            return
    else:
        yield from _rodar(sessao, "ver_propostas_de_prazo", {"acao": "aumentar", "top": 5, **filtro})
        props = sessao._ultimo.get("linhas", [])
        if not props:
            yield from _rodar(sessao, "ver_propostas_de_prazo", {"top": 5, **filtro})
            props = sessao._ultimo.get("linhas", [])
        if not props:
            yield _fim(sessao, "Não achei região com proposta de prazo nesse filtro.")
            return
        alvos = [(props[0], None)]

    enviados, deixados = [], []
    for p, valor in alvos[:6]:
        if p["acao"] not in ("aumentar", "reduzir") and not valor:
            deixados.append(p)
            continue
        yield from _propor_uma(sessao, p, valor)
        enviados.append(sessao._resumo_pedido)

    if not enviados:
        p = deixados[0]
        yield _fim(sessao, f"*{p['cidade_referencia']}/{p['uf']}*: a {p['transportadora']} entrega {_pct(p['cumprimento_hoje'])} no prazo e "
                           f"o site mostra {int(p['prazo_site_hoje'])} dias úteis. Está no lugar certo, não mexeria.")
        return
    if len(enviados) == 1:
        e = enviados[0]; p, conc = e["p"], e["conc"]
        texto = (f"*{p['cidade_referencia']}/{p['uf']}, prefixo {p['cep3']}*\n\n"
                 f"A {p['transportadora']} entrega {_pct(p['cumprimento_hoje'])} no prazo ali"
                 + (", bem abaixo da meta de 92%" if (p["cumprimento_hoje"] or 1) < 0.92 else "") + ". "
                 f"O site promete {int(p['prazo_site_hoje'])} dias e 9 em cada 10 entregas levam até "
                 f"{int(p['prazo_proposto'])} dias úteis.\n"
                 + (f"Os concorrentes mostram cerca de {int(conc['prazo_conc_mediana'])} dias nessa região.\n" if conc.get("prazo_conc_mediana") else "")
                 + f"\n{e['verbo']} para {e['novo']} dias "
                 + ("evita cerca de " + _brl(p["impacto_custo_atraso_rs"]) + " de custo com atraso" if e["verbo"] == "Subir"
                    else "deixa a gente mais competitivo sem furar a meta")
                 + ".\n\n" + ("Esse pedido já estava na fila da Marina." if e["repetido"] else "Mandei para a Marina: mudar o prazo do site não é decisão minha."))
        yield _fim(sessao, texto)
        return
    linhas = "\n".join(
        f"• *{e['p']['cidade_referencia']}/{e['p']['uf']}*: {int(e['p']['prazo_site_hoje'])} → {e['novo']} dias úteis "
        f"({_pct(e['p']['cumprimento_hoje'])} no prazo hoje, evita {_brl(e['p']['impacto_custo_atraso_rs'])})"
        + (" · já estava na fila" if e["repetido"] else "") for e in enviados)
    total = sum(e["p"]["impacto_custo_atraso_rs"] or 0 for e in enviados)
    texto = f"Montei *{len(enviados)} pedidos* de prazo, cada um com a sua evidência, e mandei para a Marina:\n\n{linhas}\n\nJuntos evitam cerca de {_brl(total)} de custo com atraso."
    if deixados:
        texto += "\nDeixei de fora " + ", ".join(d["cidade_referencia"] for d in deixados) + ": o prazo do site já está certo."
    texto += "\nA Marina decide um por um; você acompanha aqui e no seu WhatsApp."
    yield _fim(sessao, texto)


def _impacto(sessao, propor: bool = True) -> Iterator[dict]:
    """Quanto o atraso custa: soma do custo evitável nas regiões em que o site promete menos do que se entrega."""
    yield from _rodar(sessao, "ver_propostas_de_prazo", {"acao": "aumentar", "top": 200})
    ls = sessao._ultimo.get("linhas", [])
    total = sum(l.get("impacto_custo_atraso_rs") or 0 for l in ls)
    if not ls:
        yield _fim(sessao, "Não sobrou região com custo de atraso evitável: tudo que dava para corrigir já foi aprovado.")
        return
    top = "\n".join(f"• {l['cidade_referencia']}/{l['uf']}: {_brl(l['impacto_custo_atraso_rs'])} (site {int(l['prazo_site_hoje'])} → {int(l['prazo_proposto'])} dias)" for l in ls[:3])
    texto = (f"Nos 60 dias medidos (03/09 a 02/11), o atraso custou cerca de *{_brl(total)}* em *{len(ls)}* regiões em que o site "
             f"promete menos do que a transportadora entrega, uns *{_brl(total / 2)} por mês*.\n\n"
             f"*Maiores custos:*\n{top}\n\n"
             "Conta só o custo de atraso (regras de parametros.md); o efeito na conversão ainda não entra. ")
    texto += "Quer que eu monte a proposta da primeira região para a Marina?" if propor else "A decisão é sua; eu só mostro a conta."
    yield _fim(sessao, texto)


def _regiao(sessao, nome: str, ufs: list[str], concorrentes: bool) -> Iterator[dict]:
    """Uma região inteira (Nordeste, Sul...): roda a ferramenta estado por estado e resume."""
    nome_bonito = nome.replace("centro oeste", "Centro-Oeste").title()
    linhas = []
    for uf in ufs:
        yield from _rodar(sessao, "consultar_concorrentes" if concorrentes else "ver_propostas_de_prazo",
                          {"uf": uf} if concorrentes else {"uf": uf, "top": 200})
        linhas += sessao._ultimo.get("linhas", [])
    if not linhas:
        yield _fim(sessao, f"Não achei dados do {nome_bonito}.")
        return
    if concorrentes:
        lentos = sorted((l for l in linhas if (l.get("diferenca") or 0) > 0), key=lambda l: -l["diferenca"])
        fretes = sorted(l["frete_conc_mediana"] for l in linhas if l.get("frete_conc_mediana"))
        top = "\n".join(f"• {l['cidade_referencia']}/{l['uf']}: nosso site {int(l['nosso_prazo'])} dias, concorrentes {int(l['prazo_conc_mediana'])} (+{int(l['diferenca'])})" for l in lentos[:4])
        yield _fim(sessao, f"*{nome_bonito}* ({len(linhas)} prefixos olhados): mostramos prazo maior que o dos concorrentes em *{len(lentos)}*.\n"
                           + (f"O frete mediano deles fica em torno de R$ {fretes[len(fretes) // 2]:.2f}.\n" if fretes else "")
                           + (f"\n*Onde estamos mais atrás:*\n{top}\n" if top else "\nNão estamos atrás em nenhum prefixo.\n")
                           + "\nObservação: produto esgotado no concorrente mostra 1 dia sem ser prazo real; isso fica de fora.")
        return
    aum = sorted((l for l in linhas if l.get("acao") == "aumentar"), key=lambda l: -(l.get("impacto_custo_atraso_rs") or 0))
    red = [l for l in linhas if l.get("acao") == "reduzir"]
    top = "\n".join(f"• {l['cidade_referencia']}/{l['uf']}: site {int(l['prazo_site_hoje'])} → {int(l['prazo_proposto'])} dias ({_brl(l['impacto_custo_atraso_rs'])})" for l in aum[:4])
    yield _fim(sessao, f"*{nome_bonito}*: de {len(linhas)} prefixos, *{len(aum)}* precisam de prazo maior e *{len(red)}* podem baixar.\n"
                       + (f"\n*Mais urgentes:*\n{top}\n" if top else "")
                       + "\nQuer que eu monte a proposta de uma delas para a Marina?")


def _ola(sessao) -> Iterator[dict]:
    if sessao.papel == F.PAPEL_CONSULTA:
        yield _fim(sessao, "Oi, Marina! Eu explico o que o analista propôs e mostro os números, mas a decisão é sua. "
                           "Pergunte, por exemplo: “O que está esperando minha decisão?”, “Por que Marabá?” ou “Quanto perdemos por mês com atraso?”")
    else:
        yield _fim(sessao, "Oi, Lucas! Eu leio os portais das transportadoras, meço quem entrega no prazo e monto propostas de prazo para a Marina. "
                           "Pergunte, por exemplo: “Qual prazo do site precisa mudar?”, “Qual a melhor rota para os envios novos de SP?” "
                           "ou “Onde resolvemos mais problemas?”")


def _quer_custo(s: str) -> bool:
    return bool(re.search(r"perd|prejuizo|quanto (a gente )?(custa|gasta|economiz)|custo|impacto|dinheiro|em reais", s))


def _quer_ranking(s: str) -> bool:
    """'Melhores transportadoras do Nordeste', 'pior do Sul', 'como estão as entregas no Sudeste'."""
    if re.search(r"problema|reclama|chamado|extravio|avaria|resolvemos|rota|rotear|envios? novo|despach|propost|precisa mudar|prazo do site", s) or _quer_concorrente(s):
        return False
    return bool(re.search(r"transportadora|melhor|pior|ranking|entrega|desempenho|cumprimento|no prazo|como esta|como estao|como vai", s))


def _ranking_regiao(sessao, nome: str, ufs: list[str]) -> Iterator[dict]:
    """Transportadoras de uma região, do melhor ao pior cumprimento de prazo (soma dos estados, ponderada pelos envios)."""
    nome_bonito = nome.replace("centro oeste", "Centro-Oeste").title()
    acum: dict[str, dict] = {}
    for uf in ufs:
        yield from _rodar(sessao, "medir_desempenho", {"uf": uf})
        for l in sessao._ultimo.get("linhas", []):
            a = acum.setdefault(l["transportadora"], {"envios": 0.0, "no_prazo": 0.0, "extravios": 0.0, "ufs": 0})
            e = float(l.get("envios") or 0)
            a["envios"] += e; a["no_prazo"] += e * float(l.get("cumprimento") or 0)
            a["extravios"] += float(l.get("extravios") or 0); a["ufs"] += 1
    if not acum:
        yield _fim(sessao, f"Não achei envios medidos no {nome_bonito}.")
        return
    rank = sorted(({"t": k, "c": v["no_prazo"] / v["envios"] if v["envios"] else 0, **v} for k, v in acum.items() if v["envios"] >= 30),
                  key=lambda x: -x["c"])
    linhas = "\n".join(f"{'🟢' if r['c'] >= 0.92 else '🔴'} {r['t']}: {_pct(r['c'])} no prazo ({int(r['envios'])} envios, {int(r['ufs'])} estados"
                       + (f", {int(r['extravios'])} extravios" if r["extravios"] else "") + ")" for r in rank)
    yield _fim(sessao, f"*{nome_bonito}*: transportadoras do melhor ao pior, de 03/09 a 02/11 ({len(ufs)} estados).\n\n{linhas}\n\n"
                       f"*Melhor:* {rank[0]['t']}. *Pior:* {rank[-1]['t']}. A meta é 92%.\n"
                       "Quer ver um estado em detalhe ou o que fazer com quem está abaixo?")


def _quer_problemas(s: str) -> bool:
    return bool(re.search(r"problema|reclama|chamado|extravio|avaria|resolvemos|dor", s))


def _problemas_regiao(sessao, nome: str, ufs: list[str]) -> Iterator[dict]:
    """Chamados e extravios de uma região inteira, por estado e por transportadora."""
    nome_bonito = nome.replace("centro oeste", "Centro-Oeste").title()
    por_uf: dict[str, dict] = {}
    por_transp: dict[str, float] = {}
    for uf in ufs:   # "uf" dá a taxa certa do estado; "transportadora" (filtrada pelo estado) dá quem gerou os chamados
        yield from _rodar(sessao, "consultar_problemas", {"agrupar_por": "uf", "uf": uf})
        for l in sessao._ultimo.get("linhas", []):
            por_uf[uf] = {"chamados": float(l.get("chamados") or 0), "extravios": float(l.get("extravios") or 0),
                          "taxa": float(l.get("chamados_por_100_envios") or 0)}
        yield from _rodar(sessao, "consultar_problemas", {"agrupar_por": "transportadora", "uf": uf})
        for l in sessao._ultimo.get("linhas", []):
            por_transp[l["transportadora"]] = por_transp.get(l["transportadora"], 0) + float(l.get("chamados") or 0)
    if not por_uf:
        yield _fim(sessao, f"Não achei chamados no {nome_bonito}.")
        return
    estados = sorted(por_uf.items(), key=lambda kv: -kv[1]["taxa"])[:4]
    transps = sorted(por_transp.items(), key=lambda kv: -kv[1])
    total = int(sum(v["chamados"] for v in por_uf.values())); extr = int(sum(v["extravios"] for v in por_uf.values()))
    yield _fim(sessao, f"*{nome_bonito}*, de 03/09 a 02/11: {total} chamados e {extr} extravios.\n\n"
                       "*Estados com mais chamados (por 100 envios):*\n"
                       + "\n".join(f"• {k}: {v['taxa']:.1f} ({int(v['chamados'])} chamados)" for k, v in estados)
                       + "\n\n*Transportadoras com mais chamados:*\n"
                       + "\n".join(f"• {k}: {int(v)} chamados" for k, v in transps[:5])
                       + "\n\nQuer que eu monte a proposta de prazo para onde dói mais?")


def _quer_concorrente(s: str) -> bool:
    return any(k in s for k in ["concorrente", "concorrencia", "barato", "competi", "mercado"])


def _quer_piloto(s: str) -> bool:
    return bool(re.search(r"sozinh|piloto|automatic|autonom|sem (eu|ninguem) pedir|por conta propria", s))


def _piloto(sessao) -> Iterator[dict]:
    """O que o agente decidiu sozinho em segundo plano."""
    yield from _rodar(sessao, "consultar_piloto_automatico", {"limite": 6})
    r = sessao._ultimo
    res, dec = r.get("resumo", {}), [d for d in r.get("decisoes", []) if d["tipo"] != "modo"]
    if not dec:
        yield _fim(sessao, "O piloto automático ainda não tomou nenhuma decisão neste cenário"
                           + (" (está pausado na tela da Marina)." if r.get("modo") == "pausado" else ". O primeiro ciclo roda em instantes."))
        return
    linhas = "\n".join(f"• {d['titulo']}" for d in dec[:5])
    yield _fim(sessao, f"Sozinho, em segundo plano, eu já: troquei *{res.get('rotas_trocadas', 0)}* rotas "
                       f"({_brl(res.get('economia_rotas'))} de saldo), abri *{res.get('incidentes', 0)}* incidente(s) com transportadora "
                       f"e levei *{res.get('propostas', 0)}* proposta(s) à Marina.\n\n*Últimas decisões:*\n{linhas}\n\n"
                       "Tudo dentro da política: prazo do site continua sendo decisão da Marina, e ela pode me pausar.")


def _status_aprovacoes(sessao) -> Iterator[dict]:
    yield from _rodar(sessao, "consultar_aprovacoes", {})
    r = sessao._ultimo
    pedidos = r.get("pedidos", [])
    if not pedidos:
        yield _fim(sessao, "Ainda não mandei nenhum pedido para a Marina nesta conversa. Quer que eu monte um?")
        return
    nomes = {"pendente": "⏳ aguardando a Marina", "aprovada": "✅ aprovado", "ajustada": "✅ aprovado com ajuste", "recusada": "❌ recusado"}
    linhas = []
    for p in pedidos[:5]:
        extra = f" (valor final: {p['valor_final']:g})" if p.get("valor_final") is not None else ""
        com = f"\n   Ela escreveu: \"{p['comentario_do_gerente']}\"" if p.get("comentario_do_gerente") else ""
        linhas.append(f"{nomes.get(p['situacao'], p['situacao'])}{extra}: {p['resumo']}{com}")
    pend = sum(1 for p in pedidos if p["situacao"] == "pendente")
    abre = (f"{pend} pedido(s) ainda esperando a Marina" if pend else "A Marina já respondeu tudo") + f", de {len(pedidos)} no total.\n\n"
    yield _fim(sessao, abre + "\n".join(linhas) +
               f"\n\nO cenário permite {r.get('limite')} aprovações; já foram {r.get('aprovadas_no_cenario')}.")


def _explicar(sessao, uf, prefixo, pergunta, gerente=True) -> Iterator[dict]:
    """Agente de consulta (gerente): explica uma região em palavras simples, sem propor nada."""
    filtro = {"uf": uf} if uf else {}
    yield from _rodar(sessao, "ver_propostas_de_prazo", {"top": 200, **filtro} if prefixo else {"acao": "aumentar", "top": 5, **filtro})
    props = sessao._ultimo.get("linhas", [])
    if prefixo:
        props = [l for l in props if l["cep3"] == prefixo]
    if not props:
        yield _fim(sessao, "Não achei uma região com proposta para explicar. Diga a cidade ou o estado.")
        return
    p = props[0]
    yield from _rodar(sessao, "consultar_concorrentes", {"prefixo_cep": p["cep3"]})
    conc = (sessao._ultimo.get("linhas") or [{}])[0]
    texto = (f"*{p['cidade_referencia']}/{p['uf']}*\n\n"
             f"A {p['transportadora']} entrega {_pct(p['cumprimento_hoje'])} no prazo ({int(p['envios_medidos'])} pedidos medidos). "
             f"O site promete {int(p['prazo_site_hoje'])} dias úteis; 9 em cada 10 entregas levam até {int(p['prazo_proposto'])}.\n")
    if conc.get("prazo_conc_mediana"):
        texto += f"Os concorrentes mostram cerca de {int(conc['prazo_conc_mediana'])} dias.\n"
    if p["acao"] in ("aumentar", "reduzir"):
        texto += f"\nA conta aponta para {int(p['prazo_proposto'])} dias ({_brl(p['impacto_custo_atraso_rs'])} de custo de atraso em jogo)."
    texto += "\n\nA decisão é sua: eu só explico." if gerente else "\n\nSe quiser, monto a proposta e mando para a Marina."
    yield _fim(sessao, texto)


def _consulta(sessao, pergunta, s, uf, prefixo, transp, regiao=None, local=None) -> Iterator[dict]:
    if any(k in s for k in ["pedido", "pendente", "esperando", "aprovacao", "aprovacoes"]):
        yield from _status_aprovacoes(sessao)
    elif _quer_custo(s):
        yield from _impacto(sessao, propor=False)
    elif regiao and not prefixo and _quer_ranking(s):
        yield from _ranking_regiao(sessao, regiao[0], regiao[1])
    elif regiao and not prefixo and _quer_problemas(s):
        yield from _problemas_regiao(sessao, regiao[0], regiao[1])
    elif any(k in s for k in ["problema", "reclama", "chamado", "extravio", "pior"]):
        yield from _problemas(sessao, uf, local)
    elif regiao and not any(k in s for k in ["aprova", "troca", "muda", "propon"]):
        yield from _regiao(sessao, regiao[0], regiao[1], concorrentes=_quer_concorrente(s))
    elif any(k in s for k in ["aprova", "troca", "muda", "propon", "proponha"]):
        yield _fim(sessao, "Isso eu não faço: quem aprova é você, na fila de decisões, e as trocas de rota ficam com o analista. "
                           "Posso explicar qualquer pedido, se quiser.")
    elif prefixo or any(k in s for k in ["por que", "porque", "prazo", "explica", "concorrente"]):
        yield from _explicar(sessao, uf, prefixo, pergunta)
    else:
        yield from _desempenho(sessao, uf, transp)


def _aprovar(sessao, uf) -> Iterator[dict]:
    """Pedem para o agente aprovar algo: não é dele. Mostra a recusa e leva ao gerente."""
    yield from _rodar(sessao, "aprovar_proposta", {"proposta_id": "pendente", "decisao": "aprovar"})
    yield _fim(sessao, "Essa eu não posso fazer: aprovar mudança de prazo é da Marina Duarte, gerente de logística. "
                       "O sistema nem me deixa.\n\nO que eu faço é montar a proposta com a evidência e mandar para ela. "
                       "Quer que eu faça isso para alguma região?")


def _desempenho(sessao, uf, transp) -> Iterator[dict]:
    args = {}
    if uf:
        args["uf"] = uf
    if transp:
        args["transportadora"] = transp
    yield from _rodar(sessao, "medir_desempenho", args)
    linhas = sessao._ultimo.get("linhas", [])
    if not linhas:
        yield _fim(sessao, "Sem envios medidos nesse filtro.")
        return
    corpo = "\n".join(
        f"{'🔴' if l.get('abaixo_da_meta') else '🟢'} {l.get('transportadora')}: {_pct(l.get('cumprimento'))} no prazo, "
        f"9 em cada 10 em até {l.get('prazo_real_p92'):.0f} dias ({int(l.get('envios', 0))} envios)"
        for l in linhas[:5])
    alvo = f" em {uf}" if uf else ""
    yield _fim(sessao, f"Cumprimento de prazo{alvo}, de 03/09 a 02/11:\n\n{corpo}\n\nA meta é 92%. Quer que eu veja o que fazer com quem está abaixo?")


def _nao_entendi(sessao) -> Iterator[dict]:
    """Não casou com nada: em vez de chutar um assunto, diz o que não pegou e o que dá para pedir."""
    if sessao.papel == F.PAPEL_CONSULTA:
        sug = "“O que está esperando minha decisão?”, “Por que Marabá?” ou “Onde resolvemos mais problemas?”"
    else:
        sug = "“Qual a melhor rota para os envios novos de SP?”, “Qual prazo do site precisa mudar?” ou “A Marina já respondeu?”"
    yield _fim(sessao, f"Não peguei bem o que você quis. Pode repetir? Por exemplo: {sug}")


def responder_sem_ia(sessao, pergunta: str) -> Iterator[dict]:
    yield _evento("aviso", texto="Modo sem IA: roteiro local decidindo os passos, com as mesmas ferramentas.")
    s = _sem_acento(pergunta)
    if SAUDACAO.fullmatch(s.strip()):
        yield from _ola(sessao)
        return
    if _quer_piloto(s):   # vale para o analista e para a gerente: é só leitura
        yield from _piloto(sessao)
        return
    uf, prefixo = _lugar_na_pergunta(pergunta)
    cep_uf, cep_prefixo, aproximado = _cep_na_pergunta(pergunta)
    if cep_prefixo and not prefixo:
        uf, prefixo = cep_uf, cep_prefixo
        if aproximado:
            sessao._nota = (f"_Não meço o prefixo exato desse CEP; usei o mais próximo que tenho, {prefixo} "
                            f"({_cidade_do_prefixo(prefixo)})._")
    uf = uf or _uf_na_pergunta(pergunta)
    regiao = _regiao_na_pergunta(pergunta)
    regiao = regiao if regiao[0] and not prefixo else None
    local = _cidade_do_prefixo(prefixo) or uf
    transp = _transportadora_na_pergunta(pergunta)
    sessao._prefixo_pedido = prefixo
    # "mude o prazo de Marabá para 18", "as 3 maiores do Pará", "peça à Marina...": é pedido de proposta, não de aprovação
    pedido_de_prazo = bool(_lugares_na_pergunta(pergunta) or _quantos(s)) and any(
        k in s for k in ["prazo", "muda", "mude", "altera", "ajusta", "peca", "pedir", "solicita", "proponha", "propor", "proposta"])
    if sessao.papel == F.PAPEL_CONSULTA:
        yield from _consulta(sessao, pergunta, s, uf, prefixo, transp, regiao, local)
        return
    if any(k in s for k in ["ja respondeu", "marina respondeu", "resposta da marina", "aprovacoes", "aprovou", "recusou", "decidiu",
                            "respondeu", "pendente", "aguardando", "esperando", "quantos pedidos", "meus pedidos", "fila"]):
        yield from _status_aprovacoes(sessao)
    elif any(k in s for k in ["aprova", "autoriza"]) or (any(k in s for k in ["pode mudar", "muda o prazo", "mude o prazo"]) and not pedido_de_prazo):
        yield from _aprovar(sessao, uf)
    elif pedido_de_prazo:
        yield from _prazo(sessao, uf, pergunta)
    elif regiao and not prefixo and _quer_ranking(s):
        yield from _ranking_regiao(sessao, regiao[0], regiao[1])
    elif regiao and not prefixo and _quer_problemas(s):
        yield from _problemas_regiao(sessao, regiao[0], regiao[1])
    elif _quer_custo(s) and not prefixo:
        yield from _impacto(sessao)
    elif any(k in s for k in ["problema", "reclama", "chamado", "extravio", "avaria", "resolvemos", "dor", "pior"]):
        yield from _problemas(sessao, uf, local)
    elif any(k in s for k in ["rota", "rotear", "transportadora para", "qual transportadora", "envio", "env0", "melhor caminho", "despach"]):
        yield from _rota(sessao, uf, pergunta)
    elif regiao and not prefixo:
        yield from _regiao(sessao, regiao[0], regiao[1], concorrentes=_quer_concorrente(s))
    elif prefixo and not re.search(r"propo|mude|mudar|muda |ajust|suba|subir|baix|reduz|aument|mand|envie|pedir|pede", s):
        yield from _explicar(sessao, uf, prefixo, pergunta, gerente=False)   # só perguntou: explica, não abre pedido
    elif prefixo or any(k in s for k in ["prazo", "sla", "proposta", "site", "concorrente"]):
        yield from _prazo(sessao, uf, pergunta)
    elif uf or transp or any(k in s for k in ["desempenho", "cumprimento", "como esta", "no prazo", "ranking", "entrega", "situacao", "resumo", "panorama", "geral", "como vai", "como estamos"]):
        yield from _desempenho(sessao, uf, transp)
    else:
        yield from _nao_entendi(sessao)
