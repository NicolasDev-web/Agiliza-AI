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


def _rodar(sessao, nome: str, args: dict) -> Iterator[dict]:
    yield _evento("ferramenta", nome=nome, argumentos=args,
                  tipo_ferramenta=F.POR_NOME[nome].tipo, rotulo=rotulo_da_ferramenta(nome, args))
    time.sleep(PAUSA)
    res = F.executar(nome, args, sessao.papel, sessao.diario)
    yield _evento("resultado", nome=nome, resultado=res, recusado=bool(res.get("recusado")), custo=sessao.diario.custo)
    time.sleep(0.04)
    sessao._ultimo = res


def _fim(sessao, texto: str) -> dict:
    return _evento("resposta", texto=texto, diario=sessao.diario.acoes, custo=sessao.diario.custo)


def _pct(x) -> str:
    return "–" if x is None else f"{round(x * 100)}%"


def _brl(x) -> str:
    return "–" if x is None else f"R$ {x:,.0f}".replace(",", ".")


# --------------------------------------------------------------------------- roteiros
def _problemas(sessao, uf) -> Iterator[dict]:
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
        f"Olhei os chamados e as ocorrências de 03/09 a 02/11.\n\n"
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


def _prazo(sessao, uf, pergunta) -> Iterator[dict]:
    prefixo = getattr(sessao, "_prefixo_pedido", None)
    filtro = {"uf": uf} if uf else {}
    if prefixo:
        yield from _rodar(sessao, "ver_propostas_de_prazo", {"top": 200, **filtro})
        props = [l for l in sessao._ultimo.get("linhas", []) if l["cep3"] == prefixo]
    else:
        yield from _rodar(sessao, "ver_propostas_de_prazo", {"acao": "aumentar", "top": 5, **filtro})
        props = sessao._ultimo.get("linhas", [])
        if not props:
            yield from _rodar(sessao, "ver_propostas_de_prazo", {"top": 5, **filtro})
            props = sessao._ultimo.get("linhas", [])
    if not props:
        yield _fim(sessao, "Não achei região com proposta de prazo nesse filtro.")
        return
    p = props[0]
    yield from _rodar(sessao, "medir_desempenho", {"prefixo_cep": p["cep3"]})
    yield from _rodar(sessao, "consultar_concorrentes", {"prefixo_cep": p["cep3"]})
    conc = (sessao._ultimo.get("linhas") or [{}])[0]
    cabeca = f"*{p['cidade_referencia']}/{p['uf']}, prefixo {p['cep3']}*"
    if p["acao"] not in ("aumentar", "reduzir"):
        yield _fim(sessao, f"{cabeca}: a {p['transportadora']} entrega {_pct(p['cumprimento_hoje'])} no prazo e "
                           f"o site mostra {int(p['prazo_site_hoje'])} dias úteis. Está no lugar certo, não mexeria.")
        return
    evidencia = (f"Prefixo {p['cep3']} ({p['cidade_referencia']}/{p['uf']}), {p['transportadora']}, "
                 f"03/09 a 02/11: {int(p['envios_medidos'])} envios medidos, {_pct(p['cumprimento_hoje'])} no prazo "
                 f"(meta 92%). Prazo do site {int(p['prazo_site_hoje'])} dias; 9 em cada 10 entregas levam até "
                 f"{int(p['prazo_proposto'])}. Impacto estimado: {_brl(p['impacto_custo_atraso_rs'])}.")
    yield from _rodar(sessao, "propor_mudanca", {"tipo": "prazo_exibido", "prefixos_cep": [p["cep3"]],
                                                 "valor_novo": p["prazo_proposto"], "evidencia": evidencia,
                                                 "impacto_estimado_reais": p["impacto_custo_atraso_rs"]})
    proposta = sessao._ultimo
    verbo = "Subir" if p["acao"] == "aumentar" else "Baixar"
    resumo = (f"{verbo} o prazo do site de {int(p['prazo_site_hoje'])} para {int(p['prazo_proposto'])} dias úteis no "
              f"prefixo {p['cep3']} ({p['cidade_referencia']}/{p['uf']}).")
    yield from _rodar(sessao, "solicitar_aprovacao", {"resumo": resumo, "evidencia": evidencia,
                                                      "proposta_id": proposta.get("proposta_id")})
    texto = (f"{cabeca}\n\n"
             f"A {p['transportadora']} entrega {_pct(p['cumprimento_hoje'])} no prazo ali"
             + (", bem abaixo da meta de 92%" if (p["cumprimento_hoje"] or 1) < 0.92 else "") + ". "
             f"O site promete {int(p['prazo_site_hoje'])} dias e 9 em cada 10 entregas levam até "
             f"{int(p['prazo_proposto'])} dias úteis.\n"
             + (f"Os concorrentes mostram cerca de {int(conc['prazo_conc_mediana'])} dias nessa região.\n" if conc.get("prazo_conc_mediana") else "")
             + f"\n{verbo} para {int(p['prazo_proposto'])} dias "
             + ("evita cerca de " + _brl(p["impacto_custo_atraso_rs"]) + " de custo com atraso" if p["acao"] == "aumentar"
                else "deixa a gente mais competitivo sem furar a meta")
             + ".\n\nMandei para a Marina: mudar o prazo do site não é decisão minha.")
    yield _fim(sessao, texto)


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
    yield _fim(sessao, "Como estão os pedidos para a Marina:\n\n" + "\n".join(linhas) +
               f"\n\nO cenário permite {r.get('limite')} aprovações; já foram {r.get('aprovadas_no_cenario')}.")


