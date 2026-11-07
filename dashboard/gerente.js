/* Tela da gerente: fila de aprovação, placar, histórico e alertas financeiros, tudo em tempo real. */
(async function () {
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
  const brl = (x) => (x == null ? "–" : "R$ " + Number(x).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const brl0 = (x) => (x == null ? "–" : "R$ " + Number(x).toLocaleString("pt-BR", { maximumFractionDigits: 0 }));
  const dias = (x) => (x == null ? "–" : `${Number(x).toLocaleString("pt-BR")} dias úteis`);
  const quando = (s) => (s || "").slice(5, 16).replace("-", "/").replace(" ", " · ");
  const NOMES = { lucas: "Lucas Ferreira", marina: "Marina Duarte" };
  const TIPOS = { prazo_exibido: "Prazo exibido no site", frete_cobrado: "Frete cobrado", roteamento_padrao: "Transportadora padrão da região", outro: "Pedido do agente" };

  const eu = await window.Agiliza.exigir("gerente");
  let novos = new Set();

  async function api(caminho, metodo, corpo) {
    const r = await fetch(caminho, { method: metodo || "GET", headers: { "Content-Type": "application/json" }, body: corpo ? JSON.stringify(corpo) : undefined });
    const d = await r.json(); if (!r.ok) throw new Error(d.erro || "erro"); return d;
  }

  /* ---------- placar ---------- */
  function placar(p) {
    if (!p) return;
    const usado = p.aprovadas / p.limite * 100;
    $("#placar").replaceChildren(
      h("div", { class: p.pendentes ? "alerta" : "" }, h("b", {}, p.pendentes), h("span", {}, p.pendentes === 1 ? "pedido esperando você" : "pedidos esperando você")),
      h("div", {}, h("b", {}, `${p.restantes} de ${p.limite}`), h("span", {}, "aprovações ainda disponíveis"), h("div", { class: "barra-limite" }, h("i", { style: `width:${usado}%` }))),
      h("div", {}, h("b", {}, brl0(p.economia_prazos + p.economia_rotas)), h("span", {}, "economia estimada até agora")));
  }

  /* ---------- pedido ---------- */
  function cartaoPedido(a) {
    const ajustavel = a.valor_proposto != null;
    const coment = h("textarea", { placeholder: "Motivo (opcional): o agente conta ao Lucas com as suas palavras", "aria-label": "Comentário" });
    const valor = h("input", { type: "number", min: "2", step: "1", value: a.valor_proposto ?? "", "aria-label": "Novo valor em dias úteis" });
    const caixaAjuste = h("div", { class: "pedido-botoes", hidden: true }, h("span", { class: "rotulo-ctl" }, "Novo prazo"), valor, h("span", {}, "dias úteis"),
      h("button", { type: "button", class: "botao botao-cheio pequeno", onclick: () => decidir("ajustar") }, "Aprovar com este valor"));
    const erro = h("p", { class: "pedido-erro", hidden: true });

    async function decidir(decisao) {
      erro.hidden = true;
      try {
        const r = await api(`/api/aprovacoes/${a.id}/decidir`, "POST", { decisao, valor: decisao === "ajustar" ? valor.value : undefined, comentario: coment.value });
        placar(r.placar); carregar();
      } catch (e) { erro.textContent = e.message; erro.hidden = false; }
    }
    const btn = (t, ico, cls, fn, desligado) => h("button", { type: "button", class: "botao " + cls, onclick: fn, disabled: desligado ? "" : false },
      h("span", { class: "botao-icone", "aria-hidden": "true" }, ico), t);

    const valores = a.valor_proposto != null
      ? h("div", { class: "pedido-valores" }, h("small", {}, "hoje"), h("b", {}, a.valor_atual != null ? dias(a.valor_atual) : "–"), h("span", { class: "seta" }, "→"), h("small", {}, "proposto"), h("b", {}, dias(a.valor_proposto)))
      : null;
    return h("article", { class: "pedido" + (novos.has(a.id) ? " novo" : "") },
      h("div", { class: "pedido-topo" }, h("span", {}, TIPOS[a.tipo] || a.tipo), h("span", {}, `pedido pelo ${NOMES[a.solicitante] || a.solicitante} · ${quando(a.criado_em)}`)),
      h("p", { class: "pedido-resumo" }, a.resumo), valores,
      a.impacto_reais != null ? h("p", { class: "pedido-impacto" }, `Evita cerca de ${brl0(a.impacto_reais)} de custo com atraso`) : null,
      a.evidencia ? h("details", { class: "pedido-evid" }, h("summary", {}, "Ver os números"), a.evidencia) : h("p", { class: "pedido-evid" }, "Sem evidência anexada: peça ao agente antes de aprovar."),
      coment, caixaAjuste,
      h("div", { class: "pedido-botoes" },
        btn("Aprovar", "✓", "botao-cheio", () => decidir("aprovar")),
        btn("Ajustar", "~", "botao-cobalto", () => { caixaAjuste.hidden = !caixaAjuste.hidden; valor.focus(); }, !ajustavel),
        btn("Recusar", "×", "botao-cobalto", () => decidir("recusar"))),
      erro);
  }

  function lista(aprovacoes) {
    const pend = aprovacoes.filter((a) => a.situacao === "pendente");
    const feitas = aprovacoes.filter((a) => a.situacao !== "pendente");
    $("#n-pendentes").replaceChildren(pend.length ? h("em", {}, pend.length) : "");
    $("#fila").replaceChildren(...(pend.length ? pend.map(cartaoPedido) : [h("p", { class: "vazio" }, "Nada esperando. Quando o agente propuser uma mudança, ela aparece aqui na hora.")]));
    $("#n-decididos").textContent = feitas.length ? String(feitas.length) : "";
    const NOME = { aprovada: "aprovada", ajustada: "aprovada com ajuste", recusada: "recusada" };
    $("#historico").replaceChildren(...(feitas.length ? feitas.map((a) => h("div", { class: "historico-lin" },
      h("div", {}, h("span", { class: "etiqueta " + a.situacao }, NOME[a.situacao]), " ", a.resumo),
      h("small", {}, `${quando(a.decidido_em)} · ${a.valor_final != null ? "valor final " + dias(a.valor_final) + " · " : ""}pedido por ${NOMES[a.solicitante] || a.solicitante}${a.comentario ? " · “" + a.comentario + "”" : ""}`)))
      : [h("p", { class: "vazio" }, "As decisões vão ficando registradas aqui.")]));
    novos = new Set();
  }

  /* ---------- financeiro ---------- */
  function cartaoAlerta(a) {
    const d = a.detalhe || {};
    const resumo = h("summary", {}, h("b", {}, a.titulo), h("span", { class: "quando" }, " · " + quando(a.quando)));
    const corpo = [h("p", {}, a.texto)];
    if (d.trocas && d.trocas.length) {
      const linhas = d.trocas.slice(0, 8).map((t) => {
        const df = t.frete_para - t.frete_de;
        return h("tr", {}, h("td", {}, t.destino), h("td", {}, `${t.de} → ${t.para}`), h("td", { class: df > 0 ? "pos" : "neg" }, (df > 0 ? "+" : "") + brl(df)), h("td", { class: "neg" }, brl(t.economia_estimada)));
      });
      corpo.push(h("table", { class: "mini-tabela" }, h("thead", {}, h("tr", {}, ...["Destino", "Rota", "Frete", "Saldo"].map((x) => h("th", {}, x)))), h("tbody", {}, linhas)));
      if (d.trocas.length > 8) corpo.push(h("p", { class: "quando" }, `e mais ${d.trocas.length - 8} envios`));
    }
    if (!a.ciente) corpo.push(h("div", { class: "pedido-botoes" }, h("button", { type: "button", class: "botao botao-cobalto pequeno", onclick: async () => { const r = await api(`/api/alertas/${a.id}/ciente`, "POST", {}); placar(r.placar); carregarAlertas(); } }, "Ciente")));
    return h("details", { class: "alerta-fin" + (a.ciente ? " ciente" : "") }, resumo, ...corpo);
  }
  async function carregarAlertas() {
    const r = await api("/api/alertas"); placar(r.placar);
    const sem = r.alertas.filter((a) => !a.ciente).length;
    $("#n-alertas").replaceChildren(sem ? h("em", {}, sem) : "");
    $("#alertas").replaceChildren(...(r.alertas.length ? r.alertas.map(cartaoAlerta) : [h("p", { class: "vazio" }, "Nenhuma troca de rota ainda.")]));
  }
  async function carregar() {
    const r = await api("/api/aprovacoes"); lista(r.aprovacoes); placar(r.placar); carregarAlertas();
  }

  /* ---------- WhatsApp: a Marina conecta lendo o QR code ---------- */
  let ultimoZap = "";
  async function carregarZap() {
    let z;
    try { z = await api("/api/whatsapp"); } catch (e) { return; }
    const chave = z.estado + (z.qr || "").slice(-24) + z.numero;
    if (chave === ultimoZap) return; ultimoZap = chave;
    const ROT = { conectado: "conectado", aguardando_qr: "aguardando leitura", iniciando: "iniciando…", desconectado: "desconectado", sem_ponte: "desligado" };
    $("#zap-estado").replaceChildren(h("em", { class: "zap-pilula " + z.estado }, ROT[z.estado] || z.estado));
    const corpo = $("#zap-corpo");
    if (z.estado === "conectado") {
      corpo.replaceChildren(h("p", { class: "zap-ok" }, `Conectado${z.numero ? " no número +" + z.numero : ""}. As decisões saem daqui para ${z.destino || "o analista"}.`),
        h("button", { type: "button", class: "botao botao-cobalto pequeno", onclick: async () => { if (confirm("Desconectar o WhatsApp deste sistema?")) { await api("/api/whatsapp/sair", "POST", {}).catch(() => {}); ultimoZap = ""; carregarZap(); } } }, "Desconectar"));
    } else if (z.estado === "aguardando_qr" && z.qr) {
      corpo.replaceChildren(h("div", { class: "zap-qr" }, h("img", { src: z.qr, alt: "QR code do WhatsApp", width: 220, height: 220 }),
        h("ol", {}, h("li", {}, "Abra o WhatsApp no celular"), h("li", {}, "Toque em Aparelhos conectados"), h("li", {}, "Conectar um aparelho e aponte para este código"))),
        h("p", { class: "zap-nota" }, `Depois de ler, as respostas aos pedidos vão para ${z.destino || "o analista"} sozinhas. Uso de teste: WhatsApp Web não é a via oficial.`));
    } else if (z.estado === "sem_ponte") {
      corpo.replaceChildren(h("p", { class: "vazio" }, z.ponte_instalada ? "A ponte do WhatsApp não está respondendo. Reinicie o servidor." : "Ponte do WhatsApp não instalada. No terminal: cd whatsapp && npm install, e reinicie o servidor."),
        h("p", { class: "zap-nota" }, "Enquanto isso, o Lucas vê a mensagem como prévia na tela dele."));
    } else corpo.replaceChildren(h("p", { class: "vazio" }, "Preparando o código de leitura…"));
  }

  /* ---------- tempo real ---------- */
  function conectar() {
    const fonte = new EventSource("/api/eventos");
    const marca = (ok, t) => { $("#conexao").className = "ag-modo " + (ok ? "ia" : "simulado"); $("#conexao span").textContent = t; };
    fonte.onopen = () => marca(true, "ao vivo: os pedidos chegam sozinhos");
    fonte.onerror = () => marca(false, "reconectando…");
    fonte.onmessage = (m) => {
      let e; try { e = JSON.parse(m.data); } catch (x) { return; }
      if (e.tipo === "pedido_novo") { novos.add(e.aprovacao.id); carregar(); document.title = "(1) Gerente de logística · Transporte"; setTimeout(() => (document.title = "Gerente de logística · Transporte"), 4000); }
      else if (["alerta", "decisao_registrada", "reiniciado"].includes(e.tipo)) carregar();
    };
  }

  $("#reiniciar").addEventListener("click", async () => { if (confirm("Zerar pedidos, decisões, prazos aprovados e alertas?")) { await api("/api/demo/reiniciar", "POST", {}); carregar(); } });
  await carregar().catch((e) => { $("#fila").replaceChildren(h("p", { class: "vazio" }, "Não consegui falar com o servidor: " + e.message)); });
  conectar();
  if (window.Agiliza.panorama) window.Agiliza.panorama($("#panorama"), "gerente");
  carregarZap(); setInterval(carregarZap, 3000);
})();
