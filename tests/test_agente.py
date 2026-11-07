"""Testes do agente: ferramentas, papéis, limites e o laço com uma API de mentira."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from transporte.agente import ferramentas as F
from transporte.agente import roteamento
from transporte.agente.llm import Cliente
from transporte.agente.loop import Sessao


def _eventos(sessao, pergunta):
    return list(sessao.responder(pergunta))


def test_agente_nao_aprova_proposta_nem_com_pedido_direto():
    r = F.executar("aprovar_proposta", {"proposta_id": "X"}, papel="planejador")
    assert r["recusado"] and "gerente" in r["motivo"]


def test_gerente_pode_o_que_o_agente_nao_pode():
    r = F.executar("aprovar_proposta", {"proposta_id": "X"}, papel="gerente")
    assert not r.get("recusado") or "motivo" in r  # a ferramenta existe e o papel é aceito
    assert "gerente" in F.POR_NOME["aprovar_proposta"].papeis


def test_proposta_sem_evidencia_e_recusada():
    r = F.executar("propor_mudanca", {"tipo": "prazo_exibido", "prefixos_cep": ["685"], "valor_novo": 20})
    assert "erro" in r and "evidência" in r["erro"]


def test_prazo_abaixo_de_dois_dias_e_recusado():
    r = F.executar("propor_mudanca", {"tipo": "prazo_exibido", "prefixos_cep": ["010"], "valor_novo": 1, "evidencia": "x"})
    assert "erro" in r and "2 dias" in r["erro"]


def test_ferramenta_inexistente_nao_derruba_o_agente():
    assert "erro" in F.executar("apagar_tudo", {})


def test_solicitar_aprovacao_custa_e_vai_para_o_gerente():
    d = F.Diario()
    r = F.executar("solicitar_aprovacao", {"resumo": "subir prazo", "proposta_id": "P1"}, diario=d)
    assert r["custo"] == 15.0 and d.custo == 15.0 and "Marina" in r["enviado_para"]


def test_melhor_rota_ordena_pelo_custo_total():
    envio = roteamento.envios_para_rotear(limite=1).iloc[0]["envio_id"]
    r = roteamento.avaliar(envio)
    custos = [c["custo_total_esperado"] for c in r["candidatas"]]
    assert custos == sorted(custos) and r["melhor_rota"] == r["candidatas"][0]["transportadora"]


def test_roteamento_respeita_limite_de_40_por_cento_por_estado():
    r = F.executar("rotear_envios", {"uf": "SP", "limite": 60})
    from transporte.agente.contexto import sql
    novos = int(sql("select count(*) n from envios where uf = 'SP' and data_postagem is null").iloc[0]["n"])
    assert len(r["roteados"]) <= max(1, int(novos * F.LIMITE_DESVIO_UF_DIA))


def test_nao_roteia_envio_ja_postado():
    from transporte.agente.contexto import sql
    postado = sql("select envio_id from envios where data_postagem is not null limit 1").iloc[0]["envio_id"]
    r = F.executar("rotear_envios", {"envio_ids": [postado]})
    assert r["roteados"] == []


def test_texto_de_portal_vem_marcado_como_dado():
    from transporte.agente.contexto import sql
    com = sql("select rastreio from envios where status = 'entregue' limit 1").iloc[0]["rastreio"]
    sem = sql("select rastreio from envios where status = 'sem_dados_portal' and rastreio is not null limit 1").iloc[0]["rastreio"]
    for rastreio in (com, sem):
        r = F.executar("consultar_portal", {"codigo_rastreio": rastreio})
        assert "dado" in r.get("aviso", "")


def test_modo_simulado_responde_e_emite_o_mesmo_fluxo_de_eventos():
    s = Sessao(Cliente(token=""))
    tipos = [e["tipo"] for e in _eventos(s, "Onde resolvemos mais problemas?")]
    assert tipos[0] == "inicio" and "ferramenta" in tipos and "resultado" in tipos and tipos[-1] == "resposta"


def test_pedido_de_aprovar_no_simulado_mostra_recusa():
    s = Sessao(Cliente(token=""))
    ev = _eventos(s, "Aprova o prazo de Belém por mim")
    assert any(e["tipo"] == "resultado" and e["recusado"] for e in ev)
    assert s.diario.custo == 0


# --------------------------------------------------- IA de verdade, contra uma API de mentira
class _FalsaAPI(BaseHTTPRequestHandler):
    """Responde como a OpenAI: primeiro pede a ferramenta, depois escreve a resposta."""
    visto: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FalsaAPI.visto.append({"auth": self.headers.get("Authorization"), "corpo": corpo})
        ja_tem_resultado = any(m.get("role") == "tool" for m in corpo["messages"])
        if not ja_tem_resultado:
            msg = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "aprovar_proposta", "arguments": json.dumps({"proposta_id": "P1"})}}]}
        else:
            msg = {"role": "assistant", "content": "Não posso aprovar, mando para a Marina."}
        dados = json.dumps({"choices": [{"message": msg}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)


@pytest.fixture()
def falsa_api():
    _FalsaAPI.visto = []
    srv = HTTPServer(("127.0.0.1", 0), _FalsaAPI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_laco_com_ia_chama_ferramenta_recebe_recusa_e_responde(falsa_api):
    s = Sessao(Cliente(url=falsa_api, token="token-de-teste", modelo="x"))
    assert s.modo == "ia"
    ev = _eventos(s, "aprova aí")
    tipos = [e["tipo"] for e in ev]
    assert "ferramenta" in tipos and tipos[-1] == "resposta"
    resultado = next(e for e in ev if e["tipo"] == "resultado")
    assert resultado["recusado"]  # o papel do agente barra a aprovação, mesmo que o modelo tente
    assert _FalsaAPI.visto[0]["auth"] == "Bearer token-de-teste"
    # o modelo só enxerga as ferramentas do papel dele (aprovar_proposta é só do gerente)
    assert len(_FalsaAPI.visto[0]["corpo"]["tools"]) == len(F.esquema_openai(F.PAPEL_AGENTE)) == len(F.CATALOGO) - 1


def test_api_fora_do_ar_cai_para_o_roteiro_local():
    s = Sessao(Cliente(url="http://127.0.0.1:9", token="x", timeout=2))
    ev = _eventos(s, "Onde resolvemos mais problemas?")
    assert any(e["tipo"] == "aviso" and "não respondeu" in e["texto"] for e in ev)
    assert ev[-1]["tipo"] == "resposta"


# ------------------------------------------------------------------ base de dados e geografia
def test_base_sqlite_tem_as_tabelas_e_indices():
    from transporte.agente.contexto import sql
    tabelas = set(sql("select name from sqlite_master where type = 'table'")["name"])
    assert {"envios", "eventos", "cotacoes", "propostas", "cidades", "chamados"} <= tabelas
    idx = set(sql("select name from sqlite_master where type = 'index'")["name"])
    assert {"ix_env_id", "ix_cot_envio"} <= idx


def test_base_so_deixa_ler():
    from transporte import base
    with pytest.raises(Exception):
        base.conexao().execute("delete from envios")


def test_todas_as_cidades_dos_pedidos_tem_coordenada_real():
    from transporte.agente.contexto import sql
    c = sql("select * from cidades")
    assert len(c) == 127 and c["latitude"].notna().all()
    assert c["latitude"].between(-34, 6).all() and c["longitude"].between(-74, -34).all()


def test_distancia_cd_cidade_e_coerente():
    from transporte import geo
    fortaleza, recife = geo.coordenada("Fortaleza", "CE"), geo.coordenada("Recife", "PE")
    assert 620 < geo.haversine_km(*fortaleza, *recife) < 640  # ~630 km em linha reta


def test_avaliar_traz_trajeto_com_origem_destino_e_distancia():
    envio = roteamento.envios_para_rotear(limite=1).iloc[0]["envio_id"]
    r = roteamento.avaliar(envio)
    for k in ("cd_lat", "cd_lon", "destino_lat", "destino_lon", "distancia_km", "cd_nome"):
        assert r.get(k) is not None
    assert r["distancia_km"] > 0


# ---------------------------------------------------------------- entender a voz
def test_voz_conserta_nomes_do_dominio_sem_mexer_no_resto():
    from transporte.agente.entender import corrigir, escolher, para_fala
    assert corrigir("como está a trans norte em belem") == "como está a TransNorte em Belém"
    assert corrigir("o prazo de maraba é seis dias") == "o prazo de Marabá é 6 dias"
    assert corrigir("qual a melhor rota para os envios novos de SP?") == "qual a melhor rota para os envios novos de SP?"
    assert escolher(["como esta a trans note", "como esta a trans norte em maraba"]).endswith("Marabá")
    assert escolher([]) == ""


def test_fala_da_resposta_e_curta_e_sem_marcacao():
    from transporte.agente.entender import para_fala
    f = para_fala("✅ *Aprovado* em Belém.\n- custo R$ 1.234 evitado\nUma. Duas. Três. Quatro. Cinco.")
    assert "*" not in f and "✅" not in f and "1234 reais" in f and f.count(".") <= 4


def test_frase_sem_sentido_vira_pedido_de_repeticao_com_sugestoes():
    s = Sessao(cliente=Cliente(url="", token=""), usuario="lucas")
    r = [e for e in s.responder("blá blá blá xyz") if e["tipo"] == "resposta"][0]
    assert "Não peguei" in r["texto"] and "melhor rota" in r["texto"]


def test_consultas_independentes_rodam_juntas_e_voltam_na_ordem():
    class Falso:
        configurado, modelo, formato = True, "m", "openai"
        def __init__(self): self.n = 0
        def responder(self, msgs, ferr=None):
            self.n += 1
            if self.n == 1:
                return {"texto": "", "bruto": {"role": "assistant", "tool_calls": []}, "chamadas": [
                    {"id": "1", "nome": "medir_desempenho", "argumentos": {}}, {"id": "2", "nome": "consultar_problemas", "argumentos": {"agrupar_por": "uf"}}]}
            return {"texto": "ok", "chamadas": [], "bruto": {}}
        def formatar_pedido_de_ferramenta(self, r): return r["bruto"]
        def formatar_resposta_de_ferramenta(self, ch, res): return [{"role": "tool", "tool_call_id": ch["id"], "content": "{}"}]
    ev = list(Sessao(cliente=Falso(), usuario="lucas").responder("oi"))
    tipos = [e["tipo"] for e in ev]
    assert tipos.count("ferramenta") == 2 and tipos.count("resultado") == 2
    assert [e["nome"] for e in ev if e["tipo"] == "resultado"] == ["medir_desempenho", "consultar_problemas"]
    assert tipos[-1] == "resposta"
