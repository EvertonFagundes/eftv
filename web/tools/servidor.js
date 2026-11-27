/* Servidor estático mínimo para testar o EFTV localmente.
   Uso: node web/tools/servidor.js [pasta-raiz] [porta]
   Ex.: node web/tools/servidor.js . 4173
*/
const http = require("http");
const fs = require("fs");
const path = require("path");

const raiz = path.resolve(process.argv[2] || ".");
const porta = Number(process.argv[3] || 4173);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".webmanifest": "application/manifest+json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".mp4": "video/mp4",
  ".m3u8": "application/vnd.apple.mpegurl",
  ".ts": "video/mp2t",
  ".txt": "text/plain; charset=utf-8",
};

http
  .createServer((req, res) => {
    let caminho;
    try {
      caminho = decodeURIComponent(new URL(req.url, "http://localhost").pathname);
    } catch (_) {
      res.writeHead(400).end("Requisição inválida");
      return;
    }

    if (caminho.endsWith("/")) caminho += "index.html";
    const arquivo = path.join(raiz, caminho);

    // Impede sair da pasta raiz.
    if (!arquivo.startsWith(raiz)) {
      res.writeHead(403).end("Proibido");
      return;
    }

    fs.readFile(arquivo, (erro, dados) => {
      if (erro) {
        res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
        res.end("404 — arquivo não encontrado: " + caminho);
        return;
      }
      res.writeHead(200, {
        "Content-Type": MIME[path.extname(arquivo).toLowerCase()] || "application/octet-stream",
        "Cache-Control": "no-store",
        "Service-Worker-Allowed": "/",
      });
      res.end(dados);
    });
  })
  .listen(porta, () => {
    console.log(`EFTV local: http://localhost:${porta}/`);
    console.log(`Landing:    http://localhost:${porta}/web/landing/`);
    console.log(`App:        http://localhost:${porta}/web/app/`);
  });
