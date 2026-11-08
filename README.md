# EFTV — Plataforma de Streaming por Assinatura

> Transformação da EFTV de player local M3U para SaaS de streaming com catálogo centralizado, usuários, assinaturas e pagamentos.

## 📁 Estrutura do Projeto

```
EFTV/
├── frontend/                 # Deploy: Cloudflare Pages
│   ├── public/              # Arquivos estáticos
│   │   ├── index.html       # Landing page
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── plans.html
│   │   ├── account.html     # Área do assinante
│   │   ├── player.html      # Player (HLS/DASH/TS/MP4)
│   │   ├── manifest.webmanifest
│   │   ├── sw.js            # Service Worker
│   │   └── assets/
│   │       ├── css/style.css
│   │       └── js/          # ES Modules (api, auth, catalog, account, player, utils)
│   ├── package.json
│   └── vite.config.js
│
├── backend/                  # Deploy: Render (FastAPI)
│   ├── app/
│   │   ├── main.py          # FastAPI app + lifespan + routers
│   │   ├── config.py        # Settings (pydantic-settings)
│   │   ├── database.py      # SQLAlchemy async + session
│   │   ├── models/          # SQLAlchemy models
│   │   │   ├── user.py
│   │   │   ├── plan.py
│   │   │   ├── subscription.py
│   │   │   ├── payment.py
│   │   │   ├── category.py
│   │   │   ├── channel.py
│   │   │   └── playback_session.py
│   │   ├── schemas/         # Pydantic schemas
│   │   ├── routes/          # API routes
│   │   │   ├── auth.py      # /auth/register, /login, /me, /refresh
│   │   │   ├── plans.py     # /plans (público + admin)
│   │   │   ├── channels.py  # /channels, /channels/{slug}/play
│   │   │   ├── categories.py
│   │   │   ├── subscriptions.py # /subscriptions, webhook MP
│   │   │   └── admin.py     # /admin/* (protegido)
│   │   ├── services/        # Business logic
│   │   │   ├── auth_service.py    # JWT, bcrypt
│   │   │   ├── mercadopago.py     # Checkout, webhooks
│   │   │   ├── streaming.py       # Tokens CDN
│   │   │   └── catalog.py
│   │   ├── security/        # Dependencies (get_current_user, rate_limit)
│   │   └── tasks/           # Background jobs (APScheduler)
│   ├── alembic/             # Migrations
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── streaming/               # Docs/config infra streaming
├── docs/                    # Documentação
├── docker-compose.yml       # Dev local (API + Postgres + Redis + Frontend)
└── .github/workflows/       # CI/CD
```

## 🚀 Início Rápido (Desenvolvimento)

### Pré-requisitos
- Docker + Docker Compose
- Node.js 20+ (para frontend build)
- Python 3.11+ (para backend local sem Docker)

### 1. Clone e configure
```bash
git clone https://github.com/EvertonFagundes/eftv
cd EFTV

# Backend
cp backend/.env.example backend/.env
# Edite backend/.env com suas chaves (SECRET_KEY, Mercado Pago, etc.)
```

### 2. Suba o ambiente de desenvolvimento
```bash
docker compose up -d
```

Serviços disponíveis:
- **Frontend**: http://localhost:3000 (Vite dev server com proxy `/api` → backend)
- **Backend API**: http://localhost:8000
- **Docs API**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432 (user: postgres, pass: postgres, db: eftv)
- **Redis**: localhost:6379

### 3. Execute migrações
```bash
docker compose exec backend alembic upgrade head
```

### 4. Crie planos no Mercado Pago (sandbox)
1. Acesse https://www.mercadopago.com.br/developers/panel
2. Crie planos de assinatura (preapproval plans)
3. Copie os `preapproval_plan_id` para o `.env` ou cadastre via admin

## 🔧 Scripts Úteis

```bash
# Backend
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload          # Dev server
alembic revision --autogenerate -m "msg"  # Nova migration
alembic upgrade head                   # Aplica migrations
pytest                                 # Testes

# Frontend
cd frontend
npm install
npm run dev                            # Dev server (porta 3000)
npm run build                          # Build produção (pasta dist/)
npm run preview                        # Preview build
```

## 🌐 Deploy Produção

### Backend → Render
1. Conecte repo GitHub no Render
2. New Web Service → Docker
3. Variáveis de ambiente (Settings → Environment):
   - `DATABASE_URL` (Postgres do Supabase, pooler na porta 6543)
   - `SECRET_KEY` (gere: `openssl rand -hex 32`)
   - `IPTV_PLAYLIST_URL` (playlist licenciada; nunca no repositório)
   - `EMAIL_PROVIDER=brevo`, `BREVO_API_KEY` e `EMAIL_FROM`
     (o remetente precisa estar verificado no Brevo)
   - `FRONTEND_URL=https://evertonfagundes.github.io/eftv`
   - `CORS_ORIGINS=https://evertonfagundes.github.io`
     (aceita uma URL, lista separada por vírgula ou JSON)
   - `ENVIRONMENT=production`
   - `DEBUG=false`
   - `MERCADOPAGO_ACCESS_TOKEN`, `MERCADOPAGO_PUBLIC_KEY`,
     `MERCADOPAGO_WEBHOOK_SECRET` e `MERCADOPAGO_SANDBOX=false`
     (somente quando o pagamento for ativado)

