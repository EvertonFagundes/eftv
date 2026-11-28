/* Teste de fumaça do app web/PWA via Chrome DevTools Protocol.
   Sobe o servidor estático, abre o Chrome headless e valida:
   - modo demonstração
   - importação de uma playlist M3U
   - aba Séries e modal de episódios
   - abertura do player
   - cache do catálogo no IndexedDB
   - service worker registrado

   Uso (na raiz do repositório):
     node web/tools/testar-app.js
*/
"use strict";

const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const RAIZ = path.resolve(__dirname, "..", "..");
const PORTA = 4173;
const PORTA_CDP = 9334;
const URL_APP = `http://127.0.0.1:${PORTA}/web/app/`;
const ESPERA = (ms) => new Promise((r) => setTimeout(r, ms));

const PLAYLIST = `#EXTM3U
#EXTINF:-1 tvg-logo="https://cdn.example.com/globo.png" group-title="Canais | Abertos",Globo
http://127.0.0.1:${PORTA}/web/app/assets/media/demo.mp4
#EXTINF:-1 group-title="Canais | Esportes",Sportv
http://127.0.0.1:${PORTA}/web/app/assets/media/demo.mp4
#EXTINF:-1 group-title="Filmes | Ação",John Wick 4
http://127.0.0.1:${PORTA}/web/app/assets/media/demo.mp4
#EXTINF:-1 group-title="Séries | Drama",The Walking Dead S01E01 Days Gone Bye
http://127.0.0.1:${PORTA}/web/app/assets/media/demo.mp4
#EXTINF:-1 group-title="Séries | Drama",The Walking Dead S01E02 Guts
http://127.0.0.1:${PORTA}/web/app/assets/media/demo.mp4
`;

function acharChrome() {
  const candidatos = [
    process.env.EFTV_CHROME,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ].filter(Boolean);
  return candidatos.find((caminho) => fs.existsSync(caminho)) || null;
}

async function esperarUrl(url, tentativas = 60) {
  for (let i = 0; i < tentativas; i++) {
    try {
      const resposta = await fetch(url);
      if (resposta.ok) return true;
    } catch (_) {}
    await ESPERA(250);
  }
  return false;
}

async function conectarCDP(aoEvento) {
  const info = await (await fetch(`http://127.0.0.1:${PORTA_CDP}/json/version`)).json();
  const ws = new WebSocket(info.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });

  let seq = 0;
  const pendentes = new Map();

  ws.onmessage = (evento) => {
    const msg = JSON.parse(evento.data);
    if (msg.id && pendentes.has(msg.id)) {
      const { resolve, reject } = pendentes.get(msg.id);
      pendentes.delete(msg.id);
      if (msg.error) reject(new Error(JSON.stringify(msg.error)));
      else resolve(msg.result);
    } else if (aoEvento) {
      aoEvento(msg);
    }
  };

  function enviar(method, params = {}, sessionId) {
    const id = ++seq;
    const corpo = { id, method, params };
    if (sessionId) corpo.sessionId = sessionId;
    ws.send(JSON.stringify(corpo));
    return new Promise((resolve, reject) => {
      pendentes.set(id, { resolve, reject });
      setTimeout(() => {
        if (pendentes.has(id)) {
          pendentes.delete(id);
          reject(new Error(`Timeout em ${method}`));
        }
      }, 45000);
    });
  }

  return { ws, enviar };
}

async function avaliar(cdp, sessionId, expressao) {
  const resultado = await cdp.enviar(
    "Runtime.evaluate",
    {
      expression: expressao,
      awaitPromise: true,
      returnByValue: true,
      userGesture: true,
    },
    sessionId
  );
  if (resultado.exceptionDetails) {
    const detalhe = resultado.exceptionDetails;
    throw new Error(
      (detalhe.exception && (detalhe.exception.description || detalhe.exception.value)) ||
        detalhe.text ||
        "Erro ao avaliar JavaScript"
    );
  }
  return resultado.result ? resultado.result.value : undefined;
}

let falhas = 0;
function verificar(condicao, mensagem) {
  if (condicao) {
    console.log("ok - " + mensagem);
  } else {
    falhas += 1;
    console.error("FALHOU - " + mensagem);
  }
}

