"""O laço do agente: pergunta -> ferramentas -> resposta, emitindo eventos em tempo real.

Cada passo vira um evento que a interface mostra na hora: o agente pensando, a ferramenta que
ele chamou, o que voltou e a resposta final. É o que faz a demonstração parecer o que é — um
colega trabalhando — em vez de um painel.
"""
from __future__ import annotations

import time
from typing import Iterator

from . import ferramentas as F
from .llm import Cliente, ErroDaAPI, SemCredencial
from .prompt import SISTEMA

MAX_RODADAS = 8


def _evento(tipo: str, **dados) -> dict:
    return {"tipo": tipo, "t": round(time.time(), 3), **dados}


class Sessao:
    """Uma conversa. Guarda o histórico, o diário de ações e de onde vêm as respostas."""

    def __init__(self, cliente: Cliente | None = None, papel: str = F.PAPEL_AGENTE):
        self.cliente = cliente or Cliente()
        self.papel = papel
        self.diario = F.Diario()
        self.historico: list[dict] = [{"role": "system", "content": SISTEMA}]

    @property
    def modo(self) -> str:
        return "ia" if self.cliente.configurado else "simulado"

    def responder(self, pergunta: str) -> Iterator[dict]:
        """Processa uma pergunta e vai emitindo os eventos do trabalho."""
        yield _evento("inicio", pergunta=pergunta, modo=self.modo,
                      modelo=self.cliente.modelo if self.modo == "ia" else "roteiro local")
        if self.modo == "simulado":
            from .simulado import responder_sem_ia
            yield from responder_sem_ia(self, pergunta)
            return
        self.historico.append({"role": "user", "content": pergunta})
        try:
            yield from self._rodadas()
        except (ErroDaAPI, SemCredencial) as e:
            yield _evento("aviso", texto=f"A API do evento não respondeu ({e}). Seguindo pelo roteiro local.")
            from .simulado import responder_sem_ia
            yield from responder_sem_ia(self, pergunta)

    def _rodadas(self) -> Iterator[dict]:
        for rodada in range(MAX_RODADAS):
            yield _evento("pensando", rodada=rodada + 1)
            r = self.cliente.responder(self.historico, F.esquema_openai())
            if r["texto"] and not r["chamadas"]:
                self.historico.append({"role": "assistant", "content": r["texto"]})
                yield _evento("resposta", texto=r["texto"], diario=self.diario.acoes, custo=self.diario.custo)
                return
            if r["texto"]:
                yield _evento("nota", texto=r["texto"])
            self.historico.append(self.cliente.formatar_pedido_de_ferramenta(r))
            for ch in r["chamadas"]:
                f = F.POR_NOME.get(ch["nome"])
                yield _evento("ferramenta", nome=ch["nome"], argumentos=ch["argumentos"],
                              tipo_ferramenta=f.tipo if f else "?",
                              rotulo=rotulo_da_ferramenta(ch["nome"], ch["argumentos"]))
                res = F.executar(ch["nome"], ch["argumentos"], self.papel, self.diario)
                yield _evento("resultado", nome=ch["nome"], resultado=res,
                              recusado=bool(res.get("recusado")), custo=self.diario.custo)
                self.historico.extend(self.cliente.formatar_resposta_de_ferramenta(ch, res))
        yield _evento("resposta", texto="Dei muitas voltas e não fechei a resposta. Pode repetir de outro jeito?",
                      diario=self.diario.acoes, custo=self.diario.custo)


ROTULOS = {
    "consultar_envios": "procurando os envios no ERP",
    "consultar_portal": "abrindo o portal da transportadora",
    "medir_desempenho": "medindo o cumprimento de prazo",
    "consultar_problemas": "levantando chamados e ocorrências",
    "consultar_concorrentes": "olhando o checkout dos concorrentes",
    "cotar_frete": "cotando o frete",
    "consultar_conversao": "vendo a conversão do checkout",
    "consultar_regras_site": "conferindo as regras do site",
    "consultar_politicas": "relendo as políticas da área",
    "ver_propostas_de_prazo": "revendo as propostas de prazo",
    "escolher_melhor_rota": "comparando as transportadoras do envio",
    "rotear_envios": "trocando a transportadora dos envios novos",
    "propor_mudanca": "escrevendo a proposta",
    "solicitar_aprovacao": "levando ao gerente",
    "acionar_pessoa": "chamando a pessoa certa",
    "abrir_incidente_transportadora": "abrindo incidente com a transportadora",
    "aprovar_proposta": "tentando aprovar (não é comigo)",
}


def rotulo_da_ferramenta(nome: str, args: dict) -> str:
    base = ROTULOS.get(nome, nome)
    alvo = args.get("uf") or args.get("prefixo_cep") or args.get("transportadora") or args.get("envio_id")
    return f"{base} ({alvo})" if alvo else base