def _explicar(sessao, uf, prefixo, pergunta) -> Iterator[dict]:
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
    texto += "\n\nA decisão é sua: eu só explico."
    yield _fim(sessao, texto)


def _consulta(sessao, pergunta, s, uf, prefixo, transp) -> Iterator[dict]:
    if any(k in s for k in ["pedido", "pendente", "esperando", "aprovacao", "aprovacoes"]):
        yield from _status_aprovacoes(sessao)
    elif any(k in s for k in ["problema", "reclama", "chamado", "extravio", "pior"]):
        yield from _problemas(sessao, uf)
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
    uf, prefixo = _lugar_na_pergunta(pergunta)
    uf = uf or _uf_na_pergunta(pergunta)
    transp = _transportadora_na_pergunta(pergunta)
    sessao._prefixo_pedido = prefixo
    if sessao.papel == F.PAPEL_CONSULTA:
        yield from _consulta(sessao, pergunta, s, uf, prefixo, transp)
        return
    if any(k in s for k in ["ja respondeu", "marina respondeu", "resposta da marina", "aprovacoes", "aprovou", "recusou", "decidiu"]):
        yield from _status_aprovacoes(sessao)
    elif any(k in s for k in ["aprova", "autoriza", "pode mudar", "muda o prazo", "mude o prazo"]):
        yield from _aprovar(sessao, uf)
    elif any(k in s for k in ["problema", "reclama", "chamado", "extravio", "avaria", "resolvemos", "dor", "pior"]):
        yield from _problemas(sessao, uf)
    elif any(k in s for k in ["rota", "rotear", "transportadora para", "qual transportadora", "envio", "env0", "melhor caminho", "despach"]):
        yield from _rota(sessao, uf, pergunta)
    elif any(k in s for k in ["prazo", "sla", "proposta", "site", "concorrente"]):
        yield from _prazo(sessao, uf, pergunta)
    elif uf or transp or any(k in s for k in ["desempenho", "cumprimento", "como esta", "no prazo", "ranking", "entrega", "situacao", "resumo", "panorama", "geral", "como vai", "como estamos"]):
        yield from _desempenho(sessao, uf, transp)
    else:
        yield from _nao_entendi(sessao)
