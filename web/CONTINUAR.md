# CONTINUAR — EFTV Web/PWA

Guia para retomar o trabalho em outra máquina. Leia também `README.md`.

## Onde está tudo

- Projeto web: `web/` (landing em `web/landing`, app em `web/app`).
- O repositório oficial é <https://github.com/EvertonFagundes/eftv>.
- **Não altere `android/`.** O web é independente.
- Se você está em outra máquina: `git clone https://github.com/EvertonFagundes/eftv.git` e entre em `web/`.

## A versão web do app Android já existe na raiz

- `index.html`, `canal.html`, `assets/` e `sw.js` na raiz são uma cópia dos assets web embutidos no APK (`android/app/src/main/assets/eftv/`).
- O APK é um **WebView** sobre esses arquivos; ele não traz os canais do provedor. Os canais vêm da playlist que o usuário importa.
- A versão da raiz já tem importação de playlist por arquivo/link e player HLS/DASH/MPEG-TS.
- `server.py` na raiz serve essa versão em `http://127.0.0.1:8124/` e faz proxy dos streams, contornando CORS. No GitHub Pages (sem servidor), o download da playlist e os streams dependem do CORS do provedor.
- O PWA em `web/app/` é a versão nova, com login/assinatura. A importação local também foi portada para ele.

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

- [x] Landing page PT-BR premium (hero cinematográfico, bento de experiência, pilares Ao Vivo/Filmes/Séries, catálogo filtrável, planos R$ 19,90, PWA e CTA), com animações de entrada, menu mobile e OG image atualizada.
- [x] App shell com sidebar, views: Ao Vivo, Filmes, Séries, Categorias, Favoritos, Continuar, Recentes, **Minha playlist**, Conta, Ajustes, Ajuda, Busca.
- [x] Login/cadastro/esqueci senha/verificação de e-mail (endpoints reais).
- [x] Catálogo real pela playlist licenciada:
  - o backend entrega o texto M3U em `GET /player/playlist-text` (autenticado);
  - `playlist.js` lê `#EXTINF`, `tvg-logo`, `group-title`, classifica canal/filme/série e agrupa episódios (`S01E02`, `1x02`, `Temporada 1 Episódio 2`);
  - o catálogo fica no **IndexedDB** (dezenas de milhares de itens) com validade de 6h;
  - falha de rede mantém o catálogo salvo; falha sem cache mostra erro (sem trocar por demo).
- [x] **Minha playlist**: importa o arquivo `.m3u`/`.m3u8` direto no navegador (ou link, quando o CORS permite), salva no IndexedDB (`local-playlist`) e tem prioridade sobre backend/demo. A grade mostra 240 cards por vez com **Mostrar mais**.
- [x] Aba Séries com modal de temporadas e episódios.
- [x] Logos/capas reais nos cards, com fallback para o gradiente e o nome.
- [x] Busca sem acento, categorias, A-Z, filtro adulto.
- [x] Favoritos, recentes, continuar assistindo (localStorage).
- [x] Player HLS/TS/DASH/MP4 com qualidade, áudio, legenda, PiP, fullscreen, retry/reconexão, voltar ao vivo.
- [x] Sessão de player: `/player/play`, heartbeat 45 s, stop, limite de tela (`stream_limit`).
- [x] Assinatura: `/subscriptions/current`, checkout Mercado Pago com `back_urls`, cancelar, dispositivos.
- [x] PWA: manifest, service worker, ícones PNG, prints no manifest, instalação iOS/Android, abertura offline e atualização pela própria PWA (sem APK).
- [x] `checkout.html` (retorno do Mercado Pago + deep link `eftv://open`).
- [x] Modo demo explícito (`?demo=1`) com catálogo de exemplo e `media/demo.mp4`.
- [x] Media Session API (controles na tela de bloqueio/central de mídia).
- [x] Testes automatizados:
  - `node web/tools/testar-playlist.js` — parser, agrupamento e categorias;
  - `node web/tools/testar-app.js` - Chrome headless: demo, importação local por arquivo, persistência no IndexedDB, paginação de listas grandes, playlist autenticada, série, player, service worker, manifest, instalabilidade PWA e offline.
- [x] Scripts: servidor local, geração de ícones, captura de prints, layout da OG.

## O que falta / validar

- [ ] **Testar com o backend real (Render)**: login, `/player/playlist-text`, catálogo real, player, heartbeat, limite de tela, checkout. O teste automatizado usa playlist sintética; falta a conta real.
  - O `/health` de produção mostra o provedor devolvendo uma página nginx (235 bytes), não a M3U. O Render não alcança o provedor; o catálogo real depende do cache da playlist.
  - Para popular o cache, rode `backend/scripts/upload_playlist_cache.py` em uma rede que alcance o provedor (a URL e o login admin não devem ser colados no chat). Depois o app usa o cache mesmo com o provedor bloqueado.
  - O app agora mostra na tela o motivo da falha e um botão **Tentar novamente**; o aviso de modo demonstração também aparece no topo do Ao Vivo.
- [x] Conferir CORS do FastAPI para o domínio da landing/app (`CORS_ORIGINS` inclui `https://evertonfagundes.github.io`; resposta 401 de `/player/playlist-text` veio com `Access-Control-Allow-Origin`).
- [ ] Trocar `API_URL` em `web/app/assets/js/config.js` para o domínio final (`https://api.eftv.com.br`), se for usado.
- [x] `DEMO_FALLBACK: false` em produção; `DEMO_MODE: true` mantém `?demo=1` para a landing/testes.
- [ ] Substituir `web/app/assets/media/demo.mp4` e os canais de exemplo por conteúdo autorizado.
- [ ] Testar instalação em Android Chrome, iPhone Safari, Edge/Chrome desktop (o smoke test valida só Chrome headless).
- [x] Revisar textos jurídicos/planos na landing (conferido com `/plans` e `/auth`: R$ 19,90/mês, 7 dias grátis, 2 dispositivos e 1 tela por vez).
- [ ] Opcional: TWA/Bubblewrap para Play Store.
- [ ] Opcional: capas de série via TVMaze/IMDb (hoje usa o `tvg-logo` do provedor; algumas listas têm logo trocado).
- [ ] Opcional: cache offline de páginas já visitadas do catálogo (hoje o catálogo inteiro fica no IndexedDB).

