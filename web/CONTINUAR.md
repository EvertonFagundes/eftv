# CONTINUAR — EFTV Web/PWA

Guia para retomar o trabalho em outra máquina. Leia também `README.md`.

## Onde está tudo

- Projeto web: `web/` (landing em `web/landing`, app em `web/app`).
- O repositório oficial é <https://github.com/EvertonFagundes/eftv>.
- **Não altere `android/`.** O web é independente.
- Se você está em outra máquina: `git clone https://github.com/EvertonFagundes/eftv.git` e entre em `web/`.

## A versão web do app Android já existe na raiz

- `index.html`, `canal.html`, `assets/` e `sw.js` na raiz são uma cópia dos assets web embutidos no APK (`android/app/src/main/assets/eftv/`).
- O APK é um **WebView** sobre esses arquivos; ele não traz a playlist licenciada no release. A URL vem do backend (`/player/playlist`) depois do login; em debug pode ser embutida via `local.properties`.
- A versão da raiz tem um painel de playlists como fallback e player HLS/DASH/MPEG-TS.
- `server.py` na raiz serve essa versão em `http://127.0.0.1:8124/` e faz proxy dos streams, contornando CORS. No GitHub Pages (sem servidor), o download da playlist e os streams dependem do CORS do provedor.
- O PWA em `web/app/` é a versão nova, com login/assinatura e provisionamento automático da playlist (URL embutida ou backend).

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

## Provisionamento automático da playlist

Os canais **não são digitados/importados pelo cliente**. O app Android de
release recebe a URL licenciada do backend (GET /player/playlist) depois do
login; em debug, a URL pode vir embutida no build via local.properties. O PWA
agora segue o mesmo modelo:

1. Se PLAYLIST_URL estiver preenchida em config.js (build privado), baixa
   essa lista automaticamente.
2. Senão, com sessão ativa, chama GET /player/playlist e baixa a URL
   licenciada direto no navegador (o IP do cliente pode alcançar o provedor
   mesmo quando o Render não alcança).
3. Se o navegador bloquear por CORS/hotlink, chama
   GET /player/playlist-text e o backend entrega o texto.
4. Se nada funcionar, tenta /channels; por último, mostra erro com **Tentar
   novamente**.

Não existe tela de importação de M3U no PWA: o assinante só faz login.

### Para assistir

1. Abra <https://evertonfagundes.github.io/eftv/web/app/>.
2. Entre com a conta de assinante.
3. Os canais são carregados automaticamente em **Ao Vivo**.

### O que acontece por dentro

- pi.playlistAcesso() chama /player/playlist (mesma rota do Android).
- catalog._carregarPlaylistUrl() baixa e parseia a M3U; a URL e o texto não
  são logados.
- catalog._buscar() tenta URL embutida → URL do backend → texto do backend →
  /channels.
- O catálogo fica no IndexedDB (eftv-web / store catalog) por 6 h; falha de
  rede mantém a cópia salva e o app abre offline.
- playlist.js limita a **50.000 itens** (MAX_ITENS) e diagnosticar()
  explica HTML/JSON/DASH/lista vazia.
- A grade mostra **240 cards por vez** com **Mostrar mais** (LIMITE_GRADE).
- Os chips usam as categorias reais da playlist.

### Build privado com URL embutida

Em web/app/assets/js/config.js, preencha PLAYLIST_URL com a URL licenciada.
Isso reproduz o local.properties do Android em debug. **Nunca comite essa URL
em repositório público**: ela contém usuário/senha do provedor. Em produção
pública, deixe vazio e use o backend.

### Limitações

- O PWA público não tem a URL embutida; depende do backend ou de um build
  privado. O Render hoje não alcança o provedor (página nginx), então o caminho
  garantido é popular o cache (ackend/scripts/upload_playlist_cache.py) ou
  usar um build privado.
- Reprodução no navegador depende de CORS/hotlink; se o vídeo não tocar, use o
  app Android ou python server.py na raiz (proxy local).
- O endpoint /player/playlist entrega a URL licenciada ao cliente autenticado
  (como no Android). O fallback /playlist-text evita expor a URL ao navegador,
  mas depende de o backend alcançar o provedor.

## O que já está pronto

