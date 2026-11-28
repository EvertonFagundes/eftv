# EFTV — Versão Web + PWA

Versão web do EFTV (canais ao vivo, filmes e séries) com **landing page** de vendas e **app instalável (PWA)**. O app Android em `android/` não foi alterado.

> **Status:** interface e fluxos completos. O catálogo real é provisionado **automaticamente**, como no Android: o app baixa a playlist licenciada por `GET /player/playlist` (URL do backend) ou, se o navegador bloquear, por `GET /player/playlist-text`. Em build privado, `PLAYLIST_URL` em `config.js` pode trazer a URL embutida. Não há tela de importação para o assinante. No modo **self-hosted**, o app detecta o `server.py` (mesma origem ou `PROXY_URL`) e usa o catálogo magro + proxy com headers/DoH. O modo demonstração aparece com `?demo=1` ou quando não há sessão nem servidor local. Os canais **não são embutidos** no repositório. Falta validar login/player/checkout com uma conta real em produção e testar a M3U real de ~84 MB (ver `CONTINUAR.md`).

---

## 1. Estrutura

```
web/
├── landing/                     # Página pública de vendas
│   ├── index.html
│   └── assets/{css,js,img}
├── app/                         # Aplicativo PWA
│   ├── index.html               # Shell do app (views, player, modais)
│   ├── checkout.html            # Retorno do Mercado Pago + deep link
│   ├── manifest.webmanifest
│   ├── sw.js                    # Service worker
│   └── assets/
│       ├── css/style.css
│       ├── js/
│       │   ├── config.js        # API_URL, versão, intervalos, modo demo
│       │   ├── store.js         # IndexedDB do catálogo + localStorage (sessão etc.)
│       │   ├── api.js           # Cliente da API FastAPI
│       │   ├── playlist.js      # Parser M3U, diagnóstico, classificação e agrupamento de séries
│       │   ├── catalog.js       # Provisionamento automático, catálogo, busca sem acento, categorias, A-Z
│       │   ├── player.js        # HLS / MPEG-TS / DASH / MP4
│       │   ├── app.js           # Router, telas, auth, conta, ajustes, séries
│       │   └── pwa.js           # Instalação + service worker
│       ├── img/                 # Ícones PNG, poster, prints reais (screens/)
│       └── media/demo.mp4       # Vídeo de demonstração (12s, ~90 KB)
└── tools/
    ├── servidor.js              # Servidor estático local (sem dependências)
    ├── testar-playlist.js       # Testes do parser M3U (Node, sem dependências)
    ├── testar-app.js            # Smoke test do app via Chrome headless/CDP
    ├── gerar-icones.ps1         # Gera ícones PNG + OG image
    ├── og.html                  # Layout da imagem OG (1200x630)
    └── capturar.js              # Prints reais via Chrome DevTools Protocol
```

---

## 2. Rodar localmente

Requisitos: Node.js 18+ (ou Python 3) e um navegador moderno.

```bash
# na raiz do repositório
node web/tools/servidor.js . 4173
```

Abra:

- Landing: <http://localhost:4173/web/landing/>
- App: <http://localhost:4173/web/app/>
- App em modo demonstração: <http://localhost:4173/web/app/?demo=1>
- Player direto (demo): <http://localhost:4173/web/app/?demo=1&canal=globo>

> O service worker só registra em `https://`, `localhost` ou `127.0.0.1`. Em `file://` o app funciona, mas sem instalação/offline.

### Testes automatizados

```bash
# parser M3U: canais, filmes, séries, temporadas, categorias e casos inválidos
node web/tools/testar-playlist.js

# app no Chrome headless: demo, provisionamento automático (URL do backend e fallback de texto), paginação, série, player, IndexedDB, SW, manifest e offline
node web/tools/testar-app.js
```

O teste do app sobe o servidor estático e o Chrome sozinho; requer Chrome ou Edge instalado (ou `EFTV_CHROME` apontando para o executável).

---

## 3. Configuração da API

Edite `web/app/assets/js/config.js`:

