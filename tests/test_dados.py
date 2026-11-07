"""Testes com os dados reais do desafio (data/raw)."""
import pandas as pd
import pytest

from transporte import entregas, portais, propostas
from transporte.config import MIN_ENVIOS_PREFIXO


@pytest.fixture(scope="module")
def eventos():
    return portais.carregar_eventos()


@pytest.fixture(scope="module")
def medidas(eventos):
    return entregas.medir_entregas(entregas.carregar_envios(), eventos)


def test_cep_normalizado_tem_8_digitos():
    s = pd.Series(["64037004", "18090-122", "1052000", 1052000])
    assert entregas.normalizar_cep(s).tolist() == ["64037004", "18090122", "01052000", "01052000"]


def test_data_prometida_do_erp_bate_com_a_regra_oficial():
    assert entregas.conferir_data_prometida(entregas.carregar_envios()) == 1.0


def test_todos_os_portais_entram_no_formato_unico(eventos):
    assert set(eventos["transportadora"]) == {"Expressa Já", "TransNorte", "Rápido Sul", "ViaLog", "Correio Ágil"}
    assert eventos["quando"].notna().all()
    assert not eventos.duplicated(["rastreio", "tipo", "quando"]).any()


def test_texto_estranho_de_portal_nunca_vira_evento_conhecido(eventos):
    # qualquer texto que não seja um evento conhecido fica "desconhecido", sem mudar nenhuma entrega
    desc = eventos[eventos["tipo"] == "desconhecido"]
    assert (desc["tipo"] == "desconhecido").all()
    q = portais.relatorio_qualidade(eventos)
    assert q["eventos_desconhecidos"] == len(desc)


def test_correio_agil_em_utc_vira_horario_do_destino(medidas):
    ent = medidas[(medidas["transportadora"] == "Correio Ágil") & (medidas["status"] == "entregue")]
    assert len(ent) > 1000 and ent["data_entrega"].notna().all()


def test_status_cobre_todos_os_envios(medidas):
    assert medidas["status"].notna().all()
    assert medidas.loc[medidas["status"] == "entregue", "data_entrega"].notna().all()
    # pedido ainda dentro do prazo e sem rastreio não entram na conta de cumprimento
    assert not medidas.loc[medidas["status"].isin(["em_aberto_no_prazo", "sem_rastreio"]), "medido"].any()


def test_no_prazo_so_vale_para_entregue_ate_a_data_prometida(medidas):
    ok = medidas[medidas["no_prazo"]]
    assert (ok["status"] == "entregue").all()
    assert (ok["data_entrega"] <= ok["data_prometida"]).all()


def test_custo_de_atraso_cresce_com_os_dias():
    c = propostas.custo_esperado_atraso([200, 200, 200, 200], [0, 1, 4, 12])
    assert c[0] == 0 and c[0] < c[1] < c[2] < c[3]


def test_propostas_respeitam_as_politicas(medidas):
    p = propostas.gerar(medidas)
    com_dado = p[p["envios_medidos"] >= MIN_ENVIOS_PREFIXO]
    assert (com_dado["prazo_proposto"] >= 2).all()  # mínimo absoluto de 2 dias úteis
    assert (p.loc[p["acao"] == "sem evidência", "prazo_proposto"] == p.loc[p["acao"] == "sem evidência", "prazo_site_hoje"]).all()
    # toda mudança de prazo passa pelo gerente; sem mudança não há o que aprovar
    assert p.loc[p["acao"].isin(["aumentar", "reduzir"]), "requer_aprovacao"].all()
    assert not p.loc[p["acao"].isin(["manter", "sem evidência"]), "requer_aprovacao"].any()


def test_proposta_de_aumento_melhora_o_cumprimento(medidas):
    p = propostas.gerar(medidas)
    aum = p[p["acao"] == "aumentar"]
    assert len(aum) > 0
    assert (aum["cumprimento_proposto"] >= aum["cumprimento_hoje"]).all()


def test_rastreio_com_espaco_no_portal_casa_com_o_erp():
    """O portal manda 'TN4 761325774' e o ERP guarda 'TN4761325774': sem normalizar, 158 envios ficavam sem medição."""
    s = pd.Series(["TN4 761325774", " ej912383326br ", "AB-12.3", None])
    n = portais.normalizar_rastreio(s)
    assert n[0] == "TN4761325774" and n[1] == "EJ912383326BR" and n[2] == "AB123"
    assert pd.isna(n[3])   # sem código continua sem código (o ERP usa isso para 'sem rastreio')


def test_todo_rastreio_do_portal_tem_envio_no_erp_depois_de_normalizar(eventos):
    erp = set(entregas.carregar_envios()["rastreio"].dropna())
    fora = eventos[~eventos["rastreio"].isin(erp)]["rastreio"].nunique()
    assert fora <= 230   # eram 388 antes (158 com espaço no meio); os 230 que sobram são de pedidos fora do ERP
