/* Início do analista: poucas coisas, as que importam. A conversa fica no agente do canto. */
(async function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  function h(tag, attrs, ...filhos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") el.className = v; else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) el.setAttribute(k, v);
    }
    filhos.flat().forEach((f) => { if (f != null) el.append(f.nodeType ? f : document.createTextNode(String(f))); });
    return el;
  }
  const brl = (x) => (x == null ? "–" : "R$ " + Number(x).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const km = (x) => (x == null ? "" : Math.round(x).toLocaleString("pt-BR") + " km");
  const dias = (x) => (x == null ? "" : `${Number(x).toLocaleString("pt-BR")} dias úteis`);
  const hora = (s) => (s || "").slice(11, 16);

  const eu = await window.Agiliza.exigir("analista_logistica");
  const periodo = new Date().getHours() < 12 ? "Bom dia" : new Date().getHours() < 18 ? "Boa tarde" : "Boa noite";
  $("#ola").textContent = `${periodo}, ${eu.nome.split(" ")[0]}`;

  [["Melhor rota dos envios novos", "Qual a melhor rota para os envios novos de SP?"], ["Qual prazo precisa mudar?", "Qual prazo do site precisa mudar?"], ["Onde há mais problemas?", "Onde resolvemos mais problemas?"]]
    .forEach(([t, p]) => $("#acoes").append(h("button", { type: "button", class: "botao botao-cobalto", onclick: () => window.AgilizaAgente && window.AgilizaAgente.perguntar(p) }, h("span", { class: "botao-icone", "aria-hidden": "true" }, "→"), t)));

  $("#visao").addEventListener("toggle", () => { if ($("#visao").open && window.Agiliza.panorama) window.Agiliza.panorama($("#panorama"), "analista"); }, { once: true });

  /* ---------- mapa (coordenadas reais dos municípios) ---------- */
  const temMapa = typeof L !== "undefined";
  let mapa = null, camada = null;
  if (temMapa) {
    mapa = L.map("mapa-rota", { zoomSnap: 0.25, scrollWheelZoom: false, attributionControl: false, zoomControl: false });
    const base = L.geoJSON(window.UFS, { style: { fillColor: "#e3e4ef", fillOpacity: 1, color: "#fff", weight: 1 }, interactive: false }).addTo(mapa);
    mapa.fitBounds(base.getBounds(), { padding: [4, 4] }); camada = L.layerGroup().addTo(mapa);
  } else $("#mapa-rota").textContent = "Mapa indisponível: sem acesso ao Leaflet.";
  const ponto = (p, cor, rotulo, lado) => L.circleMarker(p, { radius: 7, color: "#fff", weight: 2, fillColor: cor, fillOpacity: 1 }).bindTooltip(rotulo, { permanent: !!lado, direction: lado || "top" }).addTo(camada);

  function rotaUnica(r) {
    if (r.cd_lat != null && temMapa) {
      camada.clearLayers(); const o = [r.cd_lat, r.cd_lon], d = [r.destino_lat, r.destino_lon];
      L.polyline([o, d], { color: "#2f37c4", weight: 3, dashArray: "6 6" }).addTo(camada);
      ponto(o, "#1f2599", r.cd_nome, "right"); ponto(d, "#e8631e", `${r.destino} · ${km(r.distancia_km)}`, "left");
      mapa.fitBounds(L.latLngBounds([o, d]).pad(0.5), { maxZoom: 7 });
    }
    const atual = (r.candidatas || []).find((c) => c.foi_a_escolhida_no_erp);
    $("#rota-sub").textContent = r.envio_id;
    $("#rota-resumo").replaceChildren(
      h("p", { class: "rota-titulo" }, h("b", {}, r.melhor_rota), ` para ${r.destino}`),
      h("p", { class: "rota-linha" }, atual && atual.transportadora !== r.melhor_rota ? `Economiza ${brl(r.economia_vs_escolha_atual)} contra a ${atual.transportadora}.` : "É a que já está no pedido."),
      h("p", { class: "rota-pe" }, `${km(r.distancia_km)} em linha reta`));
  }
  function lote(r) {
    const lista = (r.roteados || []).filter((x) => x.destino_lat != null);
    if (temMapa && lista.length) {
      camada.clearLayers(); const pts = [];
      lista.forEach((x) => { const o = [x.origem_lat, x.origem_lon], d = [x.destino_lat, x.destino_lon]; L.polyline([o, d], { color: "#2f37c4", weight: 2, opacity: .8 }).addTo(camada); ponto(d, "#e8631e", `${x.destino}: ${x.de} → ${x.para}`); pts.push(o, d); });
      mapa.fitBounds(L.latLngBounds(pts).pad(0.2), { maxZoom: 7 });
    }
    $("#rota-sub").textContent = "lote";
    $("#rota-resumo").replaceChildren(
      h("p", { class: "rota-titulo" }, h("b", {}, `${(r.roteados || []).length} envios trocados`), ` · economia ${brl(r.economia_total)}`),
      ...(r.roteados || []).slice(0, 3).map((x) => h("p", { class: "rota-linha" }, `${x.destino}: ${x.de} → ${x.para}`)),
      r.gerente_avisado ? h("p", { class: "rota-pe" }, "A Marina já recebeu o alerta financeiro.") : null);
  }
  document.addEventListener("agiliza:agente", (ev) => {
    const e = ev.detail; if (e.tipo !== "resultado") return; const r = e.resultado || {};
    if (e.nome === "escolher_melhor_rota") { if (r.melhor_rota) rotaUnica(r); else if (r.detalhe && r.detalhe[0]) rotaUnica(r.detalhe[0]); }
    if (e.nome === "rotear_envios") lote(r);
    if (e.nome === "solicitar_aprovacao") { carregarFila(); carregarDicas(); }
  });

  /* ---------- pedidos para a Marina ---------- */
  const ROT = { pendente: "Aguardando a Marina", aprovada: "Aprovado", ajustada: "Aprovado com ajuste", recusada: "Recusado" };
  function fila(lista) {
    const abertos = lista.filter((a) => a.situacao === "pendente").length;
    $("#n-pedidos").replaceChildren(abertos ? h("em", {}, abertos) : "");
    $("#fila").replaceChildren(...(lista.length ? lista.slice(0, 5).map((a) => h("div", { class: "aprov " + a.situacao },
      h("p", {}, a.resumo),
      a.valor_proposto != null ? h("p", { class: "aprov-valor" }, `${dias(a.valor_atual)} → ${dias(a.situacao === "aprovada" || a.situacao === "ajustada" ? a.valor_final : a.valor_proposto)}`) : null,
      h("div", { class: "estado " + a.situacao }, h("i"), ROT[a.situacao]),
      a.comentario ? h("p", { class: "aprov-com" }, `Marina: “${a.comentario}”`) : null))
      : [h("p", { class: "vazio" }, "Quando o agente precisar de um OK, o pedido aparece aqui com a resposta dela.")]));
  }
  async function carregarFila() { try { const r = await fetch("/api/aprovacoes"); if (r.ok) fila((await r.json()).aprovacoes); } catch (e) { /* servidor fora */ } }

  /* ---------- WhatsApp: a mensagem e o cartão como chegam ---------- */
  function zap(m, canal) {
    const sit = { enviada: "enviada ao seu WhatsApp", pendente: "vai ao seu WhatsApp assim que a Marina conectar", previa: "prévia: WhatsApp ainda não conectado", falhou: "o WhatsApp falhou; veja aqui" }[m.situacao] || m.situacao;
    $("#canal").textContent = m.situacao === "enviada" ? "enviada" : "prévia";
    $("#zap").replaceChildren(h("div", { class: "zap-bolha" },
      h("img", { src: m.imagem, alt: "Cartão da decisão", loading: "lazy" }),
      h("div", { class: "zap-texto" }, ...m.texto.split(/(\*[^*\n]+\*)/g).map((p) => (/^\*[^*\n]+\*$/.test(p) ? h("b", {}, p.slice(1, -1)) : p))),
      h("span", { class: "zap-hora" }, hora(m.quando) + " ✓✓")),
      h("p", { class: "rota-pe" }, `${sit}${m.destino ? " · " + m.destino : ""}`));
  }
  async function carregarMensagens() { try { const r = await fetch("/api/mensagens"); if (r.ok) { const d = await r.json(); if (d.mensagens[0]) zap(d.mensagens[0], d.canal); else $("#canal").textContent = d.canal === "qr" ? "ligado" : "prévia"; } } catch (e) { /* servidor fora */ } }

  /* ---------- o que o agente acha que vale pedir à Marina ---------- */
  const brl0 = (x) => "R$ " + Number(x).toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  const pedir = (t) => window.AgilizaAgente && window.AgilizaAgente.perguntar(t);
  async function carregarDicas() {
    try {
      const r = await fetch("/api/dicas"); if (!r.ok) return; const { dicas } = await r.json();
      $("#dicas-painel").hidden = !dicas.length; $("#n-dicas").replaceChildren(dicas.length ? h("em", {}, dicas.length) : "");
      $("#dicas").replaceChildren(...dicas.map((d) => h("div", { class: "dica" },
        h("b", {}, `${d.cidade}/${d.uf}: ${d.hoje} → ${d.proposto} dias úteis`),
        h("small", {}, `${d.motivo} `, h("span", { class: "ganho" }, `evita ~${brl0(d.impacto)}`)),
        h("button", { type: "button", class: "botao botao-cobalto pequeno", onclick: () => pedir(d.pedido) }, "Pedir"))),
        ...(dicas.length > 1 ? [h("button", { type: "button", class: "botao botao-cheio pequeno dicas-todas", onclick: () => pedir("Peça à Marina para mudar o prazo de " + dicas.map((d) => `${d.cidade} para ${d.proposto} dias`).join(", ")) }, `Pedir as ${dicas.length} de uma vez`)] : []));
    } catch (e) { /* servidor fora */ }
  }

  carregarFila(); carregarMensagens(); carregarDicas();
  const canal = new EventSource("/api/eventos");
  canal.onmessage = (m) => {
    let e; try { e = JSON.parse(m.data); } catch (x) { return; }
    if (e.tipo === "pedido_enviado" || e.tipo === "decisao" || e.tipo === "reiniciado") { carregarFila(); carregarDicas(); }
    if (e.tipo === "whatsapp") zap(e.mensagem);
    if (e.tipo === "reiniciado") { $("#zap").replaceChildren(h("p", { class: "vazio" }, "Quando a Marina decidir, a resposta chega aqui e no seu WhatsApp.")); }
  };
})();
