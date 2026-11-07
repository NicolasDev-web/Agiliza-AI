"""Servidor do agente: conversa por SSE e serve a interface. Só biblioteca padrão.

    python servidor.py            # http://localhost:8000
    python servidor.py --porta 9000
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

from transporte import estado  # noqa: E402
from transporte.agente.llm import Cliente  # noqa: E402
from transporte.agente.loop import Sessao  # noqa: E402

PUBLICO = RAIZ / "dashboard"
SESSOES: dict[str, Sessao] = {}
TRAVA = threading.Lock()


def sessao(sid: str, usuario: str = "lucas") -> Sessao:
    with TRAVA:
        if sid not in SESSOES:
            SESSOES[sid] = Sessao(usuario=usuario, sid=sid)
        return SESSOES[sid]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, formato, *args):  # silêncio no terminal
        pass

    def _json(self, dados: dict, codigo: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/api/saude":
            c = Cliente()
            return self._json({"modo": "ia" if c.configurado else "simulado", "modelo": c.modelo,
                               "url": c.url, "formato": c.formato, "modelos_disponiveis": c.modelos()[:20]})
        q = parse_qs(url.query)
        if url.path == "/api/conversa":
            return self._conversa(q)
        if url.path == "/api/usuarios":
            return self._json({"usuarios": estado.usuarios()})
        if url.path == "/api/prazos-vigentes":
            return self._json({"prazos": estado.prazos_vigentes()})
        if url.path.startswith("/api/"):
            return self._api_com_usuario("GET", url.path, q, {})
        return self._arquivo(url.path)

    def do_POST(self) -> None:
        url = urlparse(self.path)
        tamanho = int(self.headers.get("Content-Length") or 0)
        try:
            corpo = json.loads(self.rfile.read(tamanho) or b"{}")
        except ValueError:
            return self._json({"erro": "o corpo precisa ser JSON"}, 400)
        if not url.path.startswith("/api/"):
            return self._json({"erro": "não achei isso"}, 404)
        self._api_com_usuario("POST", url.path, parse_qs(url.query), corpo)

    # ---- tudo abaixo exige saber quem é o usuário; o papel vem do servidor, nunca do navegador
    def _quem(self, q: dict, corpo: dict, papel: str | None = None) -> dict | None:
        uid = (q.get("usuario") or [corpo.get("usuario")])[0]
        u = estado.usuario(uid)
        if not u:
            self._json({"erro": "entre como Lucas ou Marina primeiro"}, 401)
            return None
        if papel and u["papel"] != papel:
            quem = "o gerente de logística" if papel == "gerente" else "o analista de logística"
            self._json({"erro": f"isso é com {quem}; {u['nome']} é {u['cargo'].lower()}"}, 403)
            return None
        return u

    def _api_com_usuario(self, metodo: str, caminho: str, q: dict, corpo: dict) -> None:
        try:
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
                    s = SESSOES.get(a["sessao"] or "")
                if s:
                    s.receber_decisao(a, u["nome"])
                return self._json({"aprovacao": a, "placar": estado.placar()})
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
        sid = (q.get("sessao") or [str(uuid.uuid4())])[0]
        u = self._quem(q, {}, "analista_logistica")
        if not u:
            return
        if not pergunta:
            return self._json({"erro": "faltou a pergunta"}, 400)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        s = sessao(sid, u["id"])
        try:
            for evento in s.responder(pergunta):
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
        self.end_headers()
        self.wfile.write(corpo)


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
    print(f"Agente de logística em http://localhost:{args.porta}  |  modo: {modo}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", args.porta), Handler).serve_forever()


if __name__ == "__main__":
    main()
