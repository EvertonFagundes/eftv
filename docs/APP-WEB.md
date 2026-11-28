# EFTV Web — documentação técnica

A versão web existe em duas partes, com papéis diferentes:

| Parte | Onde vive | Publicação | Papel |
|---|---|---|---|
| **Páginas estáticas** | raiz do repositório (`index.html`, `checkout.html`, `verify-email.html`, `canal.html`, `privacidade.html`, `termos.html`) | **GitHub Pages** → `https://evertonfagundes.github.io/eftv` | landing, retorno do checkout, confirmação de e-mail, player web, páginas legais |
| **SPA do assinante** | `frontend/` (Vite + HTML/CSS/JS) | **Cloudflare Pages** (opcional, via workflow) | login, cadastro, planos, conta, player |

O backend usa `FRONTEND_URL = https://evertonfagundes.github.io/eftv` para o
`back_url` do Mercado Pago e para os links dos e-mails. Ou seja: **o que o cliente
recebe por e-mail é GitHub Pages**, não a SPA.

---

## 1. Páginas estáticas (GitHub Pages)

Publicadas direto da raiz do repositório (`.nojekyll` presente). Não há build.

| Arquivo | Função |
|---|---|
| `index.html` | landing/apresentação: o que é a EFTV, como assinar, como instalar o app, instruções de servidor local (Termux/PC) |
| `checkout.html` | página de retorno do Mercado Pago. Lê `status` da URL; se voltou sem status (`/preapproval` não devolve), abre o app por `eftv://open` com fallback |
| `verify-email.html` | confirma o e-mail: `POST /auth/verify-email` com o token do link, mostra resultado e botão "Abrir o app" (`eftv://open`) |
| `canal.html` | player web de um canal (abre pela URL do catálogo) |
| `privacidade.html` / `termos.html` | documentos legais exigidos por loja/pagamento |
| `manifest.webmanifest` + `sw.js` | PWA (instalável, cache offline básico) |

Pontos de atenção:
- `checkout.html` **não** processa pagamento: quem processa é o Mercado Pago.
  Ele só lê o retorno e devolve o cliente ao app.
- O deep link `eftv://open` só abre o app se ele estiver instalado; senão a página
  mostra o fallback.

---

## 2. SPA do assinante (`frontend/`)

Projeto Vite (Node 20), sem framework:

```
frontend/
├── public/
│   ├── index.html        # landing da SPA
│   ├── login.html
│   ├── register.html
│   ├── plans.html
│   ├── account.html      # área do assinante
│   ├── player.html       # player HLS/DASH/TS/MP4
│   ├── assets/css/style.css
│   ├── assets/js/        # api, auth, catalog, account, player, utils (ES Modules)
│   ├── manifest.webmanifest
│   └── sw.js
├── package.json
└── vite.config.js
```

**Rodar local:**

```bat
cd frontend
npm install
npm run dev
```

**Build:** `npm run build` → `frontend/dist`.

**Deploy:** `.github/workflows/frontend.yml` roda lint/build em cada push que
toque `frontend/`. O job `deploy-cloudflare-pages` só executa se a variável de
repositório `CLOUDFLARE_PAGES=true` existir, e usa os segredos
`CLOUDFLARE_API_TOKEN` e `CLOUDFLARE_ACCOUNT_ID`.

Sem esses segredos a SPA é apenas verificada no CI — a produção web que o
cliente vê hoje é a das páginas estáticas.

---

## 3. Autenticação na web

- Login/cadastro pela SPA usam os mesmos `/auth/*` do app Android.
- O **refresh token** pode ir em cookie `HttpOnly` (`path=/auth/refresh`) no
  navegador; no app Android vai no corpo JSON.
- Confirmação de e-mail cai em `verify-email.html` (GitHub Pages), que chama a API
  e oferece "Abrir o app".

---

## 4. Assinatura pela web

1. Cliente escolhe o plano (`plans.html` ou pelo app).
2. `POST /subscriptions/checkout` (autenticado) devolve `init_point`.
3. Navegador abre o Mercado Pago — **só cartão de crédito**.
4. Mercado Pago volta para `checkout.html` com `status`, ou abre o app por
   `eftv://open`.