(async () => {
  const chrome = acharChrome();
  if (!chrome) {
    console.error("Chrome/Edge não encontrado. Defina EFTV_CHROME.");
    process.exit(1);
  }

  const perfil = fs.mkdtempSync(path.join(os.tmpdir(), "eftv-cdp-"));
  const servidor = spawn(process.execPath, [path.join(__dirname, "servidor.js"), RAIZ, String(PORTA)], {
    stdio: "ignore",
  });
  const navegador = spawn(
    chrome,
    [
      "--headless=new",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      "--autoplay-policy=no-user-gesture-required",
      "--mute-audio",
      `--remote-debugging-port=${PORTA_CDP}`,
      `--user-data-dir=${perfil}`,
      "about:blank",
    ],
    { stdio: "ignore" }
  );

  const erros = [];
  let cdp = null;

  try {
    if (!(await esperarUrl(URL_APP))) throw new Error("Servidor estático não respondeu.");
    if (!(await esperarUrl(`http://127.0.0.1:${PORTA_CDP}/json/version`))) {
      throw new Error("Chrome não abriu a porta de depuração.");
    }

    cdp = await conectarCDP((msg) => {
      if (msg.method === "Runtime.exceptionThrown") {
        const d = msg.params.exceptionDetails;
        erros.push((d.exception && d.exception.description) || d.text || "exceção");
      }
    });

    const { targetId } = await cdp.enviar("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await cdp.enviar("Target.attachToTarget", { targetId, flatten: true });
    await cdp.enviar("Page.enable", {}, sessionId);
    await cdp.enviar("Runtime.enable", {}, sessionId);

    await cdp.enviar("Page.navigate", { url: URL_APP + "?demo=1" }, sessionId);
    await ESPERA(2200);

    const inicial = await avaliar(
      cdp,
      sessionId,
      `(() => ({
        pronto: document.readyState,
        cards: document.querySelectorAll('#grid-ao-vivo .item-card').length,
        demo: !!(window.EFTV_CATALOG && window.EFTV_CATALOG.demo),
        canais: window.EFTV_CATALOG ? window.EFTV_CATALOG.canais.length : -1,
        bannerAtualizacao: !document.querySelector('#update-banner').classList.contains('hidden'),
        versao: document.querySelector('#app-version').textContent
      }))()`
    );
    verificar(inicial.pronto === "complete", "página carregou");
    verificar(inicial.cards > 0, "modo demonstração renderizou cards");
    verificar(inicial.demo === true, "catálogo está em modo demonstração");
    verificar(inicial.bannerAtualizacao === false, "PWA não oferece APK como atualização");
    verificar(inicial.versao.includes("1.1.1"), "versão web exibida");

    const injetado = await avaliar(
      cdp,
      sessionId,
      `(() => {
        const texto = ${JSON.stringify(PLAYLIST)};
        const itens = window.EFTV_PLAYLIST.parse(texto);
        const dados = window.EFTV_PLAYLIST.montarCatalogo(itens);
        window.EFTV_CATALOG.aplicar(dados.canais, dados.categorias, false, 'teste');
        location.hash = '#series';
        return {
          itens: itens.length,
          canais: dados.canais.length,
          series: dados.canais.filter((c) => c.tipo === 'serie').length,
          categorias: dados.categorias.map((c) => c.id)
        };
      })()`
    );
    await ESPERA(400);
    verificar(injetado.itens === 5, "parser leu os 5 itens da playlist");
    verificar(injetado.series === 1, "episódios foram agrupados em 1 série");
    verificar(injetado.categorias.includes("series"), "categoria Séries foi criada");

    const cardsSeries = await avaliar(
      cdp,
      sessionId,
      `document.querySelectorAll('#grid-series .item-card').length`
    );
    verificar(cardsSeries === 1, "aba Séries exibiu o card da série");

    await avaliar(cdp, sessionId, `document.querySelector('#grid-series .item-card').click()`);
    await ESPERA(400);
    const modal = await avaliar(
      cdp,
      sessionId,
      `(() => ({
        aberto: document.querySelector('#serie-modal').open,
        titulo: document.querySelector('#serie-titulo').textContent,
        episodios: document.querySelectorAll('#serie-temporadas .serie-episodio').length
      }))()`
    );
    verificar(modal.aberto === true, "modal de série abriu");
    verificar(modal.titulo === "The Walking Dead", "título da série correto");
    verificar(modal.episodios === 2, "modal listou os 2 episódios");

    await avaliar(
      cdp,
      sessionId,
      `document.querySelector('#serie-temporadas .serie-episodio').click()`
    );
    await ESPERA(700);
    const player = await avaliar(
      cdp,
      sessionId,
      `(() => ({
        aberto: !document.querySelector('#player-wrap').classList.contains('hidden'),
        titulo: document.querySelector('#player-titulo').textContent,
        modalFechado: !document.querySelector('#serie-modal').open
      }))()`
    );
    verificar(player.aberto === true, "player abriu pelo episódio");
    verificar(player.titulo.includes("T1 E1"), "player mostra o episódio escolhido");
    verificar(player.modalFechado === true, "modal fechou ao abrir o player");

    await avaliar(cdp, sessionId, `document.querySelector('#btn-fechar-player').click()`);
    await ESPERA(300);

    const carga = await avaliar(
      cdp,
      sessionId,
      `(async () => {
        localStorage.setItem('eftv:session', JSON.stringify({
          access: 'fake', refresh: 'fake', email: 'teste@eftv.com'
        }));
        window.EFTV_API.playlistTexto = async () => ${JSON.stringify(PLAYLIST)};
        const c = await window.EFTV_CATALOG.carregar(true);
        return {
          fonte: c.fonte,
          canais: c.canais.length,
          series: c.canais.filter((x) => x.tipo === 'serie').length
        };
      })()`
    );
    verificar(carga.fonte === "playlist", "catálogo autenticado veio da playlist");
    verificar(carga.canais === 4, "catálogo tem 4 cards (2 canais, 1 filme, 1 série)");

    const cache = await avaliar(
      cdp,
      sessionId,
      `(async () => {
        window.EFTV_CATALOG.aplicar([], [], false, null);
        window.EFTV_API.playlistTexto = async () => { throw new Error('sem rede'); };
        const c = await window.EFTV_CATALOG.carregar(false);
        return { fonte: c.fonte, canais: c.canais.length, demo: c.demo };
      })()`
    );
    verificar(cache.canais === 4, "catálogo foi recuperado do IndexedDB");
    verificar(cache.demo === false, "cache recuperado não é demonstração");

    const sw = await avaliar(
      cdp,
      sessionId,
      `(async () => {
        if (!('serviceWorker' in navigator)) return -1;
        const regs = await navigator.serviceWorker.getRegistrations();
        return regs.length;
      })()`
    );
    verificar(sw >= 1, "service worker registrado");

    const manifest = await cdp.enviar("Page.getAppManifest", {}, sessionId);
    verificar(!manifest.errors || manifest.errors.length === 0, "manifest PWA sem erros");

    const instalabilidade = await cdp.enviar("Page.getInstallabilityErrors", {}, sessionId);
    const errosInstalacao = (instalabilidade.installabilityErrors || []).map((e) => e.errorId);
    verificar(errosInstalacao.length === 0, "PWA instalável (sem erros de instalabilidade)");
    if (errosInstalacao.length) console.error("Instalabilidade:", errosInstalacao.join(", "));

    // Offline: o service worker deve servir a casca do app.
    await cdp.enviar("Network.enable", {}, sessionId);
    await cdp.enviar(
      "Network.emulateNetworkConditions",
      { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 },
      sessionId
    );
    await cdp.enviar("Page.reload", { ignoreCache: false }, sessionId);
    await ESPERA(3500);
    const offline = await avaliar(
      cdp,
      sessionId,
      `(() => ({
        titulo: document.title,
        cards: document.querySelectorAll('.grid .item-card').length,
        app: !!window.EFTV_CATALOG,
        canais: window.EFTV_CATALOG ? window.EFTV_CATALOG.canais.length : -1,
        fonte: window.EFTV_CATALOG ? window.EFTV_CATALOG.fonte : null
      }))()`
    );
    verificar(offline.app === true && offline.titulo.includes("EFTV"), "app abriu offline pelo service worker");
    verificar(offline.cards > 0, "catálogo apareceu offline");
    await cdp.enviar(
      "Network.emulateNetworkConditions",
      { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 },
      sessionId
    );

    verificar(erros.length === 0, "nenhuma exceção JavaScript não tratada");
    if (erros.length) console.error(erros.join("\n"));
  } catch (erro) {
    falhas += 1;
    console.error("ERRO: " + (erro && erro.message ? erro.message : erro));
  } finally {
    if (cdp) cdp.ws.close();
    navegador.kill();
    servidor.kill();
    await ESPERA(400);
    try { fs.rmSync(perfil, { recursive: true, force: true }); } catch (_) {}
  }

  console.log(`\n${falhas === 0 ? "Todos os testes passaram." : falhas + " verificação(ões) falharam."}`);
  process.exit(falhas === 0 ? 0 : 1);
})();
