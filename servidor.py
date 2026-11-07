"""Servidor do agente: conversa por SSE e serve a interface. Só biblioteca padrão.

    python servidor.py            # http://localhost:8000
    python servidor.py --porta 9000
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys

for _f in (sys.stdout, sys.stderr):   # Windows: o console padrão não é UTF-8 e acento vira "?"
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

from transporte import estado, whatsapp  # noqa: E402
from transporte.agente import entender  # noqa: E402
from transporte.agente.llm import Cliente  # noqa: E402
from transporte.agente.ferramentas import PAPEL_AGENTE, PAPEL_CONSULTA  # noqa: E402
from transporte.agente.loop import Sessao  # noqa: E402

PUBLICO = RAIZ / "dashboard"
COOKIE = "agiliza_sessao"
PONTE_JS = RAIZ / "whatsapp" / "ponte.js"
TELAS = ["/login.html", "/analista.html", "/gerente.html", "/agente.html", "/index.html"]


def versao() -> str:
    """Identifica o código que está rodando: o commit do git, para ninguém confundir com a versão antiga."""
    try:
        import subprocess
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True, text=True, timeout=3).stdout.strip() or "sem-git"
    except Exception:
        return "sem-git"


VERSAO = versao()
SESSOES: dict[str, Sessao] = {}
TRAVA = threading.Lock()


def sessao(sid: str, usuario: str = "lucas", papel_usuario: str = "analista_logistica") -> Sessao:
    """Analista conversa com o agente planejador; a gerente, com o agente de consulta (só lê e explica)."""
    with TRAVA:
        chave = f"{usuario}:{sid}"   # a conversa pertence ao usuário: o mesmo sid em outro perfil é outra conversa
        if chave not in SESSOES:
            papel = PAPEL_CONSULTA if papel_usuario == "gerente" else PAPEL_AGENTE
            SESSOES[chave] = Sessao(papel=papel, usuario=usuario, sid=sid)
        return SESSOES[chave]


class Servidor(ThreadingHTTPServer):
    # No Windows, reaproveitar a porta deixa DOIS servidores no mesmo endereço e a versão antiga continua
    # respondendo sem avisar. Lá a porta ocupada tem que dar erro.
    allow_reuse_address = os.name != "nt"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, formato, *args):  # silêncio no terminal
        pass

    def _json(self, dados: dict, codigo: int = 200, cabecalhos: dict | None = None) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode()
        self.send_response(codigo)
        for k, v in (cabecalhos or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/api/saude":
            c = Cliente()
            return self._json({"app": "Agiliza AI", "versao": VERSAO, "telas": TELAS, "whatsapp": whatsapp.configuracao()["canal"],
                               "modo": "ia" if c.configurado else "simulado", "modelo": c.modelo,
                               "url": c.url, "formato": c.formato, "modelos_disponiveis": c.modelos()[:20]})
        q = parse_qs(url.query)
        if url.path == "/api/conversa":
            return self._conversa(q)
        if url.path == "/api/eu":
            u = estado.usuario_da_sessao(self._token())
            return self._json({"usuario": u}, 200 if u else 401)
        if url.path == "/api/prazos-vigentes":
            return self._json({"prazos": estado.prazos_vigentes()})
        if url.path.startswith("/api/"):
            return self._api_com_usuario("GET", url.path, q, {})
        return self._arquivo(url.path)

    def do_POST(self) -> None:
        url = urlparse(self.path)
        tamanho = int(self.headers.get("Content-Length") or 0)
        if url.path == "/api/transcrever":
            return self._transcrever(self.rfile.read(min(tamanho, 15_000_000)))
        try:
            corpo = json.loads(self.rfile.read(tamanho) or b"{}")
        except ValueError:
            return self._json({"erro": "o corpo precisa ser JSON"}, 400)
        if not url.path.startswith("/api/"):
            return self._json({"erro": "não achei isso"}, 404)
        self._api_com_usuario("POST", url.path, parse_qs(url.query), corpo)

    # ---- tudo abaixo exige login; o usuário e o papel vêm da sessão no servidor, nunca do navegador
    def _token(self) -> str | None:
        for parte in (self.headers.get("Cookie") or "").split(";"):
            nome, _, valor = parte.strip().partition("=")
            if nome == COOKIE:
                return valor
        return None

    def _quem(self, q: dict, corpo: dict, papel: str | None = None) -> dict | None:
        u = estado.usuario_da_sessao(self._token())
        if not u:
            self._json({"erro": "entre com seu e-mail e senha"}, 401)
            return None
        if papel and u["papel"] != papel:
            quem = "o gerente de logística" if papel == "gerente" else "o analista de logística"
            self._json({"erro": f"isso é com {quem}; {u['nome']} é {u['cargo'].lower()}"}, 403)
            return None
        return u

    def _api_com_usuario(self, metodo: str, caminho: str, q: dict, corpo: dict) -> None:
        try:
            if caminho == "/api/login" and metodo == "POST":
                try:
                    token, u = estado.entrar(corpo.get("email", ""), corpo.get("senha", ""))
                except estado.ErroDeRegra as e:
                    return self._json({"erro": str(e)}, 401)
                return self._json({"usuario": u}, 200, {"Set-Cookie": f"{COOKIE}={token}; HttpOnly; Path=/; SameSite=Lax; Max-Age={estado.SESSAO_HORAS * 3600}"})
            if caminho == "/api/sair" and metodo == "POST":
                estado.sair(self._token())
                return self._json({"ok": True}, 200, {"Set-Cookie": f"{COOKIE}=; HttpOnly; Path=/; Max-Age=0"})
            if caminho == "/api/eventos" and metodo == "GET":
                u = self._quem(q, corpo)
                return self._eventos(u) if u else None
            if caminho == "/api/aprovacoes" and metodo == "GET":
                u = self._quem(q, corpo)
                if not u:
                    return
                lista = estado.listar_aprovacoes(None if u["papel"] == "gerente" else u["id"])
                return self._json({"aprovacoes": lista, "placar": estado.placar() if u["papel"] == "gerente" else None})
            m = re.fullmatch(r"/api/aprovacoes/(\d+)/decidir", caminho)
            if m and metodo == "POST":
                u = self._quem(q, corpo, "gerente")
                if not u:
                    return
                try:
                    a = estado.decidir(int(m.group(1)), u["id"], corpo.get("decisao", ""), corpo.get("valor"), corpo.get("comentario", ""))
                except estado.ErroDeRegra as e:
                    return self._json({"erro": str(e)}, 409)
                with TRAVA:
                    s = SESSOES.get(f'{a["solicitante"]}:{a["sessao"] or ""}')
                if s:
                    s.receber_decisao(a, u["nome"])
                threading.Thread(target=whatsapp.enviar_decisao, args=(a, u["nome"]), daemon=True).start()
                return self._json({"aprovacao": a, "placar": estado.placar()})
            m = re.fullmatch(r"/api/cartao/(\d+)\.png", caminho)
            if m and metodo == "GET":
                u = self._quem(q, corpo)
                a = estado.aprovacao(int(m.group(1))) if u else None
                if u and (not a or (u["papel"] != "gerente" and a["solicitante"] != u["id"])):
                    return self._json({"erro": "cartão não encontrado"}, 404)
                png = whatsapp.cartao_png(int(m.group(1))) if u else None
                if u and not png:
                    return self._json({"erro": "cartão não encontrado"}, 404)
                if u:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(png)))
                    self.end_headers()
                    self.wfile.write(png)
                return
            if caminho == "/api/mensagens" and metodo == "GET":
                u = self._quem(q, corpo)
                if u:
                    self._json({"mensagens": estado.listar_mensagens(u["id"]), "canal": whatsapp.configuracao()["canal"]})
                return
            if caminho == "/api/analise" and metodo == "GET":
                if self._quem(q, corpo):
                    from transporte import analise
                    texto = (q.get("pergunta") or [""])[0].strip()[:300]
                    alts = [a for a in (q.get("alt") or [""])[0].split("||") if a.strip()]
                    texto = entender.escolher([texto] + alts) or texto
                    filtro, origem = analise.interpretar(texto, Cliente())
                    self._json({"filtro": filtro, "origem": origem, "corrigida": texto})
                return
            if caminho == "/api/dicas" and metodo == "GET":
                if self._quem(q, corpo, "analista_logistica"):
                    from transporte import dicas
                    self._json({"dicas": dicas.dicas_de_prazo(3)})
                return
            if caminho == "/api/whatsapp" and metodo == "GET":
                if self._quem(q, corpo, "gerente"):
                    st = whatsapp.status_da_ponte()
                    if st["estado"] == "conectado":
                        threading.Thread(target=whatsapp.enviar_pendentes, daemon=True).start()
                    d = whatsapp.configuracao()["destino"]
                    self._json({**st, "destino": whatsapp.mascara(d) if d else None, "ponte_instalada": PONTE_JS.exists() and (PONTE_JS.parent / "node_modules").exists()})
                return
            if caminho == "/api/whatsapp/sair" and metodo == "POST":
                if self._quem(q, corpo, "gerente"):
                    try:
                        whatsapp._chamar("/sair", {}, espera=30)
                        self._json({"ok": True})
                    except RuntimeError as e:
                        self._json({"erro": str(e)}, 502)
                return
            if caminho == "/api/alertas" and metodo == "GET":
                if self._quem(q, corpo, "gerente"):
                    self._json({"alertas": estado.listar_alertas(), "placar": estado.placar()})
                return
            m = re.fullmatch(r"/api/alertas/(\d+)/ciente", caminho)
            if m and metodo == "POST":
                if self._quem(q, corpo, "gerente"):
                    estado.marcar_ciente(int(m.group(1)))
                    self._json({"ok": True, "placar": estado.placar()})
                return
            if caminho == "/api/demo/reiniciar" and metodo == "POST":
                if self._quem(q, corpo, "gerente"):
                    estado.reiniciar()
                    estado.BARRAMENTO.publicar("todos", "reiniciado")
                    self._json({"ok": True})
                return
            self._json({"erro": "rota desconhecida"}, 404)
        except Exception:
            self._json({"erro": "algo quebrou no servidor", "detalhe": traceback.format_exc()[-500:]}, 500)

    def _transcrever(self, audio: bytes) -> None:
        """Voz -> texto quando o navegador não sabe transcrever sozinho (Firefox, por exemplo)."""
        if not self._quem({}, {}):
            return
        c = Cliente()
        if not c.configurado:
            return self._json({"erro": "sem token da IA no .env: use o Chrome, que transcreve no próprio navegador"}, 501)
        try:
            self._json({"texto": c.transcrever(audio, (self.headers.get("Content-Type") or "audio/webm"))})
        except Exception as e:
            self._json({"erro": f"não consegui transcrever: {e}"}, 502)

    def _eventos(self, u: dict) -> None:
        """Canal em tempo real de um usuário: o que chega para ele aparece na tela na hora."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        chaves = {u["id"], f"papel:{u['papel']}"}
        cursor = estado.BARRAMENTO.ultimo()
        self._enviar({"tipo": "conectado", "usuario": u})
        try:
            while True:
                cursor, novos = estado.BARRAMENTO.esperar(chaves, cursor)
                if not novos:
                    self.wfile.write(b": ping\n\n"); self.wfile.flush()
                for e in novos:
                    self._enviar(e)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _conversa(self, q: dict) -> None:
        pergunta = (q.get("pergunta") or [""])[0].strip()
        voz = (q.get("voz") or ["0"])[0] == "1"
        alternativas = [a for a in (q.get("alt") or [""])[0].split("||") if a.strip()]
        sid = (q.get("sessao") or [str(uuid.uuid4())])[0]
        u = self._quem(q, {})
        if not u:
            return
        if not pergunta:
            return self._json({"erro": "faltou a pergunta"}, 400)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        s = sessao(sid, u["id"], u["papel"])
        try:
            if voz:   # a voz erra nomes do nosso domínio: escolhe a melhor alternativa e conserta
                entendido = entender.escolher([pergunta] + alternativas)
                if entendido and entendido != pergunta:
                    self._enviar({"tipo": "entendi", "original": pergunta, "texto": entendido, "sessao": sid})
                pergunta = entendido or pergunta
            for evento in s.responder(pergunta, voz):
                evento["sessao"] = sid
                self._enviar(evento)
        except Exception:
            self._enviar({"tipo": "erro", "texto": "Algo quebrou aqui no servidor.",
                          "detalhe": traceback.format_exc()[-600:]})
        self._enviar({"tipo": "fim"})
        self.close_connection = True  # sem Content-Length, fechar é o que avisa o fim do stream

    def _enviar(self, evento: dict) -> None:
        linha = f"data: {json.dumps(evento, ensure_ascii=False, default=str)}\n\n"
        try:
            self.wfile.write(linha.encode())
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _arquivo(self, caminho: str) -> None:
        nome = "login.html" if caminho in ("/", "") else caminho.lstrip("/")
        alvo = (PUBLICO / nome).resolve()
        if not str(alvo).startswith(str(PUBLICO.resolve())) or not alvo.is_file():
            return self._json({"erro": "não achei esse arquivo"}, 404)
        corpo = alvo.read_bytes()
        tipo = mimetypes.guess_type(str(alvo))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8" if "text" in tipo or "javascript" in tipo else tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")   # tela velha em cache é o pior bug de demonstração
        self.end_headers()
        self.wfile.write(corpo)