5. Backend ativa por webhook **ou** pela conciliação de 5 min (`sync_pending_subscriptions`).

Detalhes, cancelamento e diagnóstico: `PAGAMENTOS.md`.

---

## 5. Diagnóstico da web

- `GET https://eftv.onrender.com/health` mostra:
  `mercadopago_configured`, `mercadopago_token_kind`, `mercadopago_sandbox`,
  `mercadopago_account`, `frontend_url`, `checkout_back_url`, `max_devices_per_subscription`,
  `app_version_code`, `app_update_configured`.
- CORS é configurado por `CORS_ORIGINS` (lista separada por vírgula).
- Rate limit de login é **por conta (e-mail)**, porque atrás do proxy do Render
  todos os clientes chegam do mesmo IP.

---

## 6. Limitações conhecidas

- A SPA não substitui o app: sem download offline de catálogo, sem servidor local
  (proxy), sem limite de telas por sessão de player.
- Player web depende do CORS/HLS do provedor; canais que exigem headers
  específicos só tocam pelo app (proxy embutido).
- GitHub Pages é estático: nenhuma lógica secreta pode morar ali.

---

## 7. App web/PWA (pasta `web/`)

Além da landing/SPA acima, o repositório agora tem uma versão **web + PWA**
independente em [`web/`](../web/), com paridade com o app Android:

- landing de vendas em `web/landing/`;
- app instalável em `web/app/` (manifest, service worker, ícones PNG, prints);
- player HLS/MPEG-TS/DASH/MP4, heartbeat de sessão, limite de 1 tela, 2 dispositivos;
- login, catálogo paginado, categorias (com busca), A-Z, favoritos, continuar assistindo com carrossel na home;
- **Provisionamento automático da playlist**: o app usa `PLAYLIST_URL` embutida
  (somente build privado) ou `GET /player/playlist` (mesma rota do Android) e
  baixa a URL licenciada direto no navegador; se o CORS bloquear, usa
  `GET /player/playlist-text`. Não há tela de importação para o assinante. O
  parser é incremental, aceita até 250.000 itens, lê `#EXTVLCOPT`/`#EXTHTTP`/
  `#KODIPROP` e headers na URL; a grade mostra 240 cards por vez com
  **Mostrar mais**;
- **Modo self-hosted**: `source.js` detecta o `server.py` na mesma origem ou em
  `PROXY_URL`, carrega o catálogo magro (`/api/catalogo.json`), resolve a fonte
  sob demanda (`/api/canal?slug=`) e usa o proxy com headers/DoH/Range. O player
  tenta proxy↔direto, HLS derivado de `.ts` e backoff exponencial;
- aviso de fim do teste grátis (`TRIAL_NUDGE_DAYS`, uma vez por dia) e ajuste de
  overscan de TV (aplicado à interface, não ao player em tela cheia);
- checkout Mercado Pago com retorno em `web/app/checkout.html`;
- modo demonstração (`?demo=1`) e vídeo local `web/app/assets/media/demo.mp4`.

Os canais **não são embutidos** no APK nem no repositório. No Android de
release, `PlaylistConfig.PLAYLIST_URL` fica vazio e o app busca
`/player/playlist` depois do login; em debug, a URL pode vir de
`local.properties`. O PWA segue o mesmo modelo: sem `PLAYLIST_URL` no build
público, depende do backend, de um build privado ou do modo self-hosted. O
catálogo fica no IndexedDB local (cache versão 3) e é apagado no logout. Versão
publicada: **1.2.0**, service worker **`eftv-web-v8`**. Hoje o Render recebe uma
página do nginx do provedor; para o live funcionar sem build privado, é preciso
popular o cache da playlist no backend
(`backend/scripts/upload_playlist_cache.py`).

Documentação completa: [`web/README.md`](../web/README.md) e
[`web/CONTINUAR.md`](../web/CONTINUAR.md).

Publicação: GitHub Pages já serve a pasta; acesse `/web/landing/` e `/web/app/`.
O service worker exige HTTPS (ou localhost). Para testar localmente:

```bash
node web/tools/servidor.js . 4173
```
