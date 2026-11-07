"""Cliente do proxy de IA do evento. Só biblioteca padrão, sem dependência extra.

O proxy do GoHacks responde no formato da OpenAI (/v1/chat/completions) ou no da Anthropic
(/v1/messages). O formato é escolhido por variável de ambiente; o padrão é o da OpenAI.

    AI_PROXY_URL=https://ai-proxy.gogroupbr.com
    AI_PROXY_TOKEN=...            (nunca comitado: fica no .env)
    AI_PROXY_MODELO=gpt-4o-mini   (ou o nome que o proxy listar)
    AI_PROXY_FORMATO=openai|anthropic
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path


def carregar_env(caminho: str | Path = ".env") -> None:
    """Lê um .env simples, sem depender do python-dotenv."""
    if os.getenv("TRANSPORTE_SEM_ENV"):   # testes: não ler o .env real
        return
    p = Path(caminho)
    if not p.exists():
        return
    for linha in p.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


class SemCredencial(RuntimeError):
    pass


class ErroDaAPI(RuntimeError):
    pass


class Cliente:
    def __init__(self, url=None, token=None, modelo=None, formato=None, timeout=90):
        carregar_env()
        self.url = (url or os.getenv("AI_PROXY_URL") or "https://ai-proxy.gogroupbr.com").rstrip("/")
        self.token = token or os.getenv("AI_PROXY_TOKEN") or ""
        self.modelo = modelo or os.getenv("AI_PROXY_MODELO") or "gpt-4o-mini"
        self.formato = (formato or os.getenv("AI_PROXY_FORMATO") or "openai").lower()
        self.timeout = timeout

    @property
    def configurado(self) -> bool:
        return bool(self.token)

    def _pedir(self, caminho: str, corpo: dict | None = None, metodo="POST") -> dict:
        if not self.token:
            raise SemCredencial("Falta AI_PROXY_TOKEN. Copie .env.example para .env e ponha o token do evento.")
        dados = json.dumps(corpo).encode() if corpo is not None else None
        cab = {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}", "User-Agent": "Agiliza-AI/1.0",
               "x-api-key": self.token, "anthropic-version": "2023-06-01"}
        req = urllib.request.Request(f"{self.url}{caminho}", data=dados, headers=cab, method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise ErroDaAPI(f"HTTP {e.code} em {caminho}: {e.read().decode()[:400]}") from e
        except urllib.error.URLError as e:
            raise ErroDaAPI(f"não consegui falar com {self.url}: {e.reason}") from e

    def modelos(self) -> list[str]:
        try:
            d = self._pedir("/v1/models", metodo="GET")
        except (ErroDaAPI, SemCredencial):
            return []
        itens = d.get("data") or d.get("models") or []
        return [m.get("id") or m.get("name") for m in itens if isinstance(m, dict)]

    # ---------------------------------------------------------------- voz
    def transcrever(self, audio: bytes, mime: str = "audio/webm") -> str:
        """Áudio -> texto pelo proxy (/v1/audio/transcriptions). Só funciona se o proxy expuser um modelo de áudio."""
        if not self.token:
            raise SemCredencial("Falta AI_PROXY_TOKEN.")
        import uuid
        lim = uuid.uuid4().hex
        modelo = os.getenv("AI_PROXY_MODELO_AUDIO") or "whisper-1"
        ext = {"audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3", "audio/wav": "wav"}.get(mime.split(";")[0], "webm")
        corpo = b""
        for k, v in {"model": modelo, "language": "pt", "response_format": "json"}.items():
            corpo += f'--{lim}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        corpo += (f'--{lim}\r\nContent-Disposition: form-data; name="file"; filename="voz.{ext}"\r\n'
                  f"Content-Type: {mime}\r\n\r\n").encode() + audio + f"\r\n--{lim}--\r\n".encode()
        req = urllib.request.Request(f"{self.url}/v1/audio/transcriptions", data=corpo, method="POST", headers={
            "Content-Type": f"multipart/form-data; boundary={lim}", "Authorization": f"Bearer {self.token}", "User-Agent": "Agiliza-AI/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return (json.loads(r.read().decode()).get("text") or "").strip()
        except urllib.error.HTTPError as e:
            raise ErroDaAPI(f"HTTP {e.code} na transcrição: {e.read().decode()[:300]}") from e
        except urllib.error.URLError as e:
            raise ErroDaAPI(f"não consegui falar com {self.url}: {e.reason}") from e

    # ---------------------------------------------------------------- conversa
    def responder(self, mensagens: list[dict], ferramentas: list[dict] | None = None) -> dict:
        """Uma rodada de conversa. Devolve {texto, chamadas:[{id,nome,argumentos}], bruto}."""
        if self.formato == "anthropic":
            return self._anthropic(mensagens, ferramentas)
        return self._openai(mensagens, ferramentas)

    def _openai(self, mensagens, ferramentas):
        corpo = {"model": self.modelo, "messages": mensagens, "temperature": 0.2}
        if ferramentas:
            corpo["tools"] = ferramentas
            corpo["tool_choice"] = "auto"
        d = self._pedir("/v1/chat/completions", corpo)
        msg = (d.get("choices") or [{}])[0].get("message", {}) or {}
        chamadas = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            chamadas.append({"id": c.get("id") or fn.get("name"), "nome": fn.get("name"), "argumentos": args})
        return {"texto": msg.get("content") or "", "chamadas": chamadas, "bruto": msg}

    def _anthropic(self, mensagens, ferramentas):
        sistema = "\n\n".join(m["content"] for m in mensagens if m.get("role") == "system")
        conv = [m for m in mensagens if m.get("role") != "system"]
        corpo = {"model": self.modelo, "max_tokens": 2000, "messages": conv}
        if sistema:
            corpo["system"] = sistema
        if ferramentas:
            corpo["tools"] = [{"name": f["function"]["name"], "description": f["function"]["description"],
                               "input_schema": f["function"]["parameters"]} for f in ferramentas]
        d = self._pedir("/v1/messages", corpo)
        texto, chamadas = "", []
        for bloco in d.get("content") or []:
            if bloco.get("type") == "text":
                texto += bloco.get("text", "")
            elif bloco.get("type") == "tool_use":
                chamadas.append({"id": bloco.get("id"), "nome": bloco.get("name"), "argumentos": bloco.get("input") or {}})
        return {"texto": texto, "chamadas": chamadas, "bruto": d}

    def formatar_resposta_de_ferramenta(self, chamada: dict, resultado: dict) -> list[dict]:
        """As mensagens que devolvem o resultado da ferramenta ao modelo, no formato certo."""
        conteudo = json.dumps(resultado, ensure_ascii=False)[:6000]
        if self.formato == "anthropic":
            return [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": chamada["id"], "content": conteudo}]}]
        return [{"role": "tool", "tool_call_id": chamada["id"], "name": chamada["nome"], "content": conteudo}]

    def formatar_pedido_de_ferramenta(self, resposta: dict) -> dict:
        """A mensagem do próprio modelo pedindo as ferramentas, para manter o histórico."""
        if self.formato == "anthropic":
            return {"role": "assistant", "content": resposta["bruto"].get("content", [])}
        return resposta["bruto"]
