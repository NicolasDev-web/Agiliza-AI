"""O cartão de imagem que acompanha a mensagem de WhatsApp quando a gerente decide.

Fica de pé sozinho: se a pessoa só ver a imagem, já entende o que foi decidido, por quem e por quê.
Fonte Inter (licença OFL) em data/ref/fontes.
"""
from __future__ import annotations

import io
from datetime import datetime
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from .config import ROOT

FONTES = ROOT / "data" / "ref" / "fontes"
L, A = 1080, 1350
COBALTO, TINTA, TINTA3 = "#2f37c4", "#15184f", "#6e7299"
PAPEL, CLARA, BOM, PERDA, RECUSA = "#ececf2", "#b9bce9", "#138a5e", "#e8631e", "#b3261e"

ESTILO = {
    "aprovada": ("PRAZO APROVADO", BOM, "ANTES", "DEPOIS"),
    "ajustada": ("APROVADO COM AJUSTE", BOM, "ANTES", "DEPOIS"),
    "recusada": ("PEDIDO RECUSADO", RECUSA, "PEDIDO", "FICA"),
}


@lru_cache(maxsize=16)
def _f(peso: str, tam: int) -> ImageFont.FreeTypeFont:
    arq = FONTES / ("Inter-SemiBold.otf" if peso == "b" else "Inter-Regular.otf")
    try:
        return ImageFont.truetype(str(arq), tam)
    except OSError:   # sem a fonte da pasta: usa a que o Pillow trouxer, para nunca quebrar o envio
        return ImageFont.load_default(tam)


def _quebra(d: ImageDraw.ImageDraw, texto: str, fonte, largura: int, max_linhas: int) -> list[str]:
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = f"{atual} {palavra}".strip()
        if d.textlength(teste, font=fonte) <= largura:
            atual = teste
        else:
            linhas.append(atual); atual = palavra
    linhas.append(atual)
    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        linhas[-1] = linhas[-1].rstrip(" .,;") + "…"
    return linhas


def _n(x) -> str:
    return "–" if x is None else f"{x:g}".replace(".", ",")


def _local(a: dict) -> tuple[str, str]:
    """(cidade/UF, linha de apoio) a partir do primeiro prefixo do pedido."""
    try:
        from .agente.contexto import tabela
        r = tabela("regras")
        r = r[r["cep3"] == (a.get("prefixos") or [""])[0]]
        if len(r):
            r = r.iloc[0]
            return f"{r['cidade_referencia']}/{r['uf']}", f"prefixo {r['cep3']} · {r['transportadora_padrao']}"
    except Exception:
        pass
    return "Mudança de prazo", f"pedido #{a.get('id', '')}"


def gerar(a: dict, por: str) -> bytes:
    """PNG 1080x1350 (4:5, boa para a tela do WhatsApp)."""
    titulo, cor, rot_a, rot_b = ESTILO.get(a["situacao"], ESTILO["recusada"])
    im = Image.new("RGB", (L, A), "white")
    d = ImageDraw.Draw(im)

    # faixa da marca
    d.rectangle([0, 0, L, 150], fill=COBALTO)
    for i, (x, y, c) in enumerate([(60, 52, "white"), (92, 52, CLARA), (60, 84, CLARA), (92, 84, "white")]):
        d.rectangle([x, y, x + 24, y + 24], fill=c)
    d.text((140, 46), "Agiliza", font=_f("b", 52), fill="white")
    d.text((140 + d.textlength("Agiliza ", font=_f("b", 52)), 46), "AI", font=_f("b", 52), fill=CLARA)

    # selo
    fs = _f("b", 38)
    w = int(d.textlength(titulo, font=fs)) + 72
    d.rounded_rectangle([60, 210, 60 + w, 282], radius=36, fill=cor)
    d.text((96, 224), titulo, font=fs, fill="white")

    cidade, apoio = _local(a)
    d.text((60, 322), cidade, font=_f("b", 84 if len(cidade) < 18 else 64), fill=TINTA)
    d.text((60, 430), apoio, font=_f("r", 34), fill=TINTA3)

    # antes -> depois
    d.rounded_rectangle([60, 520, L - 60, 800], radius=24, fill=PAPEL)
    if a.get("valor_proposto") is not None:
        final = a["valor_final"] if a["situacao"] != "recusada" else a["valor_atual"]
        esq = a["valor_atual"] if a["situacao"] != "recusada" else a["valor_proposto"]
        for x, rot, val, cl in ((110, rot_a, esq, TINTA3), (610, rot_b, final, cor if a["situacao"] != "recusada" else TINTA)):
            d.text((x, 550), rot, font=_f("r", 30), fill=TINTA3)
            d.text((x, 600), _n(val), font=_f("b", 150), fill=cl)
            d.text((x, 760), "dias úteis", font=_f("r", 28), fill=TINTA3)
        d.text((500, 640), "→", font=_f("b", 90), fill=TINTA3)
    else:
        for i, linha in enumerate(_quebra(d, a["resumo"], _f("b", 44), L - 220, 4)):
            d.text((110, 560 + i * 58), linha, font=_f("b", 44), fill=TINTA)

    y = 850
    if a.get("comentario"):
        linhas = _quebra(d, "“" + a["comentario"] + "”", _f("r", 42), L - 200, 5)
        d.rectangle([60, y, 70, y + 56 + len(linhas) * 54], fill=cor)
        d.text((100, y), f"O QUE {por.split()[0].upper()} DISSE", font=_f("r", 28), fill=TINTA3)
        for i, linha in enumerate(linhas):
            d.text((100, y + 50 + i * 54), linha, font=_f("r", 42), fill=TINTA)

    quando = (a.get("decidido_em") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    dt = datetime.strptime(quando, "%Y-%m-%d %H:%M:%S")
    d.text((60, 1195), f"Decidido por {por} · {dt:%d/%m} às {dt:%H:%M}", font=_f("r", 32), fill=TINTA)
    d.line([60, 1262, L - 60, 1262], fill=PAPEL, width=3)
    d.text((60, 1282), "Agiliza AI · demonstração com dados fictícios", font=_f("r", 26), fill=TINTA3)

    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()