def iniciar_ponte():
    """Liga a ponte do WhatsApp (Node) junto com o servidor, se ela estiver instalada. Devolve o processo ou None."""
    import shutil
    import subprocess
    from transporte.agente.llm import carregar_env
    carregar_env()
    if os.getenv("WHATSAPP_PONTE") or not PONTE_JS.exists():
        return None   # ponte externa, ou ausente
    if not (PONTE_JS.parent / "node_modules").exists() or not shutil.which("node"):
        print("  WhatsApp: ponte não instalada. Para ligar o QR code: cd whatsapp && npm install", flush=True)
        return None
    if whatsapp.status_da_ponte()["estado"] != "sem_ponte":
        return None   # já tem uma rodando
    p = subprocess.Popen(["node", str(PONTE_JS)], cwd=PONTE_JS.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import atexit
    atexit.register(p.terminate)
    return p


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--porta", type=int, default=8000)
    args = p.parse_args()
    c = Cliente()
    modo = f"IA do evento ({c.modelo})" if c.configurado else "roteiro local (sem token no .env)"
    print("Abrindo a base de dados...", flush=True)
    from transporte.agente.contexto import aquecer
    aquecer()
    estado.con()
    servidor, porta = None, args.porta
    for tentativa in range(11):
        try:
            servidor = Servidor(("0.0.0.0", porta), Handler)
            break
        except OSError:
            print(f"\n!! A porta {porta} já está em uso por outro programa, provavelmente a VERSÃO ANTIGA do app.\n"
                  f"   Feche-o (Windows: netstat -ano | findstr :{porta}  e  taskkill /PID <número> /F) ou use a porta abaixo.", flush=True)
            porta += 1
    if servidor is None:
        raise SystemExit("Nenhuma porta livre entre %d e %d." % (args.porta, args.porta + 10))
    iniciar_ponte()
    print(f"\nAgiliza AI · versão {VERSAO} · modo: {modo}", flush=True)
    print(f"  Entrar:   http://localhost:{porta}/login.html", flush=True)
    print(f"  Conferir: http://localhost:{porta}/api/saude  (deve mostrar \"app\": \"Agiliza AI\" e versão {VERSAO})\n", flush=True)
    servidor.serve_forever()


if __name__ == "__main__":
    main()
