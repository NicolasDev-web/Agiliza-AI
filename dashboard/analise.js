/* Visão geral com filtros + barra de perguntas no pé da tela.
 * A pergunta vira um filtro pequeno e fechado (o servidor interpreta); os gráficos e os textos são desenhados aqui
 * com os dados do painel (data.js). Os mesmos filtros podem ser mexidos à mão. Sem token de IA, tudo funciona. */
(function () {
  "use strict";
  const D = window.DADOS; if (!D) return;
  const meta = D.meta.meta_cumprimento;
  const $ = (s, r) => (r || document).querySelector(s);
  function h(tag, attrs, ...filhos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") el.className = v; else if (k.startsWith("on")) el.addEventListener(k.slice(2), v); else if (v != null && v !== false) el.setAttribute(k, v);
    }
    filhos.flat().forEach((f) => { if (f != null) el.append(f.nodeType ? f : document.createTextNode(String(f))); });
    return el;
  }
  const pct = (x) => Math.round(x * 100) + "%";
  const n0 = (x) => Math.round(x).toLocaleString("pt-BR");
  const brl0 = (x) => "R$ " + Number(x).toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  const NOME_UF = {}; ((window.UFS && window.UFS.features) || []).forEach((f) => { NOME_UF[f.properties.uf] = f.properties.nome; });
  const UF_LISTA = Object.keys(D.ufs).sort();
  const TRANSP = D.transportadoras.map((t) => t.transportadora).sort();
  const PADRAO = { grupo: "transportadora", uf: null, transportadora: null, metrica: "atraso", ordem: "pior", top: null };
  const METRICAS = { atraso: "Entregas fora do prazo", cumprimento: "Entregas no prazo", impacto: "Custo de atraso evitável", envios: "Envios medidos" };
  const GRUPOS = { transportadora: "Transportadoras", uf: "Estados", regiao: "Regiões" };
  let filtro = { ...PADRAO }, papel = "analista", raiz = null;

  /* ---------- números ---------- */
  function linhas(f) {
    const mapa = new Map();
    const pegar = (k, nome, sub) => { if (!mapa.has(k)) mapa.set(k, { nome, sub, envios: 0, no_prazo: 0, impacto: 0, abaixo: 0 }); return mapa.get(k); };
    if (f.grupo === "regiao") {
      D.prefixos.filter((p) => (!f.uf || p.uf === f.uf) && (!f.transportadora || p.transportadora === f.transportadora)).forEach((p) => {
        const r = pegar(p.cep3, `${p.cidade_referencia}/${p.uf}`, p.transportadora);
        r.envios = p.envios_medidos; r.no_prazo = (p.cumprimento_hoje || 0) * p.envios_medidos; r.impacto = p.impacto_custo_atraso_rs || 0;
      });
    } else {
      Object.entries(D.uf_transportadora).forEach(([chave, v]) => {
        const [uf, t] = chave.split("|");
        if ((f.uf && uf !== f.uf) || (f.transportadora && t !== f.transportadora)) return;
        const r = f.grupo === "uf" ? pegar(uf, NOME_UF[uf] || uf, "") : pegar(t, t, "");
        r.envios += v.envios; r.no_prazo += v.cumprimento * v.envios;
      });
      D.prefixos.filter((p) => (!f.uf || p.uf === f.uf) && (!f.transportadora || p.transportadora === f.transportadora)).forEach((p) => {
        const k = f.grupo === "uf" ? p.uf : p.transportadora; if (mapa.has(k)) mapa.get(k).impacto += p.impacto_custo_atraso_rs || 0;
      });
    }
    const pequena = f.grupo === "regiao" && (f.metrica === "atraso" || f.metrica === "cumprimento");
    return [...mapa.values()].filter((r) => r.envios > 0 && !(pequena && r.envios < 30)).map((r) => ({ ...r, cump: r.no_prazo / r.envios }));
  }
  const valor = (r, m) => (m === "atraso" ? 1 - r.cump : m === "cumprimento" ? r.cump : m === "impacto" ? r.impacto : r.envios);
  function ordenar(rs, f) {
    const maiorPrimeiro = f.metrica === "cumprimento" ? f.ordem === "melhor" : f.ordem === "pior";
    return rs.sort((a, b) => (maiorPrimeiro ? valor(b, f.metrica) - valor(a, f.metrica) : valor(a, f.metrica) - valor(b, f.metrica)));
  }

  /* ---------- texto ---------- */
  function frase(rs, f) {
    const lugar = f.uf ? `${EM[f.uf] || "em"} ${NOME_UF[f.uf] || f.uf}` : f.transportadora ? `na ${f.transportadora}` : "no Brasil";
    if (!rs.length) return `Não há envios medidos suficientes ${lugar}.`;
    const l = rs[0], pior = f.ordem === "pior";
    switch (f.metrica) {
      case "atraso": return `${cap(lugar)}, ${l.nome} ${pior ? "é quem mais atrasa" : "é quem menos atrasa"}: ${pct(1 - l.cump)} das entregas fora do prazo (meta: no máximo ${pct(1 - meta)}).`;
      case "cumprimento": return `${cap(lugar)}, ${l.nome} ${pior ? "é quem menos cumpre o prazo" : "é quem mais cumpre o prazo"}: ${pct(l.cump)} no prazo (meta ${pct(meta)}).`;
      case "impacto": return `${cap(lugar)}, ${l.nome} ${pior ? "concentra o maior" : "tem o menor"} custo de atraso evitável: ${brl0(l.impacto)}.`;
      default: return `${cap(lugar)}, ${l.nome} ${pior ? "tem mais" : "tem menos"} envios medidos: ${n0(l.envios)}.`;
    }
  }
  const EM = { AC: "no", AP: "no", AM: "no", CE: "no", DF: "no", ES: "no", MA: "no", MT: "no", MS: "no", PA: "no", PR: "no", PI: "no", RJ: "no", RN: "no", RS: "no", TO: "no", BA: "na", PB: "na" };
  const cap = (t) => t.charAt(0).toUpperCase() + t.slice(1);

  /* ---------- desenho ---------- */
  function render() {
    if (!raiz) return;
    const f = filtro, todas = ordenar(linhas(f), f), top = f.top || (f.grupo === "regiao" ? 8 : 12), rs = todas.slice(0, top);
    const env = todas.reduce((a, r) => a + r.envios, 0), no = todas.reduce((a, r) => a + r.no_prazo, 0), imp = todas.reduce((a, r) => a + r.impacto, 0);
    const abaixo = todas.filter((r) => r.cump < meta).length;
    const maxv = Math.max(...rs.map((r) => valor(r, f.metrica)), 1e-9), escalaPct = f.metrica === "atraso" || f.metrica === "cumprimento";
    const fmt = (r) => f.metrica === "atraso" ? pct(1 - r.cump) : f.metrica === "cumprimento" ? pct(r.cump) : f.metrica === "impacto" ? brl0(r.impacto) : n0(r.envios);
    const sel = (id, opcoes, atual, rotulo, mudou) => h("label", { class: "filtro" }, h("span", {}, rotulo),
      h("select", { id, onchange: (e) => mudou(e.target.value) }, ...opcoes.map(([v, t]) => h("option", { value: v ?? "", selected: (atual ?? "") === (v ?? "") ? "" : null }, t))));
    const set = (k) => (v) => { filtro = { ...filtro, [k]: k === "top" ? (v ? +v : null) : (v || null) }; if (k === "grupo" || k === "metrica") filtro[k] = v; render(); };
    const maisBom = f.metrica === "cumprimento" ? ["pior", "Menor cumprimento primeiro"] : ["pior", f.metrica === "atraso" ? "Mais atrasa primeiro" : "Maior primeiro"];
    const melhor = f.metrica === "cumprimento" ? ["melhor", "Maior cumprimento primeiro"] : ["melhor", f.metrica === "atraso" ? "Menos atrasa primeiro" : "Menor primeiro"];

    raiz.replaceChildren(
      h("div", { class: "filtros" },
        sel("f-grupo", Object.entries(GRUPOS), f.grupo, "Mostrar por", set("grupo")),
        sel("f-uf", [[null, "Brasil todo"], ...UF_LISTA.map((u) => [u, NOME_UF[u] || u])], f.uf, "Estado", set("uf")),
        sel("f-transp", [[null, "Todas"], ...TRANSP.map((t) => [t, t])], f.transportadora, "Transportadora", set("transportadora")),
        sel("f-metrica", Object.entries(METRICAS), f.metrica, "O que medir", set("metrica")),
        sel("f-ordem", [maisBom, melhor], f.ordem, "Ordem", set("ordem")),
        sel("f-top", [[null, "Padrão"], ["3", "3"], ["5", "5"], ["10", "10"], ["20", "20"]], f.top ? String(f.top) : null, "Quantos", set("top")),
        h("button", { type: "button", class: "botao botao-cobalto pequeno", onclick: () => { filtro = { ...PADRAO }; render(); } }, "Limpar")),
      h("p", { class: "analise-frase" }, frase(rs, f)),
      h("div", { class: "pan-kpis" },
        h("div", { class: "pan-kpi" }, h("b", { class: env && no / env < meta ? "ruim" : "" }, env ? pct(no / env) : "–"), h("span", {}, `entregas no prazo (meta ${pct(meta)})`)),
        h("div", { class: "pan-kpi" }, h("b", {}, n0(env)), h("span", {}, "envios medidos")),
        h("div", { class: "pan-kpi" }, h("b", {}, `${abaixo} de ${todas.length}`), h("span", {}, `${GRUPOS[f.grupo].toLowerCase()} abaixo da meta`)),
        h("div", { class: "pan-kpi" }, h("b", {}, brl0(imp)), h("span", {}, "de custo com atraso que dá para evitar"))),
      h("div", { class: "pan-cartao analise-grafico" }, h("h3", {}, `${GRUPOS[f.grupo]} · ${METRICAS[f.metrica].toLowerCase()}`),
        h("small", {}, f.grupo === "regiao" && (f.metrica === "atraso" || f.metrica === "cumprimento") ? "só regiões com 30 envios medidos ou mais" : `${rs.length} de ${todas.length}`),
        ...(rs.length ? rs.map((r) => h("div", { class: "barra-lin analise-lin", title: `${n0(r.envios)} envios · ${pct(r.cump)} no prazo` },
          h("span", {}, r.nome, r.sub ? h("small", {}, r.sub) : null),
          h("div", { class: "trilho" }, h("i", { class: r.cump < meta ? "ruim" : "", style: `width:${Math.max(2, (escalaPct ? valor(r, f.metrica) : valor(r, f.metrica) / maxv) * 100)}%` }),
            f.metrica === "cumprimento" ? h("u", { style: `left:${meta * 100}%` }) : f.metrica === "atraso" ? h("u", { style: `left:${(1 - meta) * 100}%` }) : null),
          h("b", {}, fmt(r)))) : [h("p", { class: "vazio" }, "Nada para mostrar com esses filtros.")]),
        f.metrica === "cumprimento" || f.metrica === "atraso" ? h("p", { class: "legenda-meta" }, h("u"), "meta") : null));
  }

  function aplicar(novo, texto) {
    filtro = { ...PADRAO, ...novo }; if (raiz) { const d = $("#visao"); if (d && !d.open) d.open = true; render(); (d || raiz).scrollIntoView({ behavior: "smooth", block: "start" }); }
    return resumo(filtro);
  }
  function resumo(f) {
    return [GRUPOS[f.grupo].toLowerCase(), f.uf ? NOME_UF[f.uf] || f.uf : null, f.transportadora, METRICAS[f.metrica].toLowerCase(),
      f.metrica === "cumprimento" ? (f.ordem === "pior" ? "menos cumprem primeiro" : "mais cumprem primeiro") : (f.ordem === "pior" ? "maiores primeiro" : "menores primeiro"), f.top ? "top " + f.top : null].filter(Boolean).join(" · ");
  }

  /* ---------- a barra de perguntas ---------- */
  function barra() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const campo = h("input", { id: "barra-campo", placeholder: "Pergunte aos gráficos: “transportadoras do Pará, das que mais atrasam”", autocomplete: "off", "aria-label": "Pergunta para os gráficos" });
    const chip = h("p", { class: "barra-chip", hidden: true, role: "status" });
    const mic = h("button", { type: "button", class: "barra-mic", "aria-label": "Falar a pergunta", title: "Falar a pergunta", hidden: !SR });
    const ok = h("button", { type: "submit", class: "barra-ok", "aria-label": "Mostrar" }, "↑");
    async function perguntar(texto, alternativas) {
      texto = (texto || "").trim(); if (!texto) return;
      chip.hidden = false; chip.textContent = "entendendo…";
      try {
        const r = await fetch(`/api/analise?pergunta=${encodeURIComponent(texto)}${alternativas && alternativas.length ? "&alt=" + encodeURIComponent(alternativas.join("||")) : ""}`);
        const d = await r.json(); if (!r.ok) throw new Error(d.erro || "erro");
        chip.textContent = "mostrando: " + aplicar(d.filtro) + (d.corrigida && d.corrigida !== texto ? `  ·  entendi: “${d.corrigida}”` : "");
        campo.value = "";
      } catch (e) { chip.textContent = "Não consegui interpretar agora. Use os filtros acima."; }
    }
    if (SR) {
      let rec = null;
      mic.addEventListener("click", () => {
        if (rec) { rec.stop(); return; }
        rec = new SR(); rec.lang = "pt-BR"; rec.interimResults = true; rec.maxAlternatives = 3; let final = "", alts = [];
        rec.onresult = (ev) => { let parcial = ""; final = ""; alts = []; for (const r of ev.results) { if (r.isFinal) { final += r[0].transcript; for (let i = 1; i < r.length; i++) alts.push(r[i].transcript); } else parcial += r[0].transcript; } campo.value = (final + " " + parcial).trim(); };
        rec.onend = () => { mic.classList.remove("ligado"); rec = null; if ((final || campo.value).trim()) perguntar(final || campo.value, alts); };
        rec.onerror = () => { mic.classList.remove("ligado"); rec = null; };
        mic.classList.add("ligado"); rec.start();
      });
    }
    const form = h("form", { class: "barra-form", onsubmit: (e) => { e.preventDefault(); perguntar(campo.value); } }, campo, mic, ok);
    document.body.append(h("div", { class: "barra-analise" }, chip, form));
    window.Agiliza.perguntarAosGraficos = perguntar;
  }

  window.Agiliza = window.Agiliza || {};
  window.Agiliza.analise = {
    montar(el, p) { raiz = el; papel = p; el.classList.add("analise"); render(); },
    aplicar, filtro: () => ({ ...filtro }), linhas: (f) => ordenar(linhas(f), f),
  };
  document.addEventListener("agiliza:usuario", barra, { once: true });
})();
