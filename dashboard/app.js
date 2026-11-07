/* Interface do projeto Transporte. Lê window.DADOS (data.js) e window.UFS (ufs.js). */
(function () {
  "use strict";
  const D = window.DADOS, U = window.UFS;
  const META = D.meta.meta_cumprimento;
  const NOMES_UF = {};
  U.features.forEach((f) => { NOMES_UF[f.properties.uf] = f.properties.nome; });
  const RAMPA = ["#a3a8ec", "#838ae5", "#666edd", "#4a52d3", "#1f2599"];   // cobalto, claro -> escuro
  const LARANJA = ["#f9d5bd", "#f3ae85", "#ee8a52", "#e8631e", "#bf4a10"];
  const NEUTRO = "#c9cad8";

  /* ---------- utilidades ---------- */
  const $ = (s, r = document) => r.querySelector(s);
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
  const pct = (x, d = 0) => (x == null ? "–" : (x * 100).toFixed(d).replace(".", ",") + "%");
  const num = (x) => (x == null ? "–" : Math.round(x).toLocaleString("pt-BR"));
  const brl = (x) => (x == null ? "–" : x.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }));
  const dias = (x) => (x == null ? "–" : String(x).replace(".", ","));
  const nomeUF = (uf) => NOMES_UF[uf] || uf;
  const estado = { camada: "cumprimento", transp: "todas", uf: null, acao: "todas", filtroUF: "todos", selCep: null, limite: 40, status: {} };

  /* ---------- navegação, rótulos e números ---------- */
  const nav = $("#topo");
  const aoRolar = () => nav.classList.toggle("clara", window.scrollY > window.innerHeight * 0.85);
  window.addEventListener("scroll", aoRolar, { passive: true }); aoRolar();

  $("#hero-rotulo").textContent = `${D.prefixos.length} prefixos de CEP, ${D.transportadoras.length} transportadoras, ${num(D.meta.envios_medidos)} entregas medidas`;
  $("#gerado").textContent = D.meta.gerado_em;
  const abaixo = D.prefixos.filter((p) => p.cumprimento_hoje != null && p.cumprimento_hoje < META).length;
  $("#frase-texto").replaceChildren(
    "Hoje ", h("b", {}, pct(D.meta.cumprimento_geral)), " dos pedidos chegam no prazo prometido. Em ",
    h("b", {}, `${abaixo} de ${D.prefixos.length}`), " regiões o site promete menos do que a transportadora entrega."
  );
  const numeros = [
    [pct(D.meta.cumprimento_geral), `dos pedidos chegaram até a data prometida (meta: ${pct(META)})`, abaixo > 0],
    [String(D.meta.propostas_aumentar), "regiões em que o site deveria mostrar um prazo maior", false],
    [brl(D.meta.impacto_total), "de custo com atraso que as propostas evitam no período", false],
  ];
  $("#numeros").replaceChildren(...numeros.map(([v, t, al]) => h("div", {}, h("dt", {}, t), h("dd", { class: al ? "alerta" : "" }, v))));

  /* ---------- mapa em pixels da abertura ---------- */
  function pontoNoPoligono(x, y, anel) {
    let dentro = false;
    for (let i = 0, j = anel.length - 1; i < anel.length; j = i++) {
      const [xi, yi] = anel[i], [xj, yj] = anel[j];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) dentro = !dentro;
    }
    return dentro;
  }
  function ufEm(x, y) {
    for (const f of U.features)
      for (const poly of f.geometry.coordinates)
        if (pontoNoPoligono(x, y, poly[0])) return f.properties.uf;
    return null;
  }
  (function pixels() {
    const cv = $("#pixels"), tag = $("#pixels-tag");
    const lon0 = -74, lon1 = -33.5, lat0 = 5.5, lat1 = -34, passo = 0.62, tam = 7;
    const cols = Math.ceil((lon1 - lon0) / passo), lin = Math.ceil((lat0 - lat1) / passo);
    cv.width = cols * tam; cv.height = lin * tam;
    const ctx = cv.getContext("2d"), grade = [];
    for (let r = 0; r < lin; r++) for (let c = 0; c < cols; c++) {
      const uf = ufEm(lon0 + (c + 0.5) * passo, lat0 - (r + 0.5) * passo);
      if (uf) grade.push({ r, c, uf });
    }
    const valor = (uf) => (D.ufs[uf] ? D.ufs[uf].cumprimento : null);
    const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
    const claro = [163, 168, 236], branco = [255, 255, 255];
    function pinta(dest) {
      ctx.clearRect(0, 0, cv.width, cv.height);
      grade.forEach((p) => {
        const v = valor(p.uf);
        const t = v == null ? 0 : Math.max(0, Math.min(1, (v - 0.55) / (1 - 0.55)));
        const cor = mix(claro, branco, t);
        ctx.fillStyle = `rgb(${cor.join(",")})`;
        const ativo = dest === p.uf, m = ativo ? 0 : 1;
        ctx.globalAlpha = dest && !ativo ? 0.45 : 1;
        ctx.fillRect(p.c * tam + m, p.r * tam + m, tam - 2 * m, tam - 2 * m);
      });
      ctx.globalAlpha = 1;
    }
    pinta(null);
    cv.addEventListener("mousemove", (e) => {
      const b = cv.getBoundingClientRect(), esc = cv.width / b.width;
      const c = Math.floor(((e.clientX - b.left) * esc) / tam), r = Math.floor(((e.clientY - b.top) * esc) / tam);
      const p = grade.find((g) => g.c === c && g.r === r);
      if (!p) { tag.hidden = true; pinta(null); return; }
      pinta(p.uf);
      const v = valor(p.uf);
      tag.textContent = `${nomeUF(p.uf)}: ${v == null ? "sem dados" : pct(v) + " no prazo"}`;
      const pai = cv.parentElement.getBoundingClientRect();
      tag.style.left = e.clientX - pai.left + "px"; tag.style.top = e.clientY - pai.top + "px"; tag.hidden = false;
    });
    cv.addEventListener("mouseleave", () => { tag.hidden = true; pinta(null); });
  })();

  /* ---------- camadas do mapa ---------- */
  const impactoMax = Math.max(1, ...Object.values(D.ufs).map((u) => Math.abs(u.impacto)));
  const camadas = {
    cumprimento: {
      titulo: "Entregas no prazo",
      valor(uf) {
        const r = estado.transp === "todas" ? D.ufs[uf] : D.uf_transportadora[uf + "|" + estado.transp];
        return r && r.envios >= (estado.transp === "todas" ? 1 : 10) ? r.cumprimento : null;
      },
      cor(v) { return v == null ? NEUTRO : v < 0.6 ? RAMPA[0] : v < 0.75 ? RAMPA[1] : v < 0.85 ? RAMPA[2] : v < META ? RAMPA[3] : RAMPA[4]; },
      classes: [["menos de 60%", RAMPA[0]], ["60 a 75%", RAMPA[1]], ["75 a 85%", RAMPA[2]], ["85 a 92%", RAMPA[3]], ["92% ou mais (meta)", RAMPA[4]]],
      texto: (v) => pct(v) + " no prazo",
    },
    acao: {
      titulo: "Regiões com prazo a aumentar",
      valor(uf) { const u = D.ufs[uf]; return u && u.prefixos ? u.aumentar / u.prefixos : null; },
      cor(v) { return v == null ? NEUTRO : v === 0 ? "#e3e4ef" : v < 0.25 ? LARANJA[0] : v < 0.5 ? LARANJA[1] : v < 0.75 ? LARANJA[2] : LARANJA[4]; },
      classes: [["nenhuma", "#e3e4ef"], ["menos de 25%", LARANJA[0]], ["25 a 50%", LARANJA[1]], ["50 a 75%", LARANJA[2]], ["75% ou mais", LARANJA[4]]],
      texto: (v) => pct(v) + " dos prefixos precisam de mais prazo",
    },
    impacto: {
      titulo: "Custo de atraso evitável",
      valor(uf) { const u = D.ufs[uf]; return u ? u.impacto : null; },
      cor(v) { if (v == null) return NEUTRO; const t = v / impactoMax; return t <= 0.02 ? "#e3e4ef" : t < 0.1 ? RAMPA[0] : t < 0.25 ? RAMPA[1] : t < 0.5 ? RAMPA[2] : t < 0.75 ? RAMPA[3] : RAMPA[4]; },
      classes: [["quase nenhum", "#e3e4ef"], ["até 10% do maior", RAMPA[0]], ["10 a 25%", RAMPA[1]], ["25 a 50%", RAMPA[2]], ["50 a 75%", RAMPA[3]], ["maior", RAMPA[4]]],
      texto: (v) => brl(v) + " evitáveis no período",
    },
  };

  const mapa = L.map($("#mapa-leaflet"), { zoomSnap: 0.25, minZoom: 3, maxZoom: 7, scrollWheelZoom: false, attributionControl: false, zoomControl: true });
  const camadaGeo = L.geoJSON(U, {
    style: estiloUF,
    onEachFeature(f, layer) {
      const uf = f.properties.uf;
      layer.on({
        mouseover() { if (estado.uf !== uf) layer.setStyle({ weight: 2, color: "#15184f" }); layer.bringToFront(); },
        mouseout() { camadaGeo.resetStyle(layer); },
        click() { selecionarUF(uf); },
      });
      layer.bindTooltip(() => `${nomeUF(uf)}: ${valorTexto(uf)}`, { sticky: true, className: "dica" });
    },
  }).addTo(mapa);
  mapa.fitBounds(camadaGeo.getBounds(), { padding: [8, 8] });

  /* pontos reais: cada prefixo de CEP na cidade de referência (coordenadas dos municípios do IBGE) */
  const pontos = L.layerGroup().addTo(mapa);
  function corPonto(p) {
    const v = p.cumprimento_hoje;
    return v == null ? NEUTRO : v < 0.6 ? "#e8631e" : v < 0.75 ? "#ee8a52" : v < META ? "#f3ae85" : "#1f2599";
  }
  D.prefixos.filter((p) => p.latitude != null).forEach((p) => {
    L.circleMarker([p.latitude, p.longitude], { radius: Math.max(4, Math.min(11, Math.sqrt(p.envios_medidos) / 2)), color: "#fff", weight: 1.5,
      fillColor: corPonto(p), fillOpacity: 0.95 })
      .bindTooltip(`${p.cep3} ${p.cidade_referencia}/${p.uf}: ${p.cumprimento_hoje == null ? "sem dados" : Math.round(p.cumprimento_hoje * 100) + "% no prazo"} · ${p.transportadora}`, { className: "dica" })
      .on("click", () => { selecionarUF(p.uf); irParaProposta(p.cep3); })
      .addTo(pontos);
  });

  function valorTexto(uf) {
    const c = camadas[estado.camada], v = c.valor(uf);
    return v == null ? "sem dados" : c.texto(v);
  }
  function estiloUF(f) {
    const uf = f.properties.uf, c = camadas[estado.camada], sel = estado.uf === uf;
    return { fillColor: c.cor(c.valor(uf)), fillOpacity: 0.92, color: sel ? "#15184f" : "#ffffff", weight: sel ? 3 : 1 };
  }
  function pintar() {
    camadaGeo.setStyle(estiloUF);
    const c = camadas[estado.camada];
    $("#legenda").replaceChildren(
      h("div", { class: "legenda-titulo" }, c.titulo + (estado.camada === "cumprimento" && estado.transp !== "todas" ? ` (${estado.transp})` : "")),
      ...c.classes.map(([t, cor]) => h("div", { class: "legenda-linha" }, h("i", { style: `background:${cor}` }), t)),
      h("div", { class: "legenda-linha" }, h("i", { style: `background:${NEUTRO}` }), "sem dados"),
      h("div", { class: "legenda-titulo", style: "margin-top:8px" }, "Pontos: prefixos de CEP"),
      h("div", { class: "legenda-linha" }, h("i", { style: "background:#e8631e;border-radius:50%" }), "abaixo de 60% no prazo"),
      h("div", { class: "legenda-linha" }, h("i", { style: "background:#f3ae85;border-radius:50%" }), "60% até a meta"),
      h("div", { class: "legenda-linha" }, h("i", { style: "background:#1f2599;border-radius:50%" }), "cumpre a meta (92%)")
    );
  }

  function segmentado(id, aoMudar) {
    const raiz = $(id);
    raiz.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      raiz.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      aoMudar(b.dataset.v);
    });
  }
  segmentado("#ctl-camada", (v) => { estado.camada = v; $("#ctl-transp").disabled = v !== "cumprimento"; pintar(); });
  const selT = $("#ctl-transp");
  selT.append(h("option", { value: "todas" }, "Todas"), ...D.transportadoras.map((t) => h("option", { value: t.transportadora }, t.transportadora)));
  selT.addEventListener("change", () => { estado.transp = selT.value; pintar(); });

  /* ---------- ficha do estado ---------- */
  function fichaVazia() {
    $("#ficha").replaceChildren(h("p", { class: "ficha-vazia" }, "Clique num estado do mapa para ver o desempenho dele e os prefixos de CEP que o agente quer corrigir."));
  }
  function selecionarUF(uf) {
    estado.uf = uf; camadaGeo.setStyle(estiloUF);
    const u = D.ufs[uf], linhas = D.prefixos.filter((p) => p.uf === uf);
    if (!u) {
      $("#ficha").replaceChildren(h("h3", {}, nomeUF(uf)), h("p", { class: "ficha-sub" }, uf), h("p", { class: "ficha-vazia" }, "Sem prefixos medidos neste estado."));
      return;
    }
    const mudar = u.aumentar + u.reduzir;
    $("#ficha").replaceChildren(
      h("h3", {}, nomeUF(uf)),
      h("p", { class: "ficha-sub" }, `${uf} · ${u.prefixos} prefixos de CEP`),
      h("div", { class: "ficha-grade" },
        h("div", {}, h("b", { class: u.cumprimento < META ? "alerta" : "" }, pct(u.cumprimento)), h("span", {}, "no prazo hoje")),
        h("div", {}, h("b", {}, num(u.envios)), h("span", {}, "pedidos medidos")),
        h("div", {}, h("b", {}, String(mudar)), h("span", {}, "prefixos com proposta"))),
      h("table", { class: "mini" },
        h("thead", {}, h("tr", {}, ...["Prefixo", "Transportadora", "Prazo", "No prazo"].map((t) => h("th", {}, t)))),
        h("tbody", {}, linhas.sort((a, b) => (a.cumprimento_hoje ?? 2) - (b.cumprimento_hoje ?? 2)).slice(0, 14).map((p) =>
          h("tr", { onclick: () => irParaProposta(p.cep3) },
            h("td", {}, `${p.cep3} ${p.cidade_referencia}`), h("td", {}, p.transportadora),
            h("td", {}, p.prazo_site_hoje === p.prazo_proposto ? dias(p.prazo_site_hoje) : `${dias(p.prazo_site_hoje)} → ${dias(p.prazo_proposto)}`),
            h("td", {}, pct(p.cumprimento_hoje)))))));
    $("#ctl-uf").value = uf; estado.filtroUF = uf; montarTabela();
  }

  /* ---------- transportadoras ---------- */
  (function transportadoras() {
    const ordem = [...D.transportadoras].sort((a, b) => b.cumprimento - a.cumprimento);
    $("#barras").replaceChildren(...ordem.map((t) =>
      h("div", { class: "barra-linha" },
        h("div", { class: "barra-nome" }, t.transportadora),
        h("div", { class: "barra-trilho", role: "img", "aria-label": `${t.transportadora}: ${pct(t.cumprimento)} no prazo` },
          h("div", { class: "barra-preench" + (t.cumprimento < META ? " abaixo" : ""), style: `width:${t.cumprimento * 100}%` }),
          h("div", { class: "barra-meta", style: `left:${META * 100}%` })),
        h("div", { class: "barra-valor" }, h("b", {}, pct(t.cumprimento)), `${num(t.envios)} pedidos`))));
    $("#cards-transp").replaceChildren(...ordem.map((t) =>
      h("div", { class: "card" }, h("h3", {}, t.transportadora),
        h("p", {}, "9 em cada 10 entregas chegam em até ", h("b", {}, dias(t.prazo_real_p92) + " dias úteis"), ". Metade chega em ", h("b", {}, dias(t.prazo_real_p50)), "."),
        h("p", {}, "Quando atrasa, atrasa em média ", h("b", {}, dias(t.atraso_medio_du == null ? null : Math.round(t.atraso_medio_du * 10) / 10) + " dias úteis"), ". ",
          num(t.extravios), " extravios e ", num(t.devolucoes), " devoluções."))));
  })();

  /* ---------- propostas ---------- */
  const selUF = $("#ctl-uf");
  selUF.append(h("option", { value: "todos" }, "Todos"), ...[...new Set(D.prefixos.map((p) => p.uf))].sort().map((u) => h("option", { value: u }, `${u} · ${nomeUF(u)}`)));
  selUF.addEventListener("change", () => { estado.filtroUF = selUF.value; estado.limite = 40; montarTabela(); });
  segmentado("#ctl-acao", (v) => { estado.acao = v; estado.limite = 40; montarTabela(); });

  const ROT_ACAO = { aumentar: "Aumentar prazo", reduzir: "Reduzir prazo", manter: "Manter", "sem evidência": "Poucos dados" };
  const CLASSE_ACAO = { aumentar: "aumentar", reduzir: "reduzir", manter: "manter", "sem evidência": "sem" };

  function filtradas() {
    return D.prefixos.filter((p) => (estado.acao === "todas" || p.acao === estado.acao) && (estado.filtroUF === "todos" || p.uf === estado.filtroUF));
  }
  function montarTabela() {
    const todas = filtradas(), vis = todas.slice(0, estado.limite);
    $("#tabela tbody").replaceChildren(...vis.map((p) => {
      const conc = p.prazo_conc_mediana == null ? "–" : `${dias(p.prazo_conc_mediana)} dias`;
      return h("tr", { class: p.cep3 === estado.selCep ? "sel" : "", "data-cep": p.cep3, onclick: () => selecionarProposta(p.cep3) },
        h("td", {}, h("b", {}, p.cep3), " ", p.cidade_referencia, h("br"), h("small", {}, `${p.uf} · ${p.localidade}`)),
        h("td", {}, p.transportadora),
        h("td", {}, p.prazo_site_hoje === p.prazo_proposto ? `${dias(p.prazo_site_hoje)} dias` : [`${dias(p.prazo_site_hoje)}`, h("span", { class: "seta" }, "→"), h("b", {}, `${dias(p.prazo_proposto)} dias`)]),
        h("td", {}, p.cumprimento_hoje == null ? "–" : p.cumprimento_hoje === p.cumprimento_proposto ? pct(p.cumprimento_hoje) : [pct(p.cumprimento_hoje), h("span", { class: "seta" }, "→"), h("b", {}, pct(p.cumprimento_proposto))]),
        h("td", {}, conc, h("br"), h("small", {}, p.prazo_site_hoje === p.prazo_proposto ? p.posicao_hoje : `${p.posicao_hoje} → ${p.posicao_proposta}`)),
        h("td", { class: p.impacto_custo_atraso_rs > 0 ? "positivo" : p.impacto_custo_atraso_rs < 0 ? "negativo" : "" }, p.impacto_custo_atraso_rs ? (p.impacto_custo_atraso_rs > 0 ? "+" : "") + brl(p.impacto_custo_atraso_rs) : "–"),
        h("td", {}, h("span", { class: "chip " + CLASSE_ACAO[p.acao] }, ROT_ACAO[p.acao]), estado.status[p.cep3] ? h("div", {}, h("small", {}, estado.status[p.cep3])) : null));
    }));
    const mais = todas.length > vis.length;
    const nota = $("#tabela-nota");
    nota.replaceChildren(`${todas.length} prefixos. `, mais ? h("button", { class: "botao botao-cobalto", onclick: () => { estado.limite += 40; montarTabela(); } }, h("span", { class: "botao-icone" }, "+"), "Mostrar mais") : "");
    if (!estado.selCep && todas.length) estado.selCep = todas[0].cep3;
    mensagem();
  }
  function selecionarProposta(cep) { estado.selCep = cep; montarTabela(); }
  function irParaProposta(cep) {
    estado.selCep = cep; estado.limite = 200; montarTabela();
    const tr = document.querySelector(`#tabela tr[data-cep="${cep}"]`);
    if (tr) tr.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function mensagem() {
    const p = D.prefixos.find((x) => x.cep3 === estado.selCep);
    const caixa = $("#msg");
    if (!p) { caixa.replaceChildren(h("p", { class: "ficha-vazia" }, "Escolha uma região na tabela para ver a mensagem que o agente mandaria.")); return; }
    const topo = h("div", { class: "msg-topo" }, h("span", { class: "msg-avatar", "aria-hidden": "true" }), "Agente de logística · mensagem para a Marina Duarte (gerente) · demonstração");
    let texto, acoes = null;
    if (p.acao === "aumentar" || p.acao === "reduzir") {
      const conc = p.prazo_conc_mediana == null ? "" : ` Os concorrentes mostram cerca de ${dias(p.prazo_conc_mediana)} dias.`;
      texto = p.acao === "aumentar"
        ? `A ${p.transportadora} entrega só ${pct(p.cumprimento_hoje)} dos pedidos no prazo na região ${p.cep3} (${p.cidade_referencia}/${p.uf}). O site promete ${dias(p.prazo_site_hoje)} dias, mas 9 em cada 10 entregas levam até ${dias(p.prazo_proposto)}. Sugiro mostrar ${dias(p.prazo_proposto)} dias.${conc} Isso evita cerca de ${brl(p.impacto_custo_atraso_rs)} de custo com atraso no período. Você aprova?`
        : `Na região ${p.cep3} (${p.cidade_referencia}/${p.uf}) a ${p.transportadora} entrega mais rápido do que o site promete: 9 em cada 10 chegam em até ${dias(p.prazo_proposto)} dias e o site mostra ${dias(p.prazo_site_hoje)}. Sugiro mostrar ${dias(p.prazo_proposto)} para ficar mais competitivo.${conc} Você aprova?`;
      acoes = h("div", { class: "msg-acoes" },
        h("a", { class: "botao botao-cheio", href: "login.html" }, h("span", { class: "botao-icone", "aria-hidden": "true" }, "→"), "Decidir na tela da gerente"));
    } else if (p.acao === "manter") {
      texto = `Região ${p.cep3} (${p.cidade_referencia}/${p.uf}): o prazo de ${dias(p.prazo_site_hoje)} dias está certo para a ${p.transportadora}. Nada a aprovar.`;
    } else {
      texto = `Região ${p.cep3} (${p.cidade_referencia}/${p.uf}): só ${p.envios_medidos} pedidos medidos com a ${p.transportadora}. É pouco para propor mudança; continuo medindo.`;
    }
    caixa.replaceChildren(topo, h("p", { class: "msg-texto" }, texto), acoes, h("p", { class: "msg-estado", id: "msg-estado" }, estado.status[p.cep3] || ""));
  }
  /* o que a Marina aprovou (servidor) passa a valer aqui; sem servidor, o painel segue estático */
  function aplicarAprovados() {
    fetch("/api/prazos-vigentes").then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (!d) return;
      estado.status = {};
      for (const [cep, v] of Object.entries(d.prazos || {})) estado.status[cep] = `Aprovado pela ${v.por}: site mostra ${dias(v.prazo)} dias (era ${dias(v.prazo_anterior)}). Vale só na demonstração.`;
      montarTabela();
    }).catch(() => {});
  }
  aplicarAprovados();
  try { const f = new EventSource("/api/eventos?usuario=marina"); f.onmessage = (m) => { try { if (JSON.parse(m.data).tipo === "prazos_mudaram") aplicarAprovados(); } catch (e) {} }; } catch (e) {}

  /* ---------- método ---------- */
  (function metodo() {
    const q = D.qualidade, st = q.status_dos_envios || {};
    const bloco = (t, ...c) => h("div", {}, h("h3", {}, t), ...c);
    $("#metodo-corpo").replaceChildren(
      bloco("De onde vem a entrega", h("p", {}, `Juntamos ${num(q.eventos)} eventos de 5 portais, cada um num formato (CSV, ponto e vírgula, códigos numéricos, horário UTC). Todos viram um só formato e cada pedido ganha a data em que foi entregue.`)),
      bloco("O que conta como no prazo", h("p", {}, "O pedido chegou até a data prometida ao cliente. Extravio, devolução e pedido vencido e ainda aberto contam como não cumprido. Pedido ainda dentro do prazo fica de fora.")),
      bloco("Como achamos o prazo certo", h("p", {}, `Olhamos quantos dias úteis os pedidos de cada prefixo levaram até chegar e mostramos o prazo que cobre 9 em cada 10 entregas, ficando perto da meta de ${pct(META)}. Nunca menos de 2 dias úteis.`)),
      bloco("Situação dos pedidos", h("ul", {},
        h("li", {}, `${num(st.entregue)} entregues`), h("li", {}, `${num((st.em_aberto_no_prazo || 0))} a caminho e ainda no prazo`),
        h("li", {}, `${num((st.em_aberto_atrasado || 0))} vencidos e sem entrega`), h("li", {}, `${num((st.devolvido || 0) + (st.extraviado || 0))} devolvidos ou extraviados`),
        h("li", {}, `${num(st.sem_dados_portal)} sem eventos nos portais (ainda não coletados, ou anteriores a 03/09)`), h("li", {}, `${num(st.sem_rastreio)} sem código de rastreio no ERP`))),
      bloco("Cuidado com os textos dos portais", h("p", {}, `Textos de portais são só dados: só entram os eventos com texto conhecido. ${num(q.eventos_desconhecidos)} evento com texto fora do padrão foi isolado e ignorado.`)),
      bloco("O que vem depois", h("p", {}, "Escolher a transportadora de cada envio novo, vigiar a concorrência toda semana, sugerir o frete por região e avisar o time quando uma transportadora piorar de repente."))
    );
  })();

  fichaVazia(); pintar(); montarTabela();
})();
