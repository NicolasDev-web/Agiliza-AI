/* Piloto automático: o que o agente decidiu sozinho, em segundo plano.
 * Aparece na tela do analista e da gerente (#piloto). Só a gerente liga e pausa (o servidor confere o papel). */
(function () {
  "use strict";
  const raiz = document.getElementById("piloto"); if (!raiz) return;
  function h(tag, attrs, ...filhos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") el.className = v; else if (k.startsWith("on")) el.addEventListener(k.slice(2), v); else if (v != null && v !== false) el.setAttribute(k, v);
    }
    filhos.flat().forEach((f) => { if (f != null) el.append(f.nodeType ? f : document.createTextNode(String(f))); });
    return el;
  }
  const brl = (x) => "R$ " + Number(x || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const ICONE = { rota: "🚚", incidente: "⚠️", proposta: "📨", priorizacao: "🧭", lembrete: "⏰", modo: "⏯️" };
  const ROTULO = { rota: "rotas", incidente: "incidente", proposta: "proposta à Marina", priorizacao: "priorização", lembrete: "lembrete", modo: "piloto" };
  let papel = null, dados = null, ocupado = false, novas = new Set(), alvo = null, pedindo = false;

  /* relógio do próximo ciclo: conta segundo a segundo no navegador, sem esperar o servidor */
  const hora = (t) => new Date(t).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  function faltam() { return alvo ? Math.max(0, Math.round((alvo - Date.now()) / 1000)) : null; }
  function textoRelogio() {
    if (!dados) return "";
    if (dados.rodando) return "trabalhando agora…";
    if (dados.modo !== "ligado") return "pausado" + (dados.ultimo ? ` · último ciclo às ${dados.ultimo}` : "");
    const s = faltam();
    if (s == null) return "ligado";
    if (s === 0) return "começando o ciclo…";
    return `próximo ciclo em ${s} s · às ${hora(alvo)}` + (dados.ultimo ? ` · último às ${dados.ultimo}` : "");
  }
  function tique() {
    const el = raiz.querySelector(".piloto-relogio"); if (el) el.textContent = textoRelogio();
    const barra = raiz.querySelector(".piloto-barra i"), s = faltam();
    if (barra && dados && s != null) barra.style.width = (dados.modo === "ligado" ? Math.min(100, (1 - s / dados.intervalo_s) * 100) : 0) + "%";
    if (s === 0 && !pedindo) { pedindo = true; setTimeout(() => { pedindo = false; carregar(); }, 1500); }   // o ciclo virou: busca o resultado
  }

  async function api(caminho, metodo, corpo) {
    const r = await fetch(caminho, { method: metodo || "GET", headers: { "Content-Type": "application/json" }, body: corpo ? JSON.stringify(corpo) : undefined });
    const d = await r.json(); if (!r.ok) throw new Error(d.erro || "erro"); return d;
  }
  async function carregar() {
    try {
      const antes = new Set((dados && dados.decisoes || []).map((d) => d.id));
      dados = await api("/api/autonomo");
      alvo = dados.proximo_em_s != null ? Date.now() + dados.proximo_em_s * 1000 : null;
      if (antes.size) dados.decisoes.forEach((d) => { if (!antes.has(d.id)) novas.add(d.id); });
      desenhar();
      if (dados.rodando && !pedindo) { pedindo = true; setTimeout(() => { pedindo = false; carregar(); }, 500); }   // acompanha o ciclo de perto
    } catch (e) { /* servidor fora: tenta de novo no próximo tique */ }
  }

  function desenhar() {
    if (!dados) return;
    const ligado = dados.modo === "ligado", r = dados.resumo || {};
    const botoes = [];
    if (papel === "gerente") {
      botoes.push(h("button", { type: "button", class: "botao botao-cobalto pequeno", disabled: ocupado ? "" : null,
        onclick: () => acao(() => api("/api/autonomo/modo", "POST", { modo: ligado ? "pausado" : "ligado" })) }, ligado ? "Pausar piloto" : "Ligar piloto"));
    }
    botoes.push(h("button", { type: "button", class: "botao botao-cobalto pequeno", disabled: ocupado || dados.rodando ? "" : null,
      title: "Adianta o próximo ciclo", onclick: () => acao(() => api("/api/autonomo/rodar", "POST", {})) }, "Rodar agora"));

    const kpi = (valor, rotulo) => h("div", { class: "piloto-kpi" }, h("b", {}, valor), h("span", {}, rotulo));
    raiz.classList.toggle("analisando", !!dados.rodando);
    const passos = dados.passos || [];
    const MARCA = { feito: "✓", agora: "●", espera: "○" };
    const blocoPassos = passos.length ? h("div", { class: "piloto-passos" + (dados.rodando ? " ao-vivo" : "") },
      h("p", { class: "piloto-passos-titulo" }, dados.rodando ? "Analisando agora…" : `O que ele analisou no último ciclo${dados.ultimo ? " (" + dados.ultimo + ")" : ""}`),
      h("ol", {}, ...passos.map((p) => h("li", { class: p.situacao },
        h("span", { class: "piloto-marca", "aria-hidden": "true" }, MARCA[p.situacao] || "○"),
        h("span", {}, p.rotulo, p.resumo ? h("small", {}, " · " + p.resumo) : p.situacao === "agora" ? h("small", {}, " · trabalhando…") : null))))) : null;
    const lista = (dados.decisoes || []).filter((d) => d.tipo !== "modo" || papel === "gerente").slice(0, 12);
    raiz.replaceChildren(
      h("div", { class: "piloto-topo" },
        h("div", {},
          h("h2", {}, "Piloto automático ", h("span", { class: "piloto-estado " + (dados.rodando ? "rodando" : ligado ? "ligado" : "pausado") }, h("i"),
            h("span", { class: "piloto-relogio", "aria-live": "off" }, textoRelogio()))),
          h("div", { class: "piloto-barra", title: `um ciclo a cada ${dados.intervalo_s} s` }, h("i")),
          h("p", { class: "piloto-sub" }, papel === "gerente"
            ? "O agente age sozinho dentro da política: troca rotas (até 40% por estado/dia), abre incidente com transportadora e escolhe o que trazer para você. Prazo do site continua sendo decisão sua."
            : "O agente trabalha sozinho no seu lugar: troca rotas dos envios novos, abre incidente com transportadora e leva à Marina as propostas que valem a pena.")),
        h("div", { class: "piloto-botoes" }, ...botoes)),
      blocoPassos,
      h("div", { class: "piloto-kpis" },
        kpi(String(r.rotas_trocadas || 0), `rotas trocadas sozinho · ${brl(r.economia_rotas)}`),
        kpi(String(r.incidentes || 0), "incidentes abertos com transportadoras"),
        kpi(String(r.propostas || 0), `propostas levadas à Marina · ${brl(r.impacto_propostas)} em jogo`),
        kpi(String(r.lembretes || 0), "lembretes de pedido parado")),
      lista.length
        ? h("ol", { class: "piloto-diario" }, ...lista.map((d) => h("li", { class: novas.has(d.id) ? "nova" : "" },
            h("span", { class: "piloto-ico", "aria-hidden": "true" }, ICONE[d.tipo] || "•"),
            h("div", {}, h("p", {}, h("b", {}, d.titulo), h("small", {}, ` · ${ROTULO[d.tipo] || d.tipo} · ${String(d.quando).slice(11, 16)}`)), h("p", { class: "piloto-txt" }, d.texto)))))
        : h("p", { class: "vazio" }, ligado ? "O primeiro ciclo roda em instantes. Tudo que o agente decidir sozinho aparece aqui, com o porquê." : "Piloto pausado: o agente só age quando alguém pede no chat."),
      dados.erro ? h("p", { class: "piloto-erro" }, "O último ciclo teve um problema; o próximo tenta de novo.") : null);
    setTimeout(() => novas.clear(), 4000);
    tique();
  }

  async function acao(fn) {
    ocupado = true; desenhar();
    try { await fn(); } catch (e) { alert(e.message); }
    ocupado = false; await carregar();
  }

  document.addEventListener("agiliza:usuario", (ev) => {
    papel = ev.detail.papel === "gerente" ? "gerente" : "analista";
    carregar();
    setInterval(carregar, 4000);   // leve: só o diário e o relógio do próximo ciclo
    setInterval(tique, 1000);      // a contagem anda a cada segundo
  }, { once: true });
})();
