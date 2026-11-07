"""Entender o que a pessoa falou: conserta o que o reconhecimento de voz erra e prepara a fala da resposta.

O reconhecimento de voz do navegador erra justamente os nomes do nosso domínio ("trans norte", "maraba",
"rapido sul"). Aqui cada trecho da frase é comparado com o vocabulário do projeto (cidades do painel,
transportadoras, estados) e, se for quase igual, vira o nome certo. Texto digitado passa pelo mesmo caminho,
sem prejuízo: só muda o que está muito perto de um nome conhecido.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from functools import lru_cache

TRANSPORTADORAS = ["Correio Ágil", "Expressa Já", "TransNorte", "Rápido Sul", "ViaLog"]
ESTADOS = ["Acre", "Alagoas", "Amapá", "Amazonas", "Bahia", "Ceará", "Distrito Federal", "Espírito Santo", "Goiás",
           "Maranhão", "Mato Grosso", "Mato Grosso do Sul", "Minas Gerais", "Pará", "Paraíba", "Paraná", "Pernambuco",
           "Piauí", "Rio de Janeiro", "Rio Grande do Norte", "Rio Grande do Sul", "Rondônia", "Roraima", "Santa Catarina",
           "São Paulo", "Sergipe", "Tocantins"]
# como a voz costuma escrever o que foi dito
APELIDOS = {"trans norte": "TransNorte", "transnorte": "TransNorte", "trans nortes": "TransNorte", "via log": "ViaLog",
            "vialogue": "ViaLog", "via logue": "ViaLog", "correio agil": "Correio Ágil", "correios agil": "Correio Ágil",
            "expressa ja": "Expressa Já", "express já": "Expressa Já", "rapido sul": "Rápido Sul", "rápido sul": "Rápido Sul",
            "gerente marina": "Marina", "dias uteis": "dias úteis", "dia util": "dia útil"}
NUMEROS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8,
           "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "quatorze": 14, "quinze": 15, "dezesseis": 16,
           "dezessete": 17, "dezoito": 18, "dezenove": 19, "vinte": 20}
PALAVRAS_DO_DOMINIO = ["prazo", "rota", "rotas", "envios", "envio", "transportadora", "aprovação", "aprovou", "recusou",
                       "pedido", "pedidos", "problemas", "chamados", "extravios", "desempenho", "cumprimento", "proposta"]


def sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c))


@lru_cache(maxsize=1)
def vocabulario() -> dict[str, str]:
    """{forma sem acento: nome certo} para cidades, transportadoras e estados."""
    v: dict[str, str] = {}
    try:
        from .contexto import tabela
        for c in tabela("regras")["cidade_referencia"].dropna().unique():
            v[sem_acento(str(c))] = str(c)
    except Exception:
        pass
    for nome in TRANSPORTADORAS + ESTADOS:
        v[sem_acento(nome)] = nome
    return v


def _palavras(texto: str) -> list[str]:
    return re.findall(r"[\wÀ-ÿ'-]+|[^\w\s]", texto, flags=re.UNICODE)


def corrigir(texto: str) -> str:
    """Troca trechos quase iguais a um nome conhecido pelo nome certo e escreve os números por extenso."""
    t = " ".join((texto or "").split())
    if not t:
        return t
    for errado, certo in APELIDOS.items():
        t = re.sub(rf"\b{re.escape(errado)}\b", certo, t, flags=re.IGNORECASE) if sem_acento(errado) == errado else t
    palavras = t.split(" ")
    vocab = vocabulario()
    chaves = list(vocab)
    saida, i = [], 0
    while i < len(palavras):
        trocado = False
        for n in (3, 2, 1):   # tenta o trecho mais longo primeiro
            trecho = palavras[i:i + n]
            if len(trecho) < n or (n > 1 and (len(trecho[0]) < 3 or len(trecho[-1]) < 3)):
                continue
            bruto = re.sub(r"[^\w ]", "", " ".join(trecho))
            chave = sem_acento(bruto)
            if len(chave) < 5 or chave in NUMEROS:
                continue
            if chave in vocab:
                alvo = vocab[chave]
            else:
                perto = [c for c in difflib.get_close_matches(chave, chaves, n=3, cutoff=0.86) if abs(len(c) - len(chave)) <= 2]
                alvo = vocab[perto[0]] if perto else None
            if alvo:
                cauda = re.search(r"[^\w]+$", " ".join(trecho))
                saida.append(alvo + (cauda.group(0) if cauda else ""))
                i += n
                trocado = True
                break
        if not trocado:
            saida.append(palavras[i])
            i += 1
    t = " ".join(saida)
    # "seis dias" -> "6 dias"
    t = re.sub(r"\b(\w+)\s+(dias?|d[ií]as? [uú]teis)\b", lambda m: f"{NUMEROS[sem_acento(m.group(1))]} {m.group(2)}" if sem_acento(m.group(1)) in NUMEROS else m.group(0), t, flags=re.IGNORECASE)
    return t


def pontuar(texto: str) -> int:
    """Quantos nomes do nosso domínio aparecem: serve para escolher a melhor alternativa do reconhecedor."""
    s = " " + sem_acento(texto) + " "
    return sum(1 for k in vocabulario() if f" {k} " in s) * 2 + sum(1 for p in PALAVRAS_DO_DOMINIO if f" {sem_acento(p)} " in s)


def escolher(alternativas: list[str]) -> str:
    """Das alternativas que o reconhecedor deu, fica com a que mais parece conversa de logística (empate: a primeira)."""
    alts = [a.strip() for a in alternativas if a and a.strip()]
    if not alts:
        return ""
    corrigidas = [corrigir(a) for a in alts]
    melhor = max(range(len(corrigidas)), key=lambda i: (pontuar(corrigidas[i]), -i))
    return corrigidas[melhor]


# ---------------------------------------------------------------------------- a fala da resposta
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿️▫•]+")


def para_fala(texto: str, maximo: int = 340) -> str:
    """Versão para ouvir: sem marcação, sem lista, no máximo umas três frases."""
    t = _EMOJI.sub("", texto or "")
    t = re.sub(r"\*([^*\n]+)\*", r"\1", t)
    t = re.sub(r"^\s*[-–•]\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"R\$\s*([\d.]+)", lambda m: m.group(1).replace(".", "") + " reais", t)
    t = re.sub(r"\s*\n+\s*", ". ", t)
    t = re.sub(r"\.(\s*\.)+", ".", t)
    t = re.sub(r"\s+", " ", t).strip()
    frases = re.split(r"(?<=[.!?])\s+", t)
    fala = ""
    for f in frases[:3]:
        if len(fala) + len(f) > maximo and fala:
            break
        fala += (" " if fala else "") + f
    return fala[:maximo].strip()
