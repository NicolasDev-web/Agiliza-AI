/* Sessão do usuário (cookie HttpOnly no servidor) e peças comuns a todas as telas do Agiliza AI. */
(function () {
  "use strict";
  const CASAS = { analista_logistica: "analista.html", gerente: "gerente.html" };
  const ROTULO = { analista_logistica: "Analista", gerente: "Gerente" };

  async function eu() {
    try { const r = await fetch("/api/eu"); return r.ok ? (await r.json()).usuario : null; } catch (e) { return null; }
  }
  async function sair() {
    try { await fetch("/api/sair", { method: "POST", body: "{}" }); } catch (e) { /* segue para o login */ }
    location.href = "login.html";
  }
  function selo(u) {
    const el = document.createElement("div"); el.className = "usuario-selo papel-" + u.papel;
    const papel = document.createElement("span"); papel.className = "usuario-papel"; papel.textContent = ROTULO[u.papel] || u.papel;
    const nome = document.createElement("span"); nome.className = "usuario-nome"; nome.textContent = u.nome;
    const b = document.createElement("button"); b.type = "button"; b.className = "usuario-troca"; b.textContent = "sair"; b.addEventListener("click", sair);
    el.append(papel, nome, b); return el;
  }

  window.Agiliza = {
    CASAS,
    eu,
    sair,
    /* exige login (e o papel da página); quem está no lugar errado volta para a sua tela */
    async exigir(papel) {
      const u = await eu();
      if (!u) { location.replace("login.html"); return new Promise(() => {}); }
      if (papel && u.papel !== papel) { location.replace(CASAS[u.papel]); return new Promise(() => {}); }
      const nav = document.querySelector(".nav"); if (nav) nav.append(selo(u));
      document.dispatchEvent(new CustomEvent("agiliza:usuario", { detail: u }));
      return u;
    },
  };
})();
