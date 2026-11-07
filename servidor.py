"""Servidor do agente: conversa por SSE e serve a interface. Só biblioteca padrão.

    python servidor.py            # http://localhost:8000
    python servidor.py --porta 9000
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

from transporte.agente.llm import Cliente  # noqa: E402
from transporte.agente.loop import Sessao  # noqa: E402

PUBLICO = RAIZ / "dashboard"
SESSOES: dict[str, Sessao] = {}
TRAVA = threading.Lock()


def sessao(sid: str) -> Sessao:
    with TRAVA:
        if sid not in SESSOES:
            SESSOES[sid] = Sessao()
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
        if url.path == "/api/conversa":
            return self._conversa(parse_qs(url.query))
        return self._arquivo(url.path)

    def _conversa(self, q: dict) -> None:
        pergunta = (q.get("pergunta") or [""])[0].strip()
        sid = (q.get("sessao") or [str(uuid.uuid4())])[0]
        if not pergunta:
            return self._json({"erro": "faltou a pergunta"}, 400)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        s = sessao(sid)
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
        nome = "agente.html" if caminho in ("/", "") else caminho.lstrip("/")
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
    print(f"Agente de logística em http://localhost:{args.porta}  |  modo: {modo}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", args.porta), Handler).serve_forever()


if __name__ == "__main__":
    main()
