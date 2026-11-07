/* Sessão POR ABA. O cookie do navegador é um só para todo o endereço, então entrar como a Marina numa aba
   e como o Lucas em outra faria as duas abas virarem o último a entrar. Aqui cada aba guarda o seu próprio
   token (sessionStorage é por aba) e o manda em toda chamada ao servidor. O cookie continua como reserva. */
(function () {
  "use strict";
  const CHAVE = "agiliza.token";
  const ler = () => { try { return sessionStorage.getItem(CHAVE); } catch (e) { return null; } };
  const guardar = (t) => { try { sessionStorage.setItem(CHAVE, t); } catch (e) { /* sem storage: fica o cookie */ } };
  const apagar = () => { try { sessionStorage.removeItem(CHAVE); } catch (e) { /* sem storage */ } };
  const caminhoApi = (u) => {
    try { const x = new URL(u, location.href); return x.origin === location.origin && x.pathname.startsWith("/api/") ? x.pathname : null; } catch (e) { return null; }
  };

  const fetchOriginal = window.fetch.bind(window);
  window.fetch = async function (entrada, init) {
    const caminho = caminhoApi(typeof entrada === "string" ? entrada : entrada.url);
    const token = ler();
    if (caminho && token) {
      init = Object.assign({}, init);
      const h = new Headers(init.headers || (typeof entrada === "string" ? undefined : entrada.headers));
      h.set("X-Sessao", token);
      init.headers = h;
    }
    const r = await fetchOriginal(entrada, init);
    if (caminho === "/api/login" && r.ok) {
      try { const d = await r.clone().json(); if (d && d.token) guardar(d.token); } catch (e) { /* segue com o cookie */ }
    }
    if (caminho === "/api/sair") apagar();
    return r;
  };

  /* EventSource não aceita cabeçalho: o token vai na URL */
  const comSessao = (url) => {
    const token = ler();
    if (!token || !caminhoApi(url)) return url;
    const u = new URL(url, location.href); u.searchParams.set("s", token); return u.pathname + u.search;
  };
  const EventSourceOriginal = window.EventSource;
  if (EventSourceOriginal) {
    window.EventSource = function (url, cfg) { return new EventSourceOriginal(comSessao(url), cfg); };
    window.EventSource.prototype = EventSourceOriginal.prototype;
    ["CONNECTING", "OPEN", "CLOSED"].forEach((k) => { window.EventSource[k] = EventSourceOriginal[k]; });
  }

  window.Agiliza = Object.assign(window.Agiliza || {}, { comSessao, temSessaoNaAba: () => !!ler() });
})();