### Frontend → Cloudflare Pages
1. Connect repository → `frontend` folder
2. Build command: `npm run build`
2. Output directory: `dist`
3. Environment variables:
   - `VITE_API_URL=https://api.eftv.com.br`

### Banco de Dados
- **Supabase free** (sem cota de horas; ver [`docs/PLANO-GRATUITO.md`](docs/PLANO-GRATUITO.md))
- Execute `alembic upgrade head` após primeiro deploy
- Backup noturno cifrado em `.github/workflows/backup.yml`
  (segredos `DATABASE_URL` e `BACKUP_PASSPHRASE`)

> Para operar com usuários reais sem custo mensal (Supabase free + Brevo +
> backup + etapas de go-live), siga [`docs/PLANO-GRATUITO.md`](docs/PLANO-GRATUITO.md).

### DNS (Cloudflare)
| Tipo | Nome | Conteúdo | Proxy |
|------|------|----------|-------|
| CNAME | eftv.com.br | `<pages-project>.pages.dev` | 🟠 Proxied |
| CNAME | app.eftv.com.br | `<pages-project>.pages.dev` | 🟠 Proxied |
| CNAME | api.eftv.com.br | `<render-service>.onrender.com` | 🟠 Proxied |

## 💳 Mercado Pago - Configuração

### Sandbox (Desenvolvimento)
- Use credenciais de teste do painel developers
- `MERCADOPAGO_SANDBOX=true`
- Webhook URL: `https://api.eftv.com.br/subscriptions/webhook/mercadopago` (configure no painel MP)

### Produção
- Conta **Mercado Pago Business** verificada
- Chaves de produção (não sandbox)
- Configure webhook de produção
- Teste fluxo completo: PIX → webhook → ativação

## 📺 Streaming - Cloudflare Stream

1. Ative Cloudflare Stream na conta
2. Configure **Token Auth** (Signed URLs)
3. Upload canais via API ou dashboard
4. Configure `stream_url` nos canais (admin)
5. Player recebe token JWT curto (15 min) no header `Authorization`

## 📋 Roadmap (Fases)

| Fase | Status | Descrição |
|------|--------|-----------|
| 1. Fundação | 🚧 Em andamento | Backend, DB, Auth, Docker, CI/CD |
| 2. Assinaturas | ⏳ Pendente | Mercado Pago, webhooks, planos, conta |
| 3. Catálogo/Player | ⏳ Pendente | Canais admin, token stream, sessões |
| 4. Streaming | ⏳ Pendente | Cloudflare Stream, ABR, testes carga |
| 5. Produção | ⏳ Pendente | Domínio, HTTPS, monitoramento, segurança |
| 6. Pós-lançamento | ⏳ Pendente | Analytics, referral, app nativo, EPG |

## 🔐 Variáveis de Ambiente Críticas

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `SECRET_KEY` | ✅ | Chave JWT (32+ chars, `openssl rand -hex 32`) |
| `DATABASE_URL` | ✅ | PostgreSQL async connection string |
| `IPTV_PLAYLIST_URL` | ✅ | Playlist licenciada entregue só pelo backend |
| `MERCADOPAGO_ACCESS_TOKEN` | Quando ativar pagamento | Token de acesso MP (produção/sandbox) |
| `MERCADOPAGO_WEBHOOK_SECRET` | Quando ativar pagamento | Validação HMAC webhooks |
| `CLOUDFLARE_ACCOUNT_ID` | Para streaming | Account ID do Cloudflare Stream |
| `CLOUDFLARE_API_TOKEN` | Para streaming | API Token com permissão Stream |
| `EMAIL_PROVIDER` | ✅ | `auto`, `brevo`, `resend` ou `dev` |
| `BREVO_API_KEY` | Para emails | API Key do Brevo |
| `EMAIL_FROM` | Para emails | Remetente verificado no provedor |
| `CORS_ORIGINS` | ✅ | URL(s) do frontend (vírgula ou JSON) |
| `FRONTEND_URL` | ✅ | URL do frontend (para CORS, links emails) |

## 📝 Licença

Projeto proprietário — EFTV. Todos os direitos reservados.

---

**Desenvolvido por Everton Fagundes** — [GitHub](https://github.com/EvertonFagundes)