- [x] Landing page PT-BR premium (hero cinematográfico, bento de experiência, pilares Ao Vivo/Filmes/Séries, catálogo filtrável, planos R$ 19,90, PWA e CTA), com animações de entrada, menu mobile e OG image atualizada.
- [x] App shell com sidebar, views: Ao Vivo, Filmes, Séries, Categorias, Favoritos, Continuar, Recentes, Conta, Ajustes, Ajuda, Busca.
- [x] Login/cadastro/esqueci senha/verificação de e-mail (endpoints reais).
- [x] Catálogo real pela playlist licenciada:
  - `GET /player/playlist` entrega a URL licenciada (como no Android); `GET /player/playlist-text` é o fallback autenticado;
  - `playlist.js` lê `#EXTINF`, `tvg-logo`, `group-title`, classifica canal/filme/série e agrupa episódios (`S01E02`, `1x02`, `Temporada 1 Episódio 2`);
  - o catálogo fica no **IndexedDB** (dezenas de milhares de itens) com validade de 6h;
  - falha de rede mantém o catálogo salvo; falha sem cache mostra erro (sem trocar por demo).
- [x] **Provisionamento automático da playlist**: o app usa `PLAYLIST_URL` embutida (build privado) ou `GET /player/playlist` + download direto; se o CORS bloquear, usa `/player/playlist-text`. Não há tela de importação para o assinante. A grade mostra 240 cards por vez com **Mostrar mais**.
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
  - `node web/tools/testar-app.js` - Chrome headless: demo, provisionamento automático (URL do backend e fallback de texto), paginação, playlist autenticada, série, player, service worker, manifest, instalabilidade PWA e offline.
- [x] Scripts: servidor local, geração de ícones, captura de prints, layout da OG.

## O que falta / validar

- [ ] **Testar com o backend real (Render)**: login, `/player/playlist`, `/player/playlist-text`, catálogo real, player, heartbeat, limite de tela, checkout. O teste automatizado usa playlist sintética; falta a conta real.
  - O `/health` de produção mostra o provedor devolvendo uma página nginx (235 bytes), não a M3U. O Render não alcança o provedor; o catálogo real depende do cache da playlist.
  - Para popular o cache, rode `backend/scripts/upload_playlist_cache.py` em uma rede que alcance o provedor (a URL e o login admin não devem ser colados no chat). Depois o app usa o cache mesmo com o provedor bloqueado.
  - O app agora mostra na tela o motivo da falha e um botão **Tentar novamente**; o aviso de modo demonstração também aparece no topo do Ao Vivo.
- [x] **Provisionamento automático no PWA**: validado em 27/11/2026 no Chrome headless (URL do backend, fallback de texto, cache e offline) e no app publicado.
- [ ] **Testar com a URL real do provedor (~84 MB)**: o teste automatizado usa playlist sintética; falta confirmar CORS/hotlink e o cache do backend com a M3U real.
- [x] Conferir CORS do FastAPI para o domínio da landing/app (`CORS_ORIGINS` inclui `https://evertonfagundes.github.io`; resposta 401 de `/player/playlist-text` veio com `Access-Control-Allow-Origin`).
- [ ] Trocar `API_URL` em `web/app/assets/js/config.js` para o domínio final (`https://api.eftv.com.br`), se for usado.
- [x] `DEMO_FALLBACK: false` em produção; `DEMO_MODE: true` mantém `?demo=1` para a landing/testes.
- [ ] Substituir `web/app/assets/media/demo.mp4` e os canais de exemplo por conteúdo autorizado.
- [ ] Testar instalação em Android Chrome, iPhone Safari, Edge/Chrome desktop (o smoke test valida só Chrome headless).
- [x] Revisar textos jurídicos/planos na landing (conferido com `/plans` e `/auth`: R$ 19,90/mês, 7 dias grátis, 2 dispositivos e 1 tela por vez).
- [ ] Opcional: TWA/Bubblewrap para Play Store.
- [ ] Opcional: capas de série via TVMaze/IMDb (hoje usa o `tvg-logo` do provedor; algumas listas têm logo trocado).
- [ ] Opcional: cache offline de páginas já visitadas do catálogo (hoje o catálogo inteiro fica no IndexedDB).

## Como funciona o provisionamento da playlist

1. O usuário faz login e o app guarda `access`/`refresh` no `localStorage`.
2. `catalog.carregar()` verifica o cache do IndexedDB (6 h).
3. Sem cache válido:
   - se `PLAYLIST_URL` estiver configurada em `config.js`, baixa essa URL;
   - senão chama `GET /player/playlist` e baixa a URL licenciada direto no navegador;
   - se o navegador bloquear (CORS/hotlink), chama `GET /player/playlist-text`;
   - se ainda falhar, tenta `/channels` (paginado).