```js
window.EFTV_CONFIG = {
  API_URL: "https://eftv.onrender.com", // troque por https://api.eftv.com.br em produção
  APP_VERSION: "1.2.0",
  PLAYLIST_URL: "",     // opcional: só em build privado; nunca comite credenciais
  PROXY_URL: "",        // opcional: server.py local ou proxy HTTPS próprio
  TRIAL_NUDGE_DAYS: 3,  // aviso de fim de teste nos últimos N dias
  DEMO_FALLBACK: false, // não troca por demo quando a rede falha
  DEMO_MODE: true,      // mantém ?demo=1 explícito para landing/testes
  HEARTBEAT_MS: 45000,
  PROGRESS_SAVE_MS: 5000,
  PAGE_SIZE: 60,
};
```

Também é possível trocar a URL sem editar o arquivo:

```js
localStorage.setItem("eftv_api_url", "https://api.eftv.com.br");
```

**Antes de publicar:** mantenha `DEMO_FALLBACK: false`. Com `true`, falhas de rede liberam o app em modo demonstração — ótimo para testar, ruim para produção. O modo demo explícito (`DEMO_MODE: true` + `?demo=1`) continua disponível para a landing e para os testes automatizados.

---

## 4. Contrato do backend (FastAPI)

Implementado em `api.js`, alinhado ao backend em `backend/app/routes/`:

| Função | Método e rota | Corpo / observação |
|---|---|---|
| Login | `POST /auth/login` | `{ email, password }` → `access_token`, `refresh_token` |
| Cadastro | `POST /auth/register` | `{ full_name, email, password }` |
| Renovar token | `POST /auth/refresh` | `{ refresh_token }` |
| Sair | `POST /auth/logout` | `{ refresh_token }` |
| Esqueci a senha | `POST /auth/forgot-password` | `{ email }` |
| Redefinir senha | `POST /auth/reset-password` | `{ email, code, new_password }` |
| Confirmar e-mail | `POST /auth/verify-email` | `{ token }` |
| Meus dados | `GET /auth/me` | Bearer |
| Categorias | `GET /categories?include_adult=` | público |
| Canais | `GET /channels?page=&page_size=&category_id=&search=&is_live=&include_adult=` | paginado, máx. 100/página; fallback quando a playlist não está disponível |
| Texto da playlist | `GET /player/playlist-text` | Bearer + `X-Device-Id`; devolve a M3U do provedor (fonte principal do catálogo) |
| Planos | `GET /plans` | `{ plans: [...] }` |
| Assinatura atual | `GET /subscriptions/current` | resumo com `status`, `plan_name`, `days_remaining`, `current_period_end`, `max_devices`, `max_streams` |
| Checkout | `POST /subscriptions/checkout` | `{ plan_id, back_urls: { success, failure, pending } }` → `init_point` |
| Cancelar | `POST /subscriptions/{subscription_id}/cancel` | Bearer |
| Iniciar player | `POST /player/play` | `{ channel_url, channel_name }` → `session_id`, `limit`, `active`, `heartbeat_in` |
| Heartbeat | `POST /player/heartbeat` | `{ session_id }` (backend expira em 120 s) |
| Parar player | `POST /player/stop` | `{ session_id }` |
| Dispositivos | `GET /player/device` | `{ limit, bound, devices: [...] }` |
| Desvincular todos | `POST /player/device/revoke-all` | Bearer |
| Versão do app | `GET /app/version` | `version_code`, `apk_url`, `mandatory` |
| Relatar erro | `POST /app/crashes` | `{ message, stacktrace, app_version, device, android: "web" }` |
| Código de TV | `POST /auth/device-code` + `POST /auth/device-code/poll` | login por código |

**Cabeçalhos enviados:** `Authorization: Bearer <access>` e `X-Device-Id: <id estável>`.

**Campos do catálogo normalizados:** `name`, `slug`, `group_title`, `category_id`, `logo_url`, `is_live`, `is_adult`, `stream_url`, `stream_type`. A playlist é lida no navegador por `playlist.js` e convertida para esses mesmos campos.

---

## 5. Funcionalidades (paridade com o Android)

- Login, cadastro, confirmação de e-mail, esqueci/redefinir senha.
- Catálogo real pela playlist licenciada, provisionado automaticamente:
  - `PLAYLIST_URL` embutida (build privado) ou `GET /player/playlist` (mesma rota do Android) e download direto no navegador;
  - se o navegador bloquear por CORS/hotlink, `GET /player/playlist-text` entrega a M3U autenticada;
  - `playlist.js` lê `#EXTINF`, `tvg-logo`, `group-title`, `#EXTVLCOPT`/`#EXTHTTP`/`#KODIPROP`, headers embutidos na URL, classifica canal/filme/série e agrupa episódios (`S01E02`, `1x02`, `Temporada 1 Episódio 2`);
  - o catálogo fica no **IndexedDB** (dezenas de milhares de itens) com validade de 6 h e cache versão 3; falha de rede mantém o cache anterior;
  - se a playlist não estiver disponível, o app tenta o catálogo local do `server.py` e depois `/channels` (paginado).
