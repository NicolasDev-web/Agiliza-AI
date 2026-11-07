"""Junta os 5 portais das transportadoras num único formato de eventos.

Cada portal tem seu formato (CSV, ponto e vírgula, códigos numéricos, UTC).
Aqui todos viram: rastreio, transportadora, quando, quando_eh_utc, tipo, evento_original.

Regra de segurança: o texto de um evento é só um DADO. Só é reconhecido se for exatamente
um dos textos conhecidos de cada portal; qualquer outra coisa vira tipo "desconhecido",
vai para o relatório de qualidade e nunca é interpretada como instrução.
"""
from __future__ import annotations

import unicodedata

import pandas as pd

from .config import RAW

TIPOS = ["postado", "transito", "saiu_entrega", "tentativa", "entregue",
         "devolvido", "extraviado", "outro", "desconhecido"]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


# texto normalizado do evento -> tipo padrão
_TEXTO_PARA_TIPO = {
    # Expressa Já
    "objeto postado": "postado",
    "em transito para unidade de distribuicao": "transito",
    "saiu para entrega": "saiu_entrega",
    "entregue": "entregue",
    "tentativa de entrega - destinatario ausente": "tentativa",
    "devolvido ao remetente": "devolvido",
    "objeto extraviado": "extraviado",
    # TransNorte
    "coleta_realizada": "postado",
    "em_transferencia": "transito",
    "em_rota": "saiu_entrega",
    "tentativa_sem_sucesso": "tentativa",
    "devolvido": "devolvido",
    "extraviado": "extraviado",
    # Rápido Sul
    "coletado no remetente": "postado",
    "em transferencia entre filiais": "transito",
    "em rota de entrega": "saiu_entrega",
    "entrega nao realizada - destinatario ausente": "tentativa",
    "devolucao ao remetente": "devolvido",
    "mercadoria extraviada": "extraviado",
    # Correio Ágil
    "objeto em transito - por favor aguarde": "transito",
    "objeto saiu para entrega ao destinatario": "saiu_entrega",
    "objeto entregue ao destinatario": "entregue",
    "a entrega nao pode ser efetuada - carteiro nao atendido": "tentativa",
    "objeto devolvido ao remetente": "devolvido",
}

# ViaLog: código numérico -> tipo (descrições em portal_vialog_codigos.csv)
_VIALOG = {
    10: "postado", 20: "transito", 30: "saiu_entrega", 40: "tentativa", 41: "tentativa",
    50: "entregue", 55: "entregue", 60: "devolvido", 70: "outro", 90: "extraviado", 99: "outro",
}


def normalizar_rastreio(serie: pd.Series) -> pd.Series:
    """Código de rastreio comparável entre ERP e portal: maiúsculo e sem espaço ou separador.

    Alguns portais mandam 'TN4 761325774' enquanto o ERP guarda 'TN4761325774'."""
    limpo = serie.astype("string").str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    return limpo.astype(object).where(limpo.notna(), None)   # código ausente continua ausente (envio sem rastreio)


def _padrao(df: pd.DataFrame, transportadora: str, *, utc: bool = False) -> pd.DataFrame:
    df = df.copy()
    df["rastreio"] = normalizar_rastreio(df["rastreio"])
    df["transportadora"] = transportadora
    df["quando_eh_utc"] = utc
    return df[["rastreio", "transportadora", "quando", "quando_eh_utc", "tipo", "evento_original"]]


def _tipo_por_texto(serie: pd.Series) -> pd.Series:
    return serie.map(lambda t: _TEXTO_PARA_TIPO.get(_norm(t), "desconhecido"))


def expressa_ja() -> pd.DataFrame:
    d = pd.read_csv(RAW / "portal_expressa_ja.csv", dtype=str)
    return _padrao(pd.DataFrame({
        "rastreio": d["codigo_rastreio"],
        "quando": pd.to_datetime(d["data_hora"], errors="coerce"),
        "tipo": _tipo_por_texto(d["evento"]),
        "evento_original": d["evento"],
    }), "Expressa Já")


def transnorte() -> pd.DataFrame:
    d = pd.read_csv(RAW / "portal_transnorte.csv", dtype=str)
    return _padrao(pd.DataFrame({
        "rastreio": d["rastreio"],
        "quando": pd.to_datetime(d["quando"], format="%Y-%m-%d %H:%M", errors="coerce"),
        "tipo": _tipo_por_texto(d["status"]),
        "evento_original": d["status"],
    }), "TransNorte")


def rapido_sul() -> pd.DataFrame:
    d = pd.read_csv(RAW / "portal_rapido_sul.csv", sep=";", dtype=str)
    return _padrao(pd.DataFrame({
        "rastreio": d["rastreio"],
        "quando": pd.to_datetime(d["data_hora"], format="%d/%m/%Y %H:%M", errors="coerce"),
        "tipo": _tipo_por_texto(d["ocorrencia"]),
        "evento_original": d["ocorrencia"],
    }), "Rápido Sul")


def vialog() -> pd.DataFrame:
    d = pd.read_csv(RAW / "portal_vialog.csv", dtype=str)
    cod = pd.to_numeric(d["cod_status"].str.strip(), errors="coerce")
    desc = pd.read_csv(RAW / "portal_vialog_codigos.csv").set_index("cod_status")["descricao"]
    return _padrao(pd.DataFrame({
        "rastreio": d["awb"],
        "quando": pd.to_datetime(d["timestamp"], errors="coerce"),
        "tipo": cod.map(_VIALOG).fillna("desconhecido"),
        "evento_original": cod.map(desc).fillna(d["cod_status"]),
    }), "ViaLog")


def correio_agil() -> pd.DataFrame:
    d = pd.read_csv(RAW / "portal_correio_agil.csv", dtype=str)
    quando = pd.to_datetime(d["data_hora_utc"], utc=True, errors="coerce").dt.tz_localize(None)
    return _padrao(pd.DataFrame({
        "rastreio": d["objeto"],
        "quando": quando,
        "tipo": _tipo_por_texto(d["descricao"]),
        "evento_original": d["descricao"],
    }), "Correio Ágil", utc=True)


def carregar_eventos() -> pd.DataFrame:
    """Todos os portais num só DataFrame, sem eventos repetidos."""
    ev = pd.concat([expressa_ja(), transnorte(), rapido_sul(), vialog(), correio_agil()],
                   ignore_index=True)
    return ev.drop_duplicates(["rastreio", "tipo", "quando"]).reset_index(drop=True)


def relatorio_qualidade(ev: pd.DataFrame) -> dict:
    """Números para o time saber em que confiar nos portais."""
    desc = ev[ev["tipo"] == "desconhecido"]
    return {
        "eventos": int(len(ev)),
        "rastreios_distintos": int(ev["rastreio"].nunique()),
        "datas_invalidas": int(ev["quando"].isna().sum()),
        "eventos_desconhecidos": int(len(desc)),
        "textos_desconhecidos": sorted(desc["evento_original"].astype(str).str.slice(0, 120).unique())[:20],
    }
