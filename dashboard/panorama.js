/* Panorama: o resumo do painel (data.js) nas telas do analista e da gerente. Sem Leaflet: mapa em SVG puro. */
(function () {
  "use strict";
  const D = window.DADOS; if (!D) return;
  const NS = "http://www.w3.org/2000/svg";
  const pct = (x) => (x * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "%";
  const pct0 = (x) => Math.round(x * 100) + "%";
  const meta = D.meta.meta_cumprimento;
  function h(tag, attrs, ...filhos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) { if (k === "class") el.className = v; else if (v != null && v !== false) el.setAttribute(k, v); }
    filhos.flat().forEach((f) => { if (f != null) el.append(f.nodeType ? f : document.createTextNode(String(f))); });
    return el;
  }
  const brl0 = (x) => "R$ " + Number(x).toLocaleString("pt-BR", { maximumFractionDigits: 0 });

  function kpis(papel) {
    const m = D.meta, abaixo = m.cumprimento_geral < meta;
    const lista = [
      h("div", { class: "pan-kpi" }, h("b", { class: abaixo ? "ruim" : "" }, pct(m.cumprimento_geral)), h("span", {}, `entregas no prazo (meta ${pct0(meta)})`)),
      h("div", { class: "pan-kpi" }, h("b", {}, m.prefixos_abaixo_da_meta), h("span", {}, "regiões abaixo da meta")),
      h("div", { class: "pan-kpi" }, h("b", {}, m.propostas_aumentar + m.propostas_reduzir), h("span", {}, `ajustes de prazo sugeridos (${m.propostas_aumentar} aumentar, ${m.propostas_reduzir} reduzir)`)),
    ];
    lista.push(papel === "gerente"
      ? h("div", { class: "pan-kpi" }, h("b", {}, brl0(m.impacto_total)), h("span", {}, "de custo com atraso que dá para evitar"))
      : h("div", { class: "pan-kpi" }, h("b", {}, m.envios_medidos.toLocaleString("pt-BR")), h("span", {}, "envios medidos nos últimos meses")));
    return h("div", { class: "pan-kpis" }, ...lista);
  }

  function transportadoras() {
    const ts = [...D.transportadoras].sort((a, b) => b.cumprimento - a.cumprimento);
    return h("section", { class: "pan-cartao pan-transp" }, h("h3", {}, "Transportadoras"), h("small", {}, "entregas dentro do prazo prometido"),
      ...ts.map((t) => h("div", { class: "barra-lin", title: `${t.envios.toLocaleString("pt-BR")} envios · atraso médio ${String(t.atraso_medio_du).replace(".", ",")} dias úteis` },
        h("span", {}, t.transportadora),
        h("div", { class: "trilho" }, h("i", { class: t.cumprimento < meta ? "ruim" : "", style: `width:${t.cumprimento * 100}%` }), h("u", { style: `left:${meta * 100}%` })),
        h("b", {}, pct0(t.cumprimento)))),
      h("p", { class: "legenda-meta" }, h("u"), `meta de ${pct0(meta)}`));
  }

  /* mapa do Brasil por estado: laranja = longe da meta, azul = acima */
  function cor(c) {
    if (c == null) return "#e6e7f2";
    const d = c - meta;   // de -0.25 a +0.08
    if (d >= 0) return "#323ac2";
    if (d > -0.04) return "#c6c9ef";
    if (d > -0.08) return "#f9d5bd";
    if (d > -0.14) return "#f3ae85";
    if (d > -0.2) return "#ee8a52";
    return "#e8631e";
  }
  function mapa() {
    const cartao = h("section", { class: "pan-cartao pan-mapa" }, h("h3", {}, "Brasil por estado"), h("small", {}, "cor = quanto falta (ou sobra) para a meta"));
    if (!window.UFS) return cartao;
    const K = Math.cos(15 * Math.PI / 180);
    const proj = ([lon, lat]) => [(lon + 74) * K, (6 - lat)];
    const caminhos = []; let maxX = 0, maxY = 0;
    window.UFS.features.forEach((f) => {
      const polis = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
      const d = polis.map((p) => p.map((anel) => "M" + anel.map((pt) => { const [x, y] = proj(pt); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); return x.toFixed(2) + "," + y.toFixed(2); }).join("L") + "Z").join("")).join("");
      caminhos.push([f.properties, d]);
    });
    const svg = document.createElementNS(NS, "svg"); svg.setAttribute("viewBox", `0 0 ${maxX.toFixed(1)} ${maxY.toFixed(1)}`); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Cumprimento do prazo por estado");
    caminhos.forEach(([p, d]) => {
      const u = D.ufs[p.uf], el = document.createElementNS(NS, "path");
      el.setAttribute("d", d); el.setAttribute("fill", cor(u && u.cumprimento));
      const t = document.createElementNS(NS, "title"); t.textContent = u ? `${p.nome}: ${pct0(u.cumprimento)} no prazo · ${u.envios.toLocaleString("pt-BR")} envios` : `${p.nome}: sem envios medidos`;
      el.append(t); svg.append(el);
    });
    cartao.append(svg, h("p", { class: "pan-escala" }, "longe da meta", h("i"), "acima da meta"));
    return cartao;
  }

  function piores() {
    const ps = D.prefixos.filter((p) => p.envios_medidos >= 30).sort((a, b) => a.cumprimento_hoje - b.cumprimento_hoje).slice(0, 5);
    return h("section", { class: "pan-cartao pan-piores" }, h("h3", {}, "Onde mais atrasa"), h("small", {}, "regiões com menos entregas no prazo"),
      ...ps.map((p) => h("div", { class: "pior-lin" },
        h("b", {}, `${p.cidade_referencia}/${p.uf}`), h("span", { class: "pct" }, pct0(p.cumprimento_hoje)),
        h("small", {}, `${p.transportadora} · site mostra ${String(p.prazo_site_hoje).replace(".", ",")} dias úteis`))));
  }

  window.Agiliza = window.Agiliza || {};
  window.Agiliza.panorama = function (el, papel) { el.classList.add("panorama"); el.replaceChildren(kpis(papel), transportadoras(), mapa(), piores()); };
})();