- Sem tela de importação: o assinante só faz login. A grade mostra 240 cards por vez com **Mostrar mais**; o parser aceita até 250.000 itens e tem diagnóstico para HTML/JSON/DASH.
- Aba **Séries** com modal de temporadas e episódios, como no Android.
- Logos/capas reais nos cards, com fallback para o gradiente e o nome.
- Catálogo com busca **sem acento**, busca de categorias, categorias com contagem e filtro de conteúdo adulto.
- Índice **A-Z** nos canais ao vivo.
- Favoritos, recentes e **continuar assistindo** (progresso salvo a cada ~1% + carrossel na home).
- **Modo self-hosted**: detecta o `server.py` na mesma origem ou em `PROXY_URL`, carrega o catálogo magro (`/api/catalogo.json`), resolve fontes em `/api/canal?slug=` e usa o proxy com headers/DoH/Range.
- Player **HLS (hls.js), MPEG-TS (mpegts.js), DASH (dash.js) e MP4**, com:
  - qualidade, faixa de áudio e legenda;
  - voltar 10 s / avançar 10 s, mudo, tela cheia, Picture-in-Picture;
  - “Voltar ao vivo”, reconexão com backoff, troca de fonte (proxy↔direto) e fallback HLS derivado de `.ts`;
  - headers por canal, Wake Lock, Media Session e heartbeat de sessão.
- Limite de **1 tela simultânea** (tratamento de `403 stream_limit` e `409 session_closed`).
- Limite de **2 dispositivos**, com lista e desvincular todos.
- Assinatura: status, validade, dias restantes, checkout Mercado Pago, cancelamento e “restaurar compras”.
- Aviso de fim do teste grátis nos últimos `TRIAL_NUDGE_DAYS` (uma vez por dia).
- Ajustes: conteúdo adulto, modo TV, economia de dados, autoplay, proxy local, passar streams pelo proxy, overscan de TV e limpar cache.
- Instalação PWA (Android/Chrome/Edge e instruções para iPhone/Safari).
- Deep link `?canal=slug` / `?id=UUID` e retorno de pagamento em `checkout.html`.
- Login por código para TV (quando o backend expõe `/auth/device-code`).
- Modo demonstração completo (`?demo=1`) com catálogo de exemplo e vídeo local.

### Diferenças inevitáveis em relação ao Android

- **Downloads offline de vídeo** não são possíveis no navegador (o PWA guarda apenas a casca/interface).
- **Canais que exigem headers/User-Agent específicos ou proxy local** funcionam pelo modo self-hosted (`server.py`) ou por um proxy HTTPS próprio; no modo direto dependem do CORS e dos headers que o navegador/hls.js consegue enviar.
- **DRM Widevine** depende do navegador/dispositivo; o app não implementa licenciamento próprio.
- **Reprodução em segundo plano** é limitada pelo sistema (Media Session/PiP ajudam, mas não é igual ao serviço nativo).
- **Android TV / Fire TV** continuam exclusivos do app nativo.

---

## 6. PWA e instalação

- Manifest: `web/app/manifest.webmanifest` (standalone, ícones PNG, atalhos, screenshots).
- Service worker: `web/app/sw.js`
  - HTML/JS/CSS: **rede primeiro** (não fica preso em versão antiga);
  - ícones/imagens: cache primeiro;
  - API, vídeo, áudio e range requests: **sem cache**.
- Instalação: abra o app em HTTPS/localhost e use “Instalar app” (Android/desktop) ou Compartilhar → “Adicionar à Tela de Início” (iOS).
- Ao publicar uma nova versão, incremente `CACHE` em `sw.js` (`eftv-web-v8` atualmente; histórico `v3` → `v4` → `v5` → `v6` → `v7` → `v8`) para limpar caches antigos. `playlist.js`, `catalog.js` e `source.js` fazem parte do `CORE` do service worker.

---

## 7. Ícones, prints e imagem OG

Os arquivos finais já estão em `web/app/assets/img/`:

