/* O agente no canto: um botão em todas as telas que abre a conversa, por texto ou por voz. */
(function () {
  "use strict";
  if (document.body.hasAttribute("data-sem-widget")) return;
  function h(tag, attrs, ...filhos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") el.className = v; else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) el.setAttribute(k, v);
    }
    filhos.flat().forEach((f) => { if (f != null) el.append(f.nodeType ? f : document.createTextNode(String(f))); });
    return el;
  }
  const guardar = (k, v) => { try { sessionStorage.setItem(k, v); } catch (e) { /* sem storage */ } };
  const ler = (k) => { try { return sessionStorage.getItem(k); } catch (e) { return null; } };
  const sid = ler("agiliza.sid") || (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())).slice(0, 8);
  guardar("agiliza.sid", sid);

  const SUGESTOES = {
    analista_logistica: ["Qual a melhor rota para os envios novos de SP?", "Qual prazo do site precisa mudar?", "A Marina já respondeu?"],
    gerente: ["O que está esperando minha decisão?", "Por que Marabá?", "Onde resolvemos mais problemas?"],
  };
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const podeGravar = !!(navigator.mediaDevices && window.MediaRecorder);

  let painel, lista, campo, mic, enviar, status, fonte = null, ocupado = false, digitando = null, porVoz = false, ouvir = ler("agiliza.ouvir") === "1";
  const historico = JSON.parse(ler("agiliza.chat") || "[]");

  function formatar(texto) {
    const frag = document.createDocumentFragment();
    String(texto).split(/(\*[^*\n]+\*)/g).forEach((p) => { if (/^\*[^*\n]+\*$/.test(p)) frag.append(h("b", {}, p.slice(1, -1))); else frag.append(p); });
    return frag;
  }
  function bolha(tipo, texto, voz, guardarNoHistorico = true) {
    const b = h("div", { class: "aw-bolha " + tipo }, voz ? h("span", { class: "aw-voz", title: "enviada por voz" }) : null, formatar(texto));
    lista.append(b); lista.scrollTop = lista.scrollHeight;
    if (guardarNoHistorico) { historico.push([tipo, texto, !!voz]); guardar("agiliza.chat", JSON.stringify(historico.slice(-30))); }
    return b;
  }
  function pontos(sim) {
    if (sim && !digitando) { digitando = h("div", { class: "aw-digitando" }, h("i"), h("i"), h("i"), (status = h("span", {}, "pensando…"))); lista.append(digitando); lista.scrollTop = lista.scrollHeight; }
    if (!sim && digitando) { digitando.remove(); digitando = null; }
  }

  function falar(texto) {
    if (!ouvir || !window.speechSynthesis) return;
    const u = new SpeechSynthesisUtterance(texto.replace(/\*/g, "").replace(/[✅❌▫️🔴🟢•]/g, "")); u.lang = "pt-BR"; u.rate = 1.05;
    speechSynthesis.cancel(); speechSynthesis.speak(u);
  }

  function tratar(e) {
    document.dispatchEvent(new CustomEvent("agiliza:agente", { detail: e }));
    switch (e.tipo) {
      case "ferramenta": if (status) status.textContent = e.rotulo + "…"; break;
      case "nota": bolha("ag", e.texto); break;
      case "resposta": pontos(false); bolha("ag", e.texto); if (porVoz) falar(e.texto); break;
      case "erro": pontos(false); bolha("sis", e.texto); break;
      case "fim": pontos(false); ocupado = false; enviar.disabled = false; porVoz = false; if (fonte) { fonte.close(); fonte = null; } break;
    }
  }
  function perguntar(texto, voz) {
    texto = (texto || "").trim(); if (!texto || ocupado) return;
    abrir(); ocupado = true; enviar.disabled = true; campo.value = ""; porVoz = !!voz;
    bolha("eu", texto, voz); pontos(true);
    fonte = new EventSource(`/api/conversa?sessao=${sid}&pergunta=${encodeURIComponent(texto)}`);
    fonte.onmessage = (m) => { try { tratar(JSON.parse(m.data)); } catch (err) { console.error(err); } };
    fonte.onerror = () => { if (ocupado) { tratar({ tipo: "erro", texto: "Perdi a conexão com o servidor." }); tratar({ tipo: "fim" }); } };
  }

  /* ---------- voz ---------- */
  let reconhecimento = null, gravador = null, pedacos = [];
  function marcarMic(ligado) { mic.classList.toggle("ligado", ligado); mic.setAttribute("aria-pressed", ligado); mic.title = ligado ? "Parar e enviar" : "Falar com o agente"; }
  function comecarVoz() {
    if (ocupado) return;
    if (SR) {
      reconhecimento = new SR(); reconhecimento.lang = "pt-BR"; reconhecimento.interimResults = true; reconhecimento.continuous = false;
      let final = "";
      reconhecimento.onresult = (ev) => {
        let parcial = ""; final = "";
        for (const r of ev.results) { if (r.isFinal) final += r[0].transcript; else parcial += r[0].transcript; }
        campo.value = (final + " " + parcial).trim();
      };
      reconhecimento.onerror = (ev) => { marcarMic(false); if (ev.error === "not-allowed") bolha("sis", "O navegador bloqueou o microfone. Libere nas permissões do site.", false, false); };
      reconhecimento.onend = () => { marcarMic(false); const t = (final || campo.value).trim(); reconhecimento = null; if (t) perguntar(t, true); };
      marcarMic(true); reconhecimento.start(); return;
    }
    if (podeGravar) {   // navegador sem reconhecimento de voz: grava e o servidor transcreve
      navigator.mediaDevices.getUserMedia({ audio: true }).then((fluxo) => {
        pedacos = []; gravador = new MediaRecorder(fluxo);
        gravador.ondataavailable = (ev) => pedacos.push(ev.data);
        gravador.onstop = async () => {
          fluxo.getTracks().forEach((t) => t.stop()); marcarMic(false);
          const blob = new Blob(pedacos, { type: gravador.mimeType || "audio/webm" });
          campo.placeholder = "transcrevendo…";
          try {
            const r = await fetch("/api/transcrever", { method: "POST", headers: { "Content-Type": blob.type }, body: blob }); const d = await r.json();
            if (!r.ok) throw new Error(d.erro); perguntar(d.texto, true);
          } catch (err) { bolha("sis", err.message || "Não consegui transcrever o áudio.", false, false); }
          campo.placeholder = "Escreva ou fale com o agente…";
        };
        marcarMic(true); gravador.start();
      }).catch(() => bolha("sis", "Não consegui abrir o microfone.", false, false));
    }
  }
  function pararVoz() { if (reconhecimento) reconhecimento.stop(); else if (gravador && gravador.state === "recording") gravador.stop(); }

  /* ---------- tela ---------- */
  function abrir() { painel.classList.add("aberto"); document.body.classList.add("aw-aberto"); campo && campo.focus({ preventScroll: true }); guardar("agiliza.aberto", "1"); }
  function fechar() { painel.classList.remove("aberto"); document.body.classList.remove("aw-aberto"); guardar("agiliza.aberto", "0"); }

  function montar(u) {
    const css = h("link", { rel: "stylesheet", href: "widget.css" }); document.head.append(css);
    lista = h("div", { class: "aw-lista", "aria-live": "polite" });
    campo = h("input", { placeholder: "Escreva ou fale com o agente…", autocomplete: "off", "aria-label": "Mensagem para o agente" });
    enviar = h("button", { type: "submit", class: "aw-enviar", "aria-label": "Enviar" }, "↑");
    mic = h("button", { type: "button", class: "aw-mic", "aria-label": "Falar com o agente", "aria-pressed": "false", title: "Falar com o agente", onclick: () => (mic.classList.contains("ligado") ? pararVoz() : comecarVoz()) });
    if (!SR && !podeGravar) mic.hidden = true;
    const som = h("button", { type: "button", class: "aw-som" + (ouvir ? " ligado" : ""), title: "Ouvir as respostas em voz alta", "aria-label": "Ouvir as respostas", onclick: () => { ouvir = !ouvir; guardar("agiliza.ouvir", ouvir ? "1" : "0"); som.classList.toggle("ligado", ouvir); if (!ouvir && window.speechSynthesis) speechSynthesis.cancel(); } });
    if (!window.speechSynthesis) som.hidden = true;
    const sug = h("div", { class: "aw-sug" }, ...(SUGESTOES[u.papel] || []).map((t) => h("button", { type: "button", onclick: () => perguntar(t) }, t)));
    painel = h("section", { class: "aw-painel", "aria-label": "Agente Agiliza" },
      h("header", {}, h("span", { class: "aw-avatar", "aria-hidden": "true" }), h("div", {}, h("b", {}, "Agente Agiliza"), h("small", {}, u.papel === "gerente" ? "explica, não decide por você" : "lê os dados e age por você")), som,
        h("button", { type: "button", class: "aw-fechar", "aria-label": "Fechar", onclick: fechar }, "×")),
      lista, sug,
      h("form", { class: "aw-form", onsubmit: (ev) => { ev.preventDefault(); perguntar(campo.value); } }, campo, mic, enviar));
    const fab = h("button", { type: "button", class: "aw-fab", "aria-label": "Abrir o agente", onclick: () => (painel.classList.contains("aberto") ? fechar() : abrir()) }, h("span", { class: "aw-marca", "aria-hidden": "true" }), h("span", {}, "Pergunte ao agente"));
    document.body.append(painel, fab);

    if (historico.length) historico.forEach(([t, x, v]) => bolha(t, x, v, false));
    else bolha("ag", `Oi, ${u.nome.split(" ")[0]}! Pode escrever ou apertar o microfone e falar. ${u.papel === "gerente" ? "Eu explico qualquer pedido, mas a decisão é sua." : "Eu cuido das rotas e levo os prazos para a Marina."}`, false, false);
    if (ler("agiliza.aberto") === "1") abrir();
  }

  window.AgilizaAgente = { abrir, fechar, perguntar: (t, v) => perguntar(t, v) };
  const start = (u) => { if (u && !painel) montar(u); };
  document.addEventListener("agiliza:usuario", (e) => start(e.detail));
  if (window.Agiliza && !document.querySelector(".usuario-selo")) { /* a página decide quando exigir login */ }
})();
