# CONTINUAR — EFTV Web/PWA

Guia para retomar o trabalho em outra máquina. Leia também `README.md`.

## Onde está tudo

- Projeto web: `web/` (landing em `web/landing`, app em `web/app`).
- O repositório oficial é <https://github.com/EvertonFagundes/eftv>.
- **Não altere `android/`.** O web é independente.
- Se você está em outra máquina: `git clone https://github.com/EvertonFagundes/eftv.git` e entre em `web/`.

## Rodar em 1 minuto

```bash
# na raiz do repositório
node web/tools/servidor.js . 4173
```

- Landing: <http://localhost:4173/web/landing/>
- App: <http://localhost:4173/web/app/>
- Demo: <http://localhost:4173/web/app/?demo=1>
- Player demo: <http://localhost:4173/web/app/?demo=1&canal=globo>

Sem Node? Use `python -m http.server 4173` na raiz.

## O que já está pronto

- [x] Landing page PT-BR (hero, recursos, prints reais, catálogo, planos R$ 19,90, PWA, CTA).
- [x] App shell com sidebar, views: Ao Vivo, Filmes, Séries, Categorias, Favoritos, Continuar, Recentes, Conta, Ajustes, Ajuda, Busca.
- [x] Login/cadastro/esqueci senha/verificação de e-mail (endpoints reais).
- [x] Catálogo com paginação (todas as páginas), busca sem acento, categorias, A-Z, filtro adulto.
- [x] Favoritos, recentes, continuar assistindo (localStorage).
- [x] Player HLS/TS/DASH/MP4 com qualidade, áudio, legenda, PiP, fullscreen, retry/reconexão, voltar ao vivo.
- [x] Sessão de player: `/player/play`, heartbeat 45 s, stop, limite de tela (`stream_limit`).
- [x] Assinatura: `/subscriptions/current`, checkout Mercado Pago com `back_urls`, cancelar, dispositivos.
- [x] PWA: manifest, service worker, ícones PNG, prints no manifest, instalação iOS/Android.
- [x] `checkout.html` (retorno do Mercado Pago + deep link `eftv://open`).
- [x] Modo demo (`?demo=1`) com catálogo de exemplo e `media/demo.mp4`.
- [x] Scripts: servidor local, geração de ícones, captura de prints, layout da OG.

## O que falta / validar

- [ ] **Testar com o backend real** (Render): login, catálogo paginado, player, heartbeat, limite de tela, checkout.
- [ ] Conferir CORS do FastAPI para o domínio da landing/app (`ALLOWED_ORIGINS`).
- [ ] Trocar `API_URL` em `web/app/assets/js/config.js` para o domínio final.
- [ ] Definir `DEMO_FALLBACK: false` em produção.
- [ ] Substituir `web/app/assets/media/demo.mp4` e os canais de exemplo por conteúdo autorizado.
- [ ] Testar instalação em Android Chrome, iPhone Safari, Edge/Chrome desktop.
- [ ] Revisar textos jurídicos/planos (2 dispositivos, 1 tela) na landing.
- [ ] Opcional: TWA/Bubblewrap para Play Store.
- [ ] Opcional: Media Session API para controles na tela de bloqueio.

## Pontos de atenção no código

- `web/app/assets/js/config.js` → `API_URL` e `DEMO_FALLBACK`.
- `web/app/assets/js/api.js` → contrato do backend. Rotas confirmadas em `backend/app/routes/`.
  - `POST /player/play` recebe `{ channel_url, channel_name }` (não `channel_id`).
  - `GET /subscriptions/current` (não `/subscriptions/me`).
  - `POST /subscriptions/{id}/cancel` (não `/subscriptions/cancel`).
  - `/channels` pagina no máximo 100; `canaisTodas()` busca todas as páginas.
- `web/app/assets/js/catalog.js` → normaliza `group_title`, `stream_type`, `is_adult`.
- `web/app/assets/js/player.js` → token HLS via `xhrSetup`; reconexão automática.
- `web/app/sw.js` → ao publicar, suba `CACHE` (`eftv-web-v2` → `v3`).
- `web/tools/gerar-icones.ps1` → se PNG ficar bloqueado (antivírus/OneDrive), rode de novo; o script usa retentativas.
- `web/tools/capturar.js` → requer Chrome com `--remote-debugging-port=9333` e o servidor em `4173`.

## Fluxo de deploy (GitHub Pages)

1. Commit e push da pasta `web/`.
2. GitHub Pages já serve a raiz; acesse `/web/landing/` e `/web/app/`.
3. Abra o app em HTTPS, instale o PWA e teste o login real.
4. Se mudar arquivos do app, incremente o cache do service worker.

## Comandos úteis

```bash
# validar sintaxe de todos os JS
node --check web/app/assets/js/app.js
node --check web/app/assets/js/api.js
node --check web/app/assets/js/catalog.js
node --check web/app/assets/js/player.js

# validar manifest
node -e "JSON.parse(require('fs').readFileSync('web/app/manifest.webmanifest','utf8')); console.log('ok')"
```

## Git (a partir da raiz do clone)

```bash
git status
git add web/
git commit -m "feat(web): app PWA com paridade Android + landing e prints reais"
git push origin main
```

> Se o push pedir credenciais, autentique com GitHub CLI (`gh auth login`) ou um Personal Access Token.

## Observações

- O modo demo é acionado por `?demo=1` e só funciona com `DEMO_FALLBACK: true`.
- O service worker não registra em `file://`; use `localhost`/HTTPS.
- Prints reais ficam em `web/app/assets/img/screens/` e são usados na landing e no manifest.