4. `playlist.js` monta os cards; `catalog.js` indexa por id e categoria.
5. O resultado é salvo no IndexedDB. Se a rede falhar, o cache anterior é mantido.
6. O player chama `POST /player/play` com a URL do canal (a mesma que o Android usa) antes de abrir o vídeo.

### Limitações importantes

- **CORS do provedor**: se o CDN do canal não liberar o domínio web, o vídeo não toca no navegador. Não há proxy no cliente web; é uma diferença em relação ao app Android. Para contornar, use `python server.py` na raiz e abra `http://127.0.0.1:8124/` (a versão web do app Android faz proxy dos streams).
- **Mixed content**: se a playlist entregar `http://` e o app estiver em `https://`, o navegador bloqueia o vídeo.
- **Headers/User-Agent**: canais que exigem cabeçalhos específicos continuam exclusivos do app Android.
- A URL licenciada contém credenciais do provedor e não é logada. Quando vem de `/player/playlist`, fica visível apenas na rede/memória do cliente autenticado (como no Android); o fallback `/playlist-text` evita expor a URL ao navegador.
- O catálogo (com as URLs dos streams) fica no IndexedDB local e é apagado no logout.

## Pontos de atenção no código

- `web/app/assets/js/config.js` → `API_URL`, `PLAYLIST_URL` (opcional, build privado), `DEMO_FALLBACK`, `DEMO_MODE`.
- `web/app/assets/js/api.js` → contrato do backend. Rotas confirmadas em `backend/app/routes/`.
  - `POST /player/play` recebe `{ channel_url, channel_name }` (não `channel_id`).
  - `GET /subscriptions/current` (não `/subscriptions/me`).
  - `POST /subscriptions/{id}/cancel` (não `/subscriptions/cancel`).
  - `/channels` pagina no máximo 100; `canaisTodas()` busca todas as páginas (fallback quando a playlist não está disponível).
  - `GET /player/playlist` entrega a URL licenciada (mesma rota do Android); `GET /player/playlist-text` pode demorar e o cliente espera até 130 s.
- `web/app/assets/js/playlist.js` → parser M3U, `MAX_ITENS` (50.000), `diagnosticar()` e classificação/agrupamento de séries.
- `web/app/assets/js/catalog.js` → provisionamento automático (URL embutida → `/player/playlist` → `/playlist-text` → `/channels`), cache, busca sem acento, categorias, A-Z.
- `web/app/assets/js/store.js` → IndexedDB do catálogo (`eftv-web` / store `catalog`); localStorage para sessão, favoritos, progresso e ajustes.
- `web/app/assets/js/player.js` → token HLS via `xhrSetup`; reconexão automática; Media Session.
- `web/app/assets/js/app.js` → router, telas, `LIMITE_GRADE` (240), conta, ajustes.
- `web/app/sw.js` → ao publicar, suba `CACHE` (atual `eftv-web-v7`; histórico `v3` → `v4` → `v5` → `v6` → `v7`).
- `web/tools/gerar-icones.ps1` → se PNG ficar bloqueado (antivírus/OneDrive), rode de novo; o script usa retentativas.
- `web/tools/capturar.js` → requer Chrome com `--remote-debugging-port=9333` e o servidor em `4173`.

## Fluxo de deploy (GitHub Pages)

1. Rode os testes (`testar-playlist.js` e `testar-app.js`).
2. Se mudar arquivos do app, suba `APP_VERSION` em `config.js`/`index.html` e `CACHE` em `sw.js` (atual `eftv-web-v7`).
3. Commit e push da pasta `web/`.
4. GitHub Pages já serve a raiz; aguarde a publicação e confira `/web/landing/` e `/web/app/`.
5. Abra o app em HTTPS e valide: versão exibida, cache do SW, login, provisionamento automático da playlist, recarregar e offline.

## Última validação (27/11/2026)

- `node web/tools/testar-playlist.js`: 6 testes ok.
- `node web/tools/testar-app.js`: todos ok, incluindo provisionamento automático pela URL do backend, fallback pelo texto do backend, paginação 240/300, service worker, manifest, instalabilidade e offline.
- Teste sintético de 50.000 itens (6,4 MB) no parser: ~7 s e 240 cards por vez.
- Live <https://evertonfagundes.github.io/eftv/web/app/>: versão **1.1.4**, SW **`eftv-web-v7`**; o carregamento real depende do backend/cache ou de `PLAYLIST_URL` em build privado.
- A URL real do provedor (~84 MB) ainda não foi testada; ver pendências acima.

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
