# EFTV — Versão Web + PWA

Versão web do EFTV (canais ao vivo, filmes e séries) com **landing page** de vendas e **app instalável (PWA)**. O app Android em `android/` não foi alterado.

> **Status:** interface e fluxos completos, com **modo demonstração** quando o backend não responde. A integração com a API real já está implementada, mas ainda precisa ser validada com o backend em produção (ver `CONTINUAR.md`).

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
│       │   ├── config.js        # API_URL, versão, intervalos
│       │   ├── store.js         # localStorage (sessão, favoritos, progresso)
│       │   ├── api.js           # Cliente da API FastAPI
│       │   ├── catalog.js       # Catálogo, busca sem acento, categorias, A-Z
│       │   ├── player.js        # HLS / MPEG-TS / DASH / MP4
│       │   ├── app.js           # Router, telas, auth, conta, ajustes
│       │   └── pwa.js           # Instalação + service worker
│       ├── img/                 # Ícones PNG, poster, prints reais (screens/)
│       └── media/demo.mp4       # Vídeo de demonstração (12s, ~90 KB)
└── tools/
    ├── servidor.js              # Servidor estático local (sem dependências)
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

---

## 3. Configuração da API

Edite `web/app/assets/js/config.js`:

```js
window.EFTV_CONFIG = {
  API_URL: "https://eftv.onrender.com", // troque por https://api.eftv.com.br em produção
  APP_VERSION: "1.0.0",
  APP_VERSION_CODE: 1,
  DEMO_FALLBACK: true,  // ⚠️ deixe false em produção
  HEARTBEAT_MS: 45000,
  PROGRESS_SAVE_MS: 5000,
  PAGE_SIZE: 60,
};
```

Também é possível trocar a URL sem editar o arquivo:

```js
localStorage.setItem("eftv_api_url", "https://api.eftv.com.br");
```

**Antes de publicar:** defina `DEMO_FALLBACK: false`. Com `true`, falhas de rede liberam o app em modo demonstração — ótimo para testar, ruim para produção.

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
| Canais | `GET /channels?page=&page_size=&category_id=&search=&is_live=&include_adult=` | paginado, máx. 100/página; o app busca todas as páginas |
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

**Campos do catálogo normalizados:** `name`, `slug`, `group_title`, `category_id`, `logo_url`, `is_live`, `is_adult`, `stream_url`, `stream_type`.

---

## 5. Funcionalidades (paridade com o Android)

- Login, cadastro, confirmação de e-mail, esqueci/redefinir senha.
- Catálogo com busca **sem acento**, categorias com contagem, filtro de conteúdo adulto.
- Índice **A-Z** nos canais ao vivo.
- Favoritos, recentes e **continuar assistindo** (progresso salvo a cada ~1%).
- Player **HLS (hls.js), MPEG-TS (mpegts.js), DASH (dash.js) e MP4**, com:
  - qualidade, faixa de áudio e legenda;
  - voltar 10 s / avançar 10 s, mudo, tela cheia, Picture-in-Picture;
  - “Voltar ao vivo”, reconexão automática e retry;
  - heartbeat de sessão e encerramento no fechamento.
- Limite de **1 tela simultânea** (tratamento de `403 stream_limit` e `409 session_closed`).
- Limite de **2 dispositivos**, com lista e desvincular todos.
- Assinatura: status, validade, dias restantes, checkout Mercado Pago, cancelamento e “restaurar compras”.
- Ajustes: conteúdo adulto, modo TV (foco ampliado), economia de dados, autoplay, limpar cache.
- Instalação PWA (Android/Chrome/Edge e instruções para iPhone/Safari).
- Deep link `?canal=slug` / `?id=UUID` e retorno de pagamento em `checkout.html`.
- Login por código para TV (quando o backend expõe `/auth/device-code`).
- Modo demonstração completo (`?demo=1`) com catálogo de exemplo e vídeo local.

### Diferenças inevitáveis em relação ao Android

- **Downloads offline de vídeo** não são possíveis no navegador (o PWA guarda apenas a casca/interface).
- **Canais que exigem headers/User-Agent específicos ou proxy local** só funcionam no app Android, por causa de CORS.
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
- Ao publicar uma nova versão, incremente `CACHE` em `sw.js` (`eftv-web-v2` → `v3`) para limpar caches antigos.

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

O app usa `API_URL` em `config.js`. Garanta CORS liberado para o domínio da landing/app no FastAPI (`ALLOWED_ORIGINS`).

---

## 9. Limitações e cuidados

- **CORS:** se o provedor de streams não liberar o domínio web, o canal não toca no navegador (toque no app Android). Não há proxy no cliente web.
- **Autoplay:** navegadores bloqueiam áudio automático; o usuário pode precisar tocar em ▶.
- **iOS:** instalação é manual (Compartilhar → Adicionar à Tela de Início) e HLS usa o player nativo.
- **Direitos autorais:** o catálogo é agregado de terceiros. Antes de promover comercialmente, confirme licenciamento/autorização dos sinais. Este projeto não concede direitos sobre o conteúdo.
- **Modo demonstração:** não cobre pagamentos reais e usa catálogo/vídeo de exemplo.

---

## 10. Próximos passos

Veja `CONTINUAR.md` para o checklist detalhado. Resumo:

1. Validar login/catálogo/player/checkout contra o backend real.
2. Trocar `demo.mp4` e os canais de exemplo por conteúdo autorizado.
3. Testar em Android Chrome, iPhone Safari e desktop.
4. Configurar CORS e `DEMO_FALLBACK: false` em produção.
5. Opcional: empacotar como TWA (Bubblewrap) para publicar na Play Store.
