/* Agente em tempo real: recebe os eventos do servidor (SSE) e desenha o trabalho na hora. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  function h(tag, attrs, ...filhos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) el.setAttribute(k, v);
    }
    filhos.flat().forEach((f) => { if (f != null) el.append(f.nodeType ? f : document.createTextNode(String(f))); });
    return el;
  }
  const hora = () => new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  const brl = (x) => (x == null ? "–" : "R$ " + Number(x).toLocaleString("pt-BR", { maximumFractionDigits: 2 }));
  const pct = (x) => (x == null ? "–" : Math.round(x * 100) + "%");
  const sid = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())).slice(0, 8);
  $("#sessao-id").textContent = "sessão " + sid;

  const chat = $("#chat"), tempo = $("#tempo"), form = $("#form"), campo = $("#pergunta"), botao = $("#enviar");
  const placar = { ferr: 0, acoes: 0, custo: 0 };
  let ocupado = false, fonte = null, digitando = null, passoAtual = null;

  /* texto do WhatsApp: *negrito* e quebras de linha, sem HTML */
  function formatar(texto) {
    const frag = document.createDocumentFragment();
    texto.split(/(\*[^*\n]+\*)/g).forEach((p) => {
      if (/^\*[^*\n]+\*$/.test(p)) frag.append(h("b", {}, p.slice(1, -1))); else frag.append(p);
    });
    return frag;
  }
  function bolha(tipo, texto) {
    const b = h("div", { class: "bolha " + tipo }, formatar(texto));
    if (tipo !== "sis") b.append(h("span", { class: "hora" }, hora()));
    chat.append(b); chat.scrollTop = chat.scrollHeight; return b;
  }
  function mostrarDigitando(sim) {
    if (sim && !digitando) { digitando = h("div", { class: "digitando" }, h("i"), h("i"), h("i")); chat.append(digitando); chat.scrollTop = chat.scrollHeight; }
    if (!sim && digitando) { digitando.remove(); digitando = null; }
  }
  function atualizarPlacar() {
    $("#p-ferr").textContent = placar.ferr; $("#p-acoes").textContent = placar.acoes;
    $("#p-custo").textContent = "R$ " + placar.custo.toLocaleString("pt-BR");
  }

  /* modo: IA de verdade ou roteiro local, dito com todas as letras */
  fetch("/api/saude").then((r) => r.json()).then((d) => {
    const m = $("#modo"); m.className = "ag-modo " + d.modo;
    m.querySelector("span").textContent = d.modo === "ia" ? `IA do evento conectada · ${d.modelo}` : "sem token: roteiro local (mesmas ferramentas, sem IA)";
  }).catch(() => { $("#modo span").textContent = "servidor fora do ar: rode python servidor.py"; });

  /* sugestões */
  ["Onde resolvemos mais problemas?", "Qual a melhor rota para os envios novos de SP?", "Como está o prazo de Belém?", "Aprova o prazo de Belém por mim", "Como está a TransNorte?"]
    .forEach((t) => $("#sugestoes").append(h("button", { type: "button", onclick: () => perguntar(t) }, t)));
  bolha("sis", "Conversa com o agente de logística · 02/11/2026");
  bolha("ag", "Oi! Eu leio os portais, meço quem entrega no prazo e proponho o prazo do site. O que você quer resolver hoje?");

  /* ---------- mapa da rota ---------- */
  const CD = { CD1: { nome: "CD Fortaleza", p: [-3.77, -38.52] }, CD2: { nome: "CD Extrema", p: [-22.85, -46.32] } };
  const centro = {};
  window.UFS.features.forEach((f) => {
    let xs = [], ys = [];
    f.geometry.coordinates.forEach((poly) => poly[0].forEach(([x, y]) => { xs.push(x); ys.push(y); }));
    centro[f.properties.uf] = [(Math.min(...ys) + Math.max(...ys)) / 2, (Math.min(...xs) + Math.max(...xs)) / 2];
  });
  const mapa = L.map("mapa-rota", { zoomSnap: 0.25, scrollWheelZoom: false, attributionControl: false, zoomControl: false });
  const base = L.geoJSON(window.UFS, { style: { fillColor: "#e3e4ef", fillOpacity: 1, color: "#fff", weight: 1 }, interactive: false }).addTo(mapa);
  mapa.fitBounds(base.getBounds(), { padding: [4, 4] });
  const camadaRota = L.layerGroup().addTo(mapa);
  const cdDoEstado = (uf) => (["SP", "RJ", "MG", "ES", "PR", "SC", "RS", "MS", "MT", "GO", "DF"].includes(uf) ? "CD2" : "CD1");

  function desenharRota(r) {
    camadaRota.clearLayers();
    const uf = (r.destino || "").split("/").pop(), cd = CD[cdDoEstado(uf)], fim = centro[uf];
    if (!fim) return;
    L.polyline([cd.p, fim], { color: "#2f37c4", weight: 3, dashArray: "6 6" }).addTo(camadaRota);
    L.circleMarker(cd.p, { radius: 7, color: "#fff", weight: 2, fillColor: "#1f2599", fillOpacity: 1 }).bindTooltip(cd.nome, { permanent: true, direction: "right" }).addTo(camadaRota);
    L.circleMarker(fim, { radius: 7, color: "#fff", weight: 2, fillColor: "#e8631e", fillOpacity: 1 }).bindTooltip(r.destino, { permanent: true, direction: "left" }).addTo(camadaRota);
    mapa.fitBounds(L.latLngBounds([cd.p, fim]).pad(0.5), { maxZoom: 6 });
    $("#rota-sub").textContent = r.envio_id || "";
    const leg = $("#rota-leg"); leg.replaceChildren();
    (r.candidatas || []).slice(0, 5).forEach((c) => leg.append(h("div", { class: "cand" + (c.transportadora === r.melhor_rota ? " melhor" : "") },
      h("span", {}, (c.transportadora === r.melhor_rota ? "✓ " : "") + c.transportadora), h("span", {}, brl(c.custo_total_esperado)),
      h("small", {}, `frete ${brl(c.frete)} · ${pct(c.entregas_no_prazo)} no prazo · histórico: ${c.base_do_historico}`))));
    leg.append(h("small", { class: "vazio" }, "Rota desenhada até o centro do estado de destino."));
  }
  function desenharLote(r) {
    const primeiro = (r.roteados || [])[0];
    if (!primeiro) return;
    camadaRota.clearLayers();
    const porUf = {};
    (r.roteados || []).forEach((x) => { const u = x.destino.split("/").pop(); porUf[u] = (porUf[u] || 0) + 1; });
    Object.entries(porUf).forEach(([uf, n]) => {
      const fim = centro[uf], cd = CD[cdDoEstado(uf)]; if (!fim) return;
      L.polyline([cd.p, fim], { color: "#2f37c4", weight: 2 + n, opacity: 0.8 }).addTo(camadaRota);
      L.circleMarker(fim, { radius: 6 + n, color: "#fff", weight: 2, fillColor: "#e8631e", fillOpacity: 1 }).bindTooltip(`${uf}: ${n} trocas`, { permanent: true }).addTo(camadaRota);
    });
    const leg = $("#rota-leg"); leg.replaceChildren(h("b", {}, `${r.roteados.length} envios trocados · economia ${brl(r.economia_total)}`));
    r.roteados.slice(0, 5).forEach((x) => leg.append(h("div", { class: "cand" }, h("span", {}, `${x.envio_id} ${x.destino}`), h("span", {}, brl(x.economia_estimada)), h("small", {}, `${x.de} → ${x.para}`))));
    $("#rota-sub").textContent = "lote";
  }

  /* ---------- fila de aprovação ---------- */
  function pedidoDeAprovacao(res) {
    const fila = $("#fila"); if (fila.querySelector(".vazio")) fila.replaceChildren();
    const estado = h("div", { class: "estado" }, "aguardando a Marina Duarte");
    const decidir = (t) => {
      estado.textContent = `${t}: demonstração, nada foi alterado no site.`;
      bolha("sis", `Marina respondeu: ${t} (demonstração)`);
    };
    fila.prepend(h("div", { class: "aprov" },
      h("p", {}, h("b", {}, "Para: "), res.enviado_para || "gerente de logística"), h("p", {}, res.resumo || ""),
      h("div", { class: "botoes" },
        ...["Aprovar", "Ajustar", "Recusar"].map((t, i) => h("button", { class: "botao " + (i === 0 ? "botao-cheio" : "botao-cobalto"), onclick: () => decidir(t) }, h("span", { class: "botao-icone" }, ["✓", "~", "×"][i]), t))),
      estado));
  }

  /* ---------- resumo curto do que voltou de cada ferramenta ---------- */
  function resumoResultado(nome, r) {
    if (r.recusado) return "RECUSADO pelo sistema: " + r.motivo;
    if (r.erro) return "erro: " + r.erro;
    if (r.linhas) return `${r.linhas.length} linhas${r.total_chamados ? " · " + r.total_chamados + " chamados" : ""}`;
    if (r.melhor_rota) return `melhor rota: ${r.melhor_rota}${r.economia_vs_escolha_atual ? " · economia " + brl(r.economia_vs_escolha_atual) : ""}`;
    if (r.roteados) return `${r.roteados.length} envios trocados · ${brl(r.economia_total)}`;
    if (r.envios_avaliados != null) return `${r.envios_avaliados} avaliados · ${r.envios_que_valem_trocar} valem trocar`;
    if (r.proposta_id) return `${r.proposta_id} criada, aguardando o gerente`;
    if (r.enviado_para) return `enviado para ${r.enviado_para} · custo ${brl(r.custo)}`;
    if (r.acionado) return `${r.acionado} acionado(a) · custo ${brl(r.custo)}`;
    return "pronto";
  }

  /* ---------- eventos do servidor ---------- */
  function tratar(e) {
    switch (e.tipo) {
      case "inicio":
        $("#t-estado").textContent = "trabalhando"; $("#fone-sub").textContent = "digitando…";
        if (tempo.querySelector(".vazio")) tempo.replaceChildren();
        tempo.prepend(h("div", { class: "passo" }, h("span", { class: "nome" }, "pergunta"), h("div", {}, e.pergunta)));
        mostrarDigitando(true); break;
      case "aviso": bolha("sis", e.texto); break;
      case "nota": bolha("ag", e.texto); break;
      case "pensando": $("#t-estado").textContent = `pensando (rodada ${e.rodada})`; break;
      case "ferramenta":
        placar.ferr++; atualizarPlacar();
        passoAtual = h("div", { class: "passo " + (e.tipo_ferramenta || "") },
          h("span", { class: "quando" }, hora()), h("div", { class: "rodando" }, e.rotulo), h("span", { class: "nome" }, e.nome + "(" + JSON.stringify(e.argumentos || {}) + ")"));
        tempo.prepend(passoAtual); break;
      case "resultado": {
        if (passoAtual) {
          passoAtual.querySelector(".rodando").className = ""; if (e.recusado) passoAtual.classList.add("recusado");
          passoAtual.append(h("div", { class: "res" }, resumoResultado(e.nome, e.resultado)));
        }
        const r = e.resultado || {};
        if (e.nome === "escolher_melhor_rota" && r.melhor_rota) desenharRota(r);
        else if (e.nome === "escolher_melhor_rota" && r.detalhe && r.detalhe[0]) desenharRota(r.detalhe[0]);
        if (e.nome === "rotear_envios") desenharLote(r);
        if (r.pedir_ao_usuario || r.enviado_para) pedidoDeAprovacao(r.enviado_para ? r : { ...r, enviado_para: r.acionado, resumo: r.motivo });
        break;
      }
      case "resposta":
        mostrarDigitando(false); bolha("ag", e.texto);
        placar.acoes = (e.diario || []).filter((a) => a.ferramenta === "rotear_envios").reduce((s, a) => s + (a.detalhe.envios || 0), 0);
        placar.custo = e.custo || 0; atualizarPlacar(); break;
      case "erro": mostrarDigitando(false); bolha("sis", e.texto); break;
      case "fim":
        mostrarDigitando(false); $("#t-estado").textContent = "parado"; $("#fone-sub").textContent = "online";
        ocupado = false; botao.disabled = false; campo.focus(); if (fonte) { fonte.close(); fonte = null; } break;
    }
  }

  function perguntar(texto) {
    texto = (texto || "").trim(); if (!texto || ocupado) return;
    ocupado = true; botao.disabled = true; campo.value = ""; bolha("eu", texto);
    fonte = new EventSource(`/api/conversa?sessao=${sid}&pergunta=${encodeURIComponent(texto)}`);
    fonte.onmessage = (m) => { try { tratar(JSON.parse(m.data)); } catch (err) { console.error(err); } };
    fonte.onerror = () => { if (ocupado) { tratar({ tipo: "erro", texto: "Perdi a conexão com o servidor." }); tratar({ tipo: "fim" }); } };
  }
  form.addEventListener("submit", (ev) => { ev.preventDefault(); perguntar(campo.value); });
})();