- `icon-72.png` … `icon-512.png`, `icon-maskable-512.png`, `apple-touch-icon.png`, `favicon-32.png`;
- `screens/app-ao-vivo.png`, `app-categorias.png`, `app-player.png`, `app-player-paisagem.png`, `app-conta.png`, `app-ajustes.png`, `app-desktop.png`;
- `placeholder-poster.svg` e `media/demo.mp4`.

Para regerar os ícones (Windows):

```powershell
powershell -ExecutionPolicy Bypass -File web/tools/gerar-icones.ps1
```

> O script grava em memória e usa retentativas porque antivírus/OneDrive podem travar PNGs recém-criados. Se um arquivo ficar bloqueado, feche visualizadores de imagem e rode de novo.

Para regerar os prints reais:

```powershell
# 1) servidor local
node web/tools/servidor.js . 4173

# 2) Chrome com depuração remota (outra janela)
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --headless=new --disable-gpu --hide-scrollbars --autoplay-policy=no-user-gesture-required --remote-debugging-port=9333 --user-data-dir="$env:TEMP\eftv-cdp" about:blank

# 3) captura
node web/tools/capturar.js web/app/assets/img/screens
```

Para regerar a imagem OG (1200x630):

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --headless=new --disable-gpu --hide-scrollbars --window-size=1200,630 --screenshot="web/landing/assets/img/og.png" "file:///CAMINHO/ABSOLUTO/web/tools/og.html"
```

Troque `demo.mp4` por um vídeo curto real quando quiser que o modo demonstração mostre conteúdo licenciado.

---

## 8. Deploy

### GitHub Pages (recomendado para este repositório)

O repositório já publica páginas estáticas na raiz. Basta enviar a pasta `web/`:

- Landing: `https://SEU-DOMINIO/web/landing/`
- App: `https://SEU-DOMINIO/web/app/`

Não é necessário build. O `.nojekyll` da raiz já está presente.

### Cloudflare Pages / Netlify / Vercel

- Build command: *(vazio)*
- Output directory: `.` (raiz do repositório)
- Os caminhos relativos continuam funcionando.

### Backend

O app usa `API_URL` em `config.js`. Garanta CORS liberado para o domínio da landing/app no FastAPI (`CORS_ORIGINS`).

---

## 9. Limitações e cuidados

- **CORS:** sem proxy, se o provedor de streams não liberar o domínio web, o canal não toca no navegador. O modo self-hosted (`python server.py` e abrir `http://127.0.0.1:8124/web/app/`) resolve CORS, headers, DoH e streams HTTP; em página HTTPS, um proxy `http://127.0.0.1` é bloqueado por mixed content, então use um proxy HTTPS.
- **Playlist provisionada:** a URL licenciada contém credenciais do provedor e não é logada. Quando vem de `/player/playlist`, fica visível apenas na rede/memória do cliente autenticado (como no Android); o fallback `/playlist-text` evita expor a URL ao navegador. O catálogo (com as URLs dos streams) fica no IndexedDB local e é apagado no logout.
- **Autoplay:** navegadores bloqueiam áudio automático; o usuário pode precisar tocar em ▶.
- **iOS:** instalação é manual (Compartilhar → Adicionar à Tela de Início) e HLS usa o player nativo.
- **Direitos autorais:** o catálogo é agregado de terceiros. Antes de promover comercialmente, confirme licenciamento/autorização dos sinais. Este projeto não concede direitos sobre o conteúdo.
- **Modo demonstração:** não cobre pagamentos reais e usa catálogo/vídeo de exemplo.

---

## 10. Próximos passos

Veja `CONTINUAR.md` para o checklist detalhado. Resumo:

1. Testar com a M3U real do provedor (~84 MB) pelo fluxo automático (`/player/playlist` ou build privado) e confirmar quais streams tocam no navegador (CORS/hotlink).
2. Validar login/catálogo/player/checkout contra o backend real com uma conta de assinante.
3. Popular o cache da playlist no backend (`backend/scripts/upload_playlist_cache.py`) ou corrigir a URL do provedor no Render (hoje o backend recebe uma página de erro do nginx em vez da M3U).
4. Trocar `demo.mp4` e os canais de exemplo por conteúdo autorizado.
5. Testar em Android Chrome, iPhone Safari e desktop.
6. Opcional: empacotar como TWA (Bubblewrap) para publicar na Play Store.
