/* Quem está usando. Hackathon: sem senha. O usuário fica na ABA (sessionStorage), para abrir
   o analista e a gerente lado a lado. O servidor lê o papel dele da base, não deste arquivo. */
(function () {
  "use strict";
  const CHAVE = "transporte.usuario";
  const CASAS = { analista_logistica: "agente.html", gerente: "gerente.html" };
  const ROTULO = { analista_logistica: "Analista", gerente: "Gerente" };

  function ler() { try { return JSON.parse(sessionStorage.getItem(CHAVE) || "null"); } catch (e) { return null; } }
  function guardar(u) {
    try { sessionStorage.setItem(CHAVE, JSON.stringify(u)); localStorage.setItem(CHAVE + ".ultimo", u.id); } catch (e) { /* sem storage: segue na URL */ }
  }
  async function entrar(id) {
    const r = await fetch("/api/usuarios"); const d = await r.json();
    const u = d.usuarios.find((x) => x.id === id);
    if (!u) throw new Error("usuário desconhecido");
    guardar(u); return u;
  }

  /* ?como=marina entra direto (útil para abrir a demonstração em duas abas) */
  const como = new URLSearchParams(location.search).get("como");
  const pronto = como ? entrar(como).catch(() => null) : Promise.resolve(ler());

  function selo(u) {
    const el = document.createElement("div"); el.className = "usuario-selo";
    el.innerHTML = '<span class="usuario-papel"></span><span class="usuario-nome"></span><a class="usuario-troca" href="login.html">trocar</a>';
    el.querySelector(".usuario-papel").textContent = ROTULO[u.papel] || u.papel;
    el.querySelector(".usuario-nome").textContent = u.nome;
    el.classList.add("papel-" + u.papel);
    return el;
  }

  /* exige o papel da página; quem está no lugar errado volta para a sua tela */
  window.Transporte = {
    pronto,
    ler,
    CASAS,
    async exigir(papel) {
      const u = await pronto;
      if (!u) { location.replace("login.html"); return new Promise(() => {}); }
      if (papel && u.papel !== papel) { location.replace(CASAS[u.papel]); return new Promise(() => {}); }
      const nav = document.querySelector(".nav");
      if (nav) nav.append(selo(u));
      return u;
    },
    entrar,
    selo,
  };
})();
