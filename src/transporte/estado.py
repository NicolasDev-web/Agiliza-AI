"""Estado compartilhado da demonstração: quem está usando, o que espera aprovação e o que foi decidido.

Fica num SQLite próprio e gravável (data/processed/estado.db), separado da base de dados do desafio,
que continua só de leitura. Hackathon: não há senha. Mesmo assim o papel do usuário é lido daqui, no
servidor, e as regras de aprovação (só o gerente aprova, nunca a própria proposta, no máximo 12 por
cenário) valem no código, não só na tela.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from .config import PROCESSED

MAX_APROVACOES = 12          # politicas.csv: no máximo 12 aprovações por cenário
CUSTO_APROVACAO = 15.0       # R$ por pedido de aprovação

USUARIOS = [
    ("lucas", "Lucas Ferreira", "analista_logistica", "Analista de logística"),
    ("marina", "Marina Duarte", "gerente", "Gerente de logística"),
]

_TRAVA = threading.RLock()
_CON: sqlite3.Connection | None = None
_CAMINHO: Path | None = None


class ErroDeRegra(Exception):
    """Uma regra da política barrou a ação. A mensagem é para o usuário ler."""


def caminho() -> Path:
    return Path(os.environ.get("TRANSPORTE_ESTADO") or (PROCESSED / "estado.db"))


def brl(x: float) -> str:
    """R$ 1.234,56 (formato do Brasil)."""
    return "R$ " + f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def con() -> sqlite3.Connection:
    global _CON, _CAMINHO
    alvo = caminho()
    with _TRAVA:
        if _CON is None or _CAMINHO != alvo:
            if _CON is not None:
                _CON.close()
            alvo.parent.mkdir(parents=True, exist_ok=True)
            _CON = sqlite3.connect(alvo, check_same_thread=False)
            _CON.row_factory = sqlite3.Row
            _CAMINHO = alvo
            _criar(_CON)
        return _CON


def _criar(c: sqlite3.Connection) -> None:
    c.executescript("""
    create table if not exists usuarios (id text primary key, nome text, papel text, cargo text);
    create table if not exists aprovacoes (
      id integer primary key autoincrement, criado_em text, tipo text, proposta_id text,
      resumo text, evidencia text, prefixos text, valor_atual real, valor_proposto real,
      impacto_reais real, solicitante text, sessao text, custo real,
      situacao text default 'pendente', decidido_por text, decidido_em text, valor_final real, comentario text);
    create table if not exists prazos_vigentes (
      cep3 text primary key, prazo real, prazo_anterior real, aprovacao_id integer, por text, quando text);
    create table if not exists alertas (
      id integer primary key autoincrement, quando text, categoria text, titulo text, texto text,
      detalhe text, origem text, ciente integer default 0);
    create index if not exists ix_aprov_situacao on aprovacoes(situacao);
    """)
    for u in USUARIOS:
        c.execute("insert or ignore into usuarios values (?,?,?,?)", u)
    c.commit()


def _linhas(consulta: str, args: tuple = ()) -> list[dict]:
    with _TRAVA:
        return [dict(r) for r in con().execute(consulta, args).fetchall()]


def reiniciar() -> None:
    """Zera pedidos, decisões, prazos aprovados e alertas. Os usuários ficam."""
    with _TRAVA:
        c = con()
        c.executescript("delete from aprovacoes; delete from prazos_vigentes; delete from alertas;"
                        "delete from sqlite_sequence;")
        c.commit()


# ---------------------------------------------------------------------------- usuários
def usuarios() -> list[dict]:
    return _linhas("select * from usuarios order by papel desc")


def usuario(uid: str | None) -> dict | None:
    if not uid:
        return None
    r = _linhas("select * from usuarios where id = ?", (uid,))
    return r[0] if r else None


# ---------------------------------------------------------------------------- barramento (tempo real)
class Barramento:
    """Eventos em memória, por usuário ("lucas") ou por papel ("papel:gerente"). Quem assina recebe só o que chega depois."""

    def __init__(self) -> None:
        self._c = threading.Condition()
        self._eventos: deque = deque(maxlen=500)
        self._n = 0

    def publicar(self, para: str, tipo: str, **dados) -> None:
        with self._c:
            self._n += 1
            self._eventos.append((self._n, para, {"tipo": tipo, "t": round(time.time(), 3), **dados}))
            self._c.notify_all()

    def ultimo(self) -> int:
        with self._c:
            return self._n

    def esperar(self, chaves: set[str], depois_de: int, espera: float = 15.0):
        """Devolve (novo_cursor, [eventos]). Lista vazia quando a espera acaba sem nada novo."""
        fim = time.time() + espera
        with self._c:
            while True:
                novos = [(i, e) for i, p, e in self._eventos if i > depois_de and (p == "todos" or p in chaves)]
                if novos:
                    return novos[-1][0], [e for _, e in novos]
                resto = fim - time.time()
                if resto <= 0:
                    return max(depois_de, self._n), []
                self._c.wait(resto)


BARRAMENTO = Barramento()


# ---------------------------------------------------------------------------- aprovações
def _normaliza(a: dict) -> dict:
    a["prefixos"] = json.loads(a["prefixos"]) if a.get("prefixos") else []
    return a


def contar_aprovadas() -> int:
    return _linhas("select count(*) n from aprovacoes where situacao in ('aprovada','ajustada')")[0]["n"]


def criar_aprovacao(*, resumo: str, solicitante: str, tipo: str = "outro", proposta_id: str | None = None,
                    evidencia: str | None = None, prefixos: list[str] | None = None, valor_atual=None,
                    valor_proposto=None, impacto_reais=None, sessao: str | None = None) -> dict:
    """Entra na fila do gerente. Pedido igual a um que já espera não duplica."""
    with _TRAVA:
        c = con()
        if contar_aprovadas() >= MAX_APROVACOES:
            raise ErroDeRegra(f"o limite de {MAX_APROVACOES} aprovações por cenário já foi usado")
        chave = json.dumps(sorted(prefixos or []))
        for p in _linhas("select * from aprovacoes where situacao = 'pendente'"):
            igual_id = proposta_id and p["proposta_id"] == proposta_id
            igual_alvo = tipo != "outro" and p["tipo"] == tipo and json.dumps(sorted(json.loads(p["prefixos"] or "[]"))) == chave
            if igual_id or igual_alvo:
                return _normaliza(p) | {"ja_existia": True}
        cur = c.execute(
            "insert into aprovacoes (criado_em,tipo,proposta_id,resumo,evidencia,prefixos,valor_atual,valor_proposto,"
            "impacto_reais,solicitante,sessao,custo) values (?,?,?,?,?,?,?,?,?,?,?,?)",
            (_agora(), tipo, proposta_id, resumo, evidencia, json.dumps(prefixos or []), valor_atual, valor_proposto,
             impacto_reais, solicitante, sessao, CUSTO_APROVACAO))
        c.commit()
        a = _normaliza(_linhas("select * from aprovacoes where id = ?", (cur.lastrowid,))[0]) | {"ja_existia": False}
    BARRAMENTO.publicar("papel:gerente", "pedido_novo", aprovacao=a)
    BARRAMENTO.publicar(solicitante, "pedido_enviado", aprovacao=a)
    return a


def aprovacao(aid: int) -> dict | None:
    r = _linhas("select * from aprovacoes where id = ?", (aid,))
    return _normaliza(r[0]) if r else None


def listar_aprovacoes(uid: str | None = None, situacao: str | None = None) -> list[dict]:
    """O gerente vê tudo; quem pediu vê só os seus."""
    onde, args = [], []
    if uid:
        onde.append("solicitante = ?"); args.append(uid)
    if situacao == "pendente":
        onde.append("situacao = 'pendente'")
    elif situacao == "decidida":
        onde.append("situacao != 'pendente'")
    filtro = (" where " + " and ".join(onde)) if onde else ""
    return [_normaliza(a) for a in _linhas(f"select * from aprovacoes{filtro} order by id desc", tuple(args))]


def decidir(aid: int, decisor: str, decisao: str, valor=None, comentario: str = "") -> dict:
    """Aprova, ajusta (muda o valor e aprova) ou recusa. Só o gerente, e nunca a própria proposta."""
    d = usuario(decisor)
    if not d or d["papel"] != "gerente":
        raise ErroDeRegra("aprovar ou recusar é do gerente de logística; esse usuário não tem esse papel")
    if decisao not in ("aprovar", "ajustar", "recusar"):
        raise ErroDeRegra("a decisão deve ser aprovar, ajustar ou recusar")
    with _TRAVA:
        a = aprovacao(aid)
        if not a:
            raise ErroDeRegra("esse pedido não existe")
        if a["situacao"] != "pendente":
            raise ErroDeRegra(f"esse pedido já foi {a['situacao']}")
        if a["solicitante"] == decisor:
            raise ErroDeRegra("o gerente não aprova uma proposta feita por ele mesmo")
        final = a["valor_proposto"]
        if decisao in ("aprovar", "ajustar") and contar_aprovadas() >= MAX_APROVACOES:
            raise ErroDeRegra(f"o limite de {MAX_APROVACOES} aprovações por cenário já foi usado")
        if decisao == "ajustar":
            if a["valor_proposto"] is None:
                raise ErroDeRegra("este pedido não tem um valor para ajustar; aprove ou recuse")
            try:
                final = float(valor)
            except (TypeError, ValueError):
                raise ErroDeRegra("informe o novo valor em número")
            if a["tipo"] == "prazo_exibido" and (final < 2 or final != int(final)):
                raise ErroDeRegra("o prazo exibido tem que ser um número inteiro de dias úteis, no mínimo 2")
        situacao = {"aprovar": "aprovada", "ajustar": "ajustada", "recusar": "recusada"}[decisao]
        c = con()
        c.execute("update aprovacoes set situacao=?, decidido_por=?, decidido_em=?, valor_final=?, comentario=? where id=?",
                  (situacao, decisor, _agora(), None if decisao == "recusar" else final, (comentario or "").strip()[:500], aid))
        if decisao != "recusar" and a["tipo"] == "prazo_exibido" and final is not None:
            for cep in a["prefixos"]:
                c.execute("insert or replace into prazos_vigentes values (?,?,?,?,?,?)",
                          (cep, final, a["valor_atual"], aid, d["nome"], _agora()))
        c.commit()
        novo = aprovacao(aid)
    BARRAMENTO.publicar(a["solicitante"], "decisao", aprovacao=novo, por=d["nome"])
    BARRAMENTO.publicar("papel:gerente", "decisao_registrada", aprovacao=novo)
    BARRAMENTO.publicar("todos", "prazos_mudaram")
    return novo


def prazos_vigentes() -> dict[str, dict]:
    return {r["cep3"]: r for r in _linhas("select * from prazos_vigentes")}


# ---------------------------------------------------------------------------- alertas para o gerente (financeiro)
def alerta(categoria: str, titulo: str, texto: str, detalhe: dict | None = None, origem: str = "agente") -> dict:
    with _TRAVA:
        c = con()
        cur = c.execute("insert into alertas (quando,categoria,titulo,texto,detalhe,origem) values (?,?,?,?,?,?)",
                        (_agora(), categoria, titulo, texto, json.dumps(detalhe or {}, ensure_ascii=False, default=str), origem))
        c.commit()
        a = _alerta(_linhas("select * from alertas where id = ?", (cur.lastrowid,))[0])
    BARRAMENTO.publicar("papel:gerente", "alerta", alerta=a)
    return a


def _alerta(r: dict) -> dict:
    r["detalhe"] = json.loads(r["detalhe"] or "{}")
    return r


def registrar_trocas_de_rota(trocas: list[dict], origem: str = "agente") -> dict | None:
    """Toda vez que o agente muda rotas, a parte financeira é do gerente: quanto o frete sobe ou desce,
    quanto de custo de atraso deixa de existir e o saldo."""
    if not trocas:
        return None
    frete = sum(t["frete_para"] - t["frete_de"] for t in trocas)
    atraso = sum(t["atraso_de"] - t["atraso_para"] for t in trocas)
    saldo = sum(t["economia_estimada"] or 0 for t in trocas)
    destinos = sorted({t["destino"].split("/")[-1] for t in trocas})
    mais_caros = sum(1 for t in trocas if t["frete_para"] > t["frete_de"])
    texto = (f"Troquei a transportadora de {len(trocas)} envios novos ({', '.join(destinos)}). "
             f"O frete {'sobe' if frete > 0 else 'cai'} {brl(abs(frete))}; o custo esperado de atraso cai {brl(atraso)}. "
             f"Saldo estimado: {brl(saldo)} a favor.")
    if mais_caros:
        texto += f" Em {mais_caros} deles o frete ficou mais caro, compensado pelo atraso evitado."
    return alerta("troca_de_rota", f"{len(trocas)} rotas trocadas · saldo {brl(saldo)}", texto,
                  {"trocas": trocas, "variacao_frete": round(frete, 2), "atraso_evitado": round(atraso, 2),
                   "saldo": round(saldo, 2)}, origem)


def listar_alertas(limite: int = 50) -> list[dict]:
    return [_alerta(r) for r in _linhas("select * from alertas order by id desc limit ?", (int(limite),))]


def marcar_ciente(aid: int) -> None:
    with _TRAVA:
        con().execute("update alertas set ciente = 1 where id = ?", (aid,))
        con().commit()


# ---------------------------------------------------------------------------- placar do gerente
def placar() -> dict:
    ap = _linhas("select situacao, impacto_reais, custo from aprovacoes")
    aprovadas = [a for a in ap if a["situacao"] in ("aprovada", "ajustada")]
    rotas = [a for a in listar_alertas(500) if a["categoria"] == "troca_de_rota"]
    return {
        "pendentes": sum(1 for a in ap if a["situacao"] == "pendente"),
        "aprovadas": len(aprovadas),
        "recusadas": sum(1 for a in ap if a["situacao"] == "recusada"),
        "restantes": MAX_APROVACOES - len(aprovadas),
        "limite": MAX_APROVACOES,
        "custo_pedidos": round(sum(a["custo"] or 0 for a in ap), 2),
        "economia_prazos": round(sum(a["impacto_reais"] or 0 for a in aprovadas), 2),
        "economia_rotas": round(sum(r["detalhe"].get("saldo", 0) for r in rotas), 2),
        "rotas_trocadas": sum(len(r["detalhe"].get("trocas", [])) for r in rotas),
        "alertas_sem_ciencia": sum(1 for a in listar_alertas(500) if not a["ciente"]),
    }
