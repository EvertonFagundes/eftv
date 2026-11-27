/* ============================================================
   EFTV — Captura de prints reais do app via Chrome DevTools Protocol.
   Requer o Chrome rodando com --remote-debugging-port=9333.

   Uso:
     node web/tools/capturar.js [saida]
   ============================================================ */

const fs = require("fs");
const path = require("path");

const PORTA_CDP = process.env.EFTV_CDP_PORT || 9333;
const BASE = `http://127.0.0.1:${PORTA_CDP}`;
const SAIDA = path.resolve(process.argv[2] || "web/app/assets/img/screens");
const URL_APP = process.env.EFTV_APP_URL || "http://localhost:4173/web/app/index.html";

const espera = (ms) => new Promise((r) => setTimeout(r, ms));

async function conectar() {
  const info = await (await fetch(`${BASE}/json/version`)).json();
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
      }, 30000);
    });
  }

  return { ws, enviar };
}

async function capturar(cdp, { nome, url, largura, altura, dpr = 2, esperaMs = 2600 }) {
  const { targetId } = await cdp.enviar("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp.enviar("Target.attachToTarget", { targetId, flatten: true });

  try {
    await cdp.enviar("Page.enable", {}, sessionId);
    await cdp.enviar(
      "Emulation.setDeviceMetricsOverride",
      { width: largura, height: altura, deviceScaleFactor: dpr, mobile: largura < 700 },
      sessionId
    );
    await cdp.enviar("Page.navigate", { url }, sessionId);
    await espera(esperaMs);

    const { data } = await cdp.enviar(
      "Page.captureScreenshot",
      { format: "png", fromSurface: true, captureBeyondViewport: false },
      sessionId
    );
    const arquivo = path.join(SAIDA, nome);
    fs.writeFileSync(arquivo, Buffer.from(data, "base64"));
    console.log(`OK  ${nome}  ${largura}x${altura}@${dpr}x  ${fs.statSync(arquivo).size} bytes`);
  } finally {
    await cdp.enviar("Target.closeTarget", { targetId }).catch(() => {});
  }
}

(async () => {
  fs.mkdirSync(SAIDA, { recursive: true });
  const cdp = await conectar();

  const telas = [
    { nome: "app-ao-vivo.png", url: `${URL_APP}#ao-vivo`, largura: 412, altura: 915, esperaMs: 2600 },
    { nome: "app-categorias.png", url: `${URL_APP}#categorias`, largura: 412, altura: 915, esperaMs: 2400 },
    { nome: "app-player.png", url: `${URL_APP}?demo=1&canal=globo`, largura: 412, altura: 915, esperaMs: 4200 },
    { nome: "app-player-paisagem.png", url: `${URL_APP}?demo=1&canal=globo`, largura: 915, altura: 412, dpr: 1, esperaMs: 4200 },
    { nome: "app-conta.png", url: `${URL_APP}?demo=1#conta`, largura: 412, altura: 915, esperaMs: 2600 },
    { nome: "app-ajustes.png", url: `${URL_APP}?demo=1#ajustes`, largura: 412, altura: 915, esperaMs: 2400 },
    { nome: "app-desktop.png", url: `${URL_APP}#ao-vivo`, largura: 1280, altura: 800, dpr: 1, esperaMs: 2800 },
  ];

  for (const tela of telas) {
    try {
      await capturar(cdp, tela);
    } catch (erro) {
      console.error(`FALHOU ${tela.nome}: ${erro.message}`);
    }
  }

  cdp.ws.close();
})().catch((erro) => {
  console.error("Erro na captura:", erro.message);
  process.exit(1);
});
