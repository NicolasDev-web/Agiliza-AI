/* Ponte do WhatsApp (WhatsApp Web, sem a API da Meta).
 * A gerente escaneia o QR code uma vez; depois o sistema envia as decisões ao analista pelo número dela.
 * Fala só com o servidor local (127.0.0.1). A sessão fica em whatsapp/sessao/ (fora do git).
 *
 * GET  /estado   -> { estado: "iniciando|aguardando_qr|conectado|desconectado", qr: "data:image/png;base64,...", numero }
 * POST /enviar   -> { numero, texto, imagem_base64? }
 * POST /sair     -> desconecta e apaga a sessão
 * Com WHATSAPP_SIMULAR=1 não toca no WhatsApp: gera um QR de mentira e POST /simular/escanear "conecta".
 */
"use strict";
const http = require("http");
const fs = require("fs");
const path = require("path");
const QRCode = require("qrcode");

const PORTA = Number(process.env.WHATSAPP_PONTE_PORTA || 8765);
const SIMULAR = process.env.WHATSAPP_SIMULAR === "1";
const PASTA = path.join(__dirname, "sessao");

let estado = "iniciando", qr = null, numero = null, sock = null, tentativas = 0;
const enviadas = [];   // só no modo simulado, para os testes conferirem

/* Quando o celular de quem recebe não consegue decifrar uma mensagem, ele pede o reenvio. Sem guardar o que
 * foi enviado, a ponte não tem o que reenviar e a pessoa vê "Aguardando mensagem. Essa ação pode levar
 * alguns minutos". Por isso guardamos as últimas mensagens (getMessage) e contamos as tentativas. */
const enviadasPorId = new Map();
function guardarEnviada(msg) {
  if (!msg || !msg.key || !msg.key.id) return;
  enviadasPorId.set(msg.key.id, msg.message);
  if (enviadasPorId.size > 300) enviadasPorId.delete(enviadasPorId.keys().next().value);
}
const tentativasDeReenvio = new Map();
const contadorDeReenvio = {
  get: (k) => tentativasDeReenvio.get(k), set: (k, v) => { tentativasDeReenvio.set(k, v); },
  del: (k) => { tentativasDeReenvio.delete(k); }, flushAll: () => { tentativasDeReenvio.clear(); },
};

async function qrImagem(texto) { return QRCode.toDataURL(texto, { margin: 1, width: 360, color: { dark: "#1c2150", light: "#ffffff" } }); }

/* ---------- WhatsApp de verdade ---------- */
async function iniciar() {
  if (SIMULAR) { estado = "aguardando_qr"; qr = await qrImagem("agiliza-simulado-" + Date.now()); return; }
  const baileys = require("@whiskeysockets/baileys");
  const makeWASocket = baileys.default || baileys.makeWASocket;
  const { useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion, Browsers } = baileys;
  const pino = require("pino");
  const { state, saveCreds } = await useMultiFileAuthState(PASTA);
  let version; try { ({ version } = await fetchLatestBaileysVersion()); } catch (e) { /* usa a que vem no pacote */ }
  sock = makeWASocket({ auth: state, version, logger: pino({ level: "silent" }), browser: Browsers.macOS("Agiliza AI"), markOnlineOnConnect: false, syncFullHistory: false,
    getMessage: async (key) => enviadasPorId.get(key.id), msgRetryCounterCache: contadorDeReenvio });
  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("connection.update", async (u) => {
    if (u.qr) { qr = await qrImagem(u.qr); estado = "aguardando_qr"; }
    if (u.connection === "open") { estado = "conectado"; qr = null; tentativas = 0; numero = (sock.user && sock.user.id || "").split(":")[0].split("@")[0] || null; console.log("[ponte] conectado", numero); }
    if (u.connection === "close") {
      const codigo = u.lastDisconnect && u.lastDisconnect.error && u.lastDisconnect.error.output && u.lastDisconnect.error.output.statusCode;
      numero = null; sock = null;
      if (codigo === DisconnectReason.loggedOut) { estado = "desconectado"; qr = null; fs.rmSync(PASTA, { recursive: true, force: true }); setTimeout(() => iniciar().catch(console.error), 500); return; }
      estado = "iniciando"; tentativas += 1;
      setTimeout(() => iniciar().catch(console.error), Math.min(2000 * tentativas, 15000));
    }
  });
}

async function enviar({ numero: para, texto, imagem_base64: img }) {
  const digitos = String(para || "").replace(/\D/g, "");
  if (digitos.length < 10) throw new Error("número do analista inválido");
  if (estado !== "conectado") throw new Error("WhatsApp não está conectado");
  if (SIMULAR) { enviadas.push({ numero: digitos, texto, imagem: !!img }); return; }
  const jid = digitos + "@s.whatsapp.net";
  const [existe] = await sock.onWhatsApp(jid);
  if (!existe || !existe.exists) throw new Error("esse número não tem WhatsApp");
  const enviada = img ? await sock.sendMessage(existe.jid, { image: Buffer.from(img, "base64"), caption: texto })
                      : await sock.sendMessage(existe.jid, { text: texto });
  guardarEnviada(enviada);
}

async function sair() {
  try { if (sock) await sock.logout(); } catch (e) { /* já caiu */ }
  fs.rmSync(PASTA, { recursive: true, force: true });
  estado = "iniciando"; qr = null; numero = null; sock = null;
  await iniciar();
}

/* ---------- HTTP local ---------- */
function corpo(req) { return new Promise((ok) => { let b = ""; req.on("data", (c) => (b += c)); req.on("end", () => { try { ok(JSON.parse(b || "{}")); } catch (e) { ok({}); } }); }); }
function json(res, cod, obj) { const s = JSON.stringify(obj); res.writeHead(cod, { "Content-Type": "application/json; charset=utf-8" }); res.end(s); }

http.createServer(async (req, res) => {
  try {
    if (req.method === "GET" && req.url === "/estado") return json(res, 200, { estado, qr, numero, simulado: SIMULAR });
    if (req.method === "GET" && req.url === "/simular/enviadas" && SIMULAR) return json(res, 200, { enviadas });
    if (req.method === "POST" && req.url === "/enviar") { await enviar(await corpo(req)); return json(res, 200, { ok: true }); }
    if (req.method === "POST" && req.url === "/sair") { await sair(); return json(res, 200, { ok: true }); }
    if (req.method === "POST" && req.url === "/simular/escanear" && SIMULAR) { estado = "conectado"; qr = null; numero = "5585900000000"; return json(res, 200, { ok: true }); }
    json(res, 404, { erro: "não existe" });
  } catch (e) { json(res, 500, { erro: String(e.message || e) }); }
}).listen(PORTA, "127.0.0.1", () => { console.log(`[ponte] ouvindo em 127.0.0.1:${PORTA}${SIMULAR ? " (simulada)" : ""}`); iniciar().catch((e) => { console.error(e); estado = "desconectado"; }); });