## Como funciona a importação da playlist

1. Se existir uma playlist importada em **Minha playlist** (`local-playlist` no IndexedDB), ela vence e o app monta o catálogo localmente, sem backend.
2. Sem playlist local, o usuário faz login e o app guarda `access`/`refresh` no `localStorage`.
3. `catalog.carregar()` verifica o cache do IndexedDB (6h).
4. Sem cache válido, chama `GET /player/playlist-text` com `Authorization: Bearer` e `X-Device-Id`.
5. O backend baixa a M3U do provedor (a URL nunca vai para o navegador) e devolve o texto.
6. `playlist.js` monta os cards; `catalog.js` indexa por id e categoria.
7. O resultado é salvo no IndexedDB. Se a rede falhar, o cache anterior é mantido.
8. O player chama `POST /player/play` com a URL do canal (a mesma que o Android usa) antes de abrir o vídeo.

### Limitações importantes

- **CORS do provedor**: se o CDN do canal não liberar o domínio web, o vídeo não toca no navegador. Não há proxy no cliente web; é uma diferença em relação ao app Android. Para contornar, use `python server.py` na raiz e abra `http://127.0.0.1:8124/` (a versão web do app Android faz proxy dos streams).
- **Mixed content**: se a playlist entregar `http://` e o app estiver em `https://`, o navegador bloqueia o vídeo.
- **Headers/User-Agent**: canais que exigem cabeçalhos específicos continuam exclusivos do app Android.
- A playlist importada contém URLs/credenciais do provedor. Ela fica **somente no IndexedDB do aparelho**, não é enviada ao backend e **não é apagada no logout** (é independente da conta). Use **Minha playlist → Remover** para apagá-la.
- O texto da playlist do backend também fica no IndexedDB local e é apagado no logout.

## Pontos de atenção no código

- `web/app/assets/js/config.js` → `API_URL`, `DEMO_FALLBACK`, `DEMO_MODE`.
- `web/app/assets/js/api.js` → contrato do backend. Rotas confirmadas em `backend/app/routes/`.
  - `POST /player/play` recebe `{ channel_url, channel_name }` (não `channel_id`).
  - `GET /subscriptions/current` (não `/subscriptions/me`).
  - `POST /subscriptions/{id}/cancel` (não `/subscriptions/cancel`).
  - `/channels` pagina no máximo 100; `canaisTodas()` busca todas as páginas (fallback quando a playlist não está disponível).
  - `GET /player/playlist-text` pode demorar; o cliente espera até 130 s.
- `web/app/assets/js/playlist.js` → parser M3U, classificação e agrupamento de séries.
- `web/app/assets/js/catalog.js` → fonte do catálogo (playlist → API → cache → demo), busca sem acento, categorias, A-Z.
- `web/app/assets/js/store.js` → IndexedDB do catálogo (`eftv-web` / store `catalog`) e da playlist local (`local-playlist`); localStorage para sessão, favoritos, progresso e ajustes.
- `web/app/assets/js/player.js` → token HLS via `xhrSetup`; reconexão automática; Media Session.
- `web/app/assets/js/app.js` → router, telas, série/episódios, conta, ajustes.
- `web/app/sw.js` → ao publicar, suba `CACHE` (`eftv-web-v3` → `v4` → `v5` → `v6`).
- `web/tools/gerar-icones.ps1` → se PNG ficar bloqueado (antivírus/OneDrive), rode de novo; o script usa retentativas.
- `web/tools/capturar.js` → requer Chrome com `--remote-debugging-port=9333` e o servidor em `4173`.

## Fluxo de deploy (GitHub Pages)

1. Commit e push da pasta `web/`.
2. GitHub Pages já serve a raiz; acesse `/web/landing/` e `/web/app/`.
3. Abra o app em HTTPS, instale o PWA e teste o login real.
4. Se mudar arquivos do app, incremente o cache do service worker (atualmente `eftv-web-v6`).

## Comandos úteis

```bash
# validar sintaxe de todos os JS
node --check web/app/assets/js/playlist.js
node --check web/app/assets/js/app.js
node --check web/app/assets/js/api.js
node --check web/app/assets/js/catalog.js
node --check web/app/assets/js/player.js
node --check web/app/assets/js/store.js

# validar manifest
node -e "JSON.parse(require('fs').readFileSync('web/app/manifest.webmanifest','utf8')); console.log('ok')"

# testes
node web/tools/testar-playlist.js
node web/tools/testar-app.js
```

## Git (a partir da raiz do clone)

```bash
git status
git add web/
git commit -m "feat(web): catálogo real pela playlist, séries e cache IndexedDB"
git push origin main
```

> Se o push pedir credenciais, autentique com GitHub CLI (`gh auth login`) ou um Personal Access Token.

## Observações

- O modo demo é acionado por `?demo=1` e funciona mesmo com `DEMO_FALLBACK: false` graças a `DEMO_MODE: true`.
- O service worker não registra em `file://`; use `localhost`/HTTPS.
- A atualização do app web é feita pelo service worker. Não use `/app/version` (versão do Android/APK) para decidir atualização da PWA.
- Prints reais ficam em `web/app/assets/img/screens/` e são usados na landing e no manifest.
