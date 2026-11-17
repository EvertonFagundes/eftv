# Pagamentos EFTV — runbook

Como o cobrança funciona, o que é automático e o que conferir quando alguém
pagar de verdade.

## Fluxo

1. Usuário verificou o e-mail → **trial de 7 dias**.
2. ⋮ → Minha assinatura → **Assinar** → `POST /subscriptions/checkout`.
3. O Mercado Pago recusa a preapproval direta com frequência → o backend cai
   no **fluxo por plano** (`preapproval_plan`), que é o caminho de produção.
4. O app abre o `init_point` no navegador; só **cartão de crédito**
   (`payment_methods_allowed`).
5. Pagamento aprovado → assinatura vira `active`, `has_access=true`.

## Como o acesso é liberado (3 caminhos, todos independentes)

| Caminho | Quando roda | O que faz |
|---|---|---|
| Webhook `subscription_preapproval` | Evento do MP (só chega se `notification_url` foi aceito na criação) | Ativa assinatura |
| Webhook `subscription_authorized_payment` | Cobrança aprovada | Grava `Payment` (bandeira + últimos 4) |
| **Conciliação** `sync_pending_subscriptions` | A cada 5 min + botão "Atualizar status" + ao abrir "Minha assinatura" | Busca a preapproval do usuário, ativa e **grava o `Payment` via `/authorized_payments/search`** |
| Renovação `check_expired_subscriptions` | A cada 30 min | Consulta `next_billing_date`, renova e grava a cobrança da renovação |

O webhook é **otimização**; sem ele tudo funciona pela conciliação (até 5 min
de atraso). Por isso não é necessário cadastrar webhook no painel do MP.

## Compra de teste (E2E)

Conta de teste: `evertonfagundes1510+compra@gmail.com` / `EftvCompra2026`
(plus-addressing: o e-mail de verificação cai no Gmail normal).

1. Clicar no link de verificação do e-mail → trial ativo.
2. No app: sair da conta principal, entrar com a conta de teste.
3. ⋮ → Minha assinatura → Assinar → pagar R$ 19,90.
4. Conferir:

```
curl -H "Authorization: Bearer <token>" https://eftv.onrender.com/subscriptions/current
```

Esperado: `status: "active"`, `has_access: true`, `payment_method`,
`payment_last_four`. No app, a linha "Pagamento: cartão …" deve aparecer.

5. Se ficou `pending` por mais de 5 minutos: botão **Atualizar status** e
   olhar os logs do Render (`sync`, `Webhook`, `conciliac`).

## Cancelamento

- App: Minha assinatura → **Cancelar** → `POST /subscriptions/{id}/cancel`.
- O backend grava `cancel_at_period_end` **e cancela no Mercado Pago**
  (`PUT /preapproval/{id}` com `status=cancelled`). Se a chamada ao MP falhar,
  o cancelamento local segue valendo e o erro vai para os logs.
- Quem cancelou **mantém o acesso até o fim do período pago** (não corta na
  hora). Ao vencer, o verificador marca `cancelled` e **não renova**, mesmo
  que o MP ainda diga `authorized`.
- Webhook de preapproval `cancelled` também preserva o acesso restante.

## Limite de telas (1 stream por conta)

O plano vendido é de 2 aparelhos **e 1 tela por vez**. O limite é aplicado no
servidor, não no app:

| Momento | Rota | Efeito |
|---|---|---|
| Abre o player | `POST /player/play` | Abre/reaproveita a sessão do aparelho; 403 `stream_limit` se já houver outra tela ativa |
| Enquanto assiste | `POST /player/heartbeat` (a cada ~45 s) | Mantém a vaga; 409 `session_closed` encerra |
| Sai do player | `POST /player/stop` | Libera a vaga na hora |
| Esqueceu aberto / perdeu rede | tarefa horária | Sessão sem heartbeat por 120 s expira sozinha |

- Trocar de canal no **mesmo** aparelho reaproveita a sessão (não gasta vaga).
- Se a API falhar (rede/erro interno), o app **não bloqueia** a reprodução:
  preferimos entregar o canal a punir o pagante por um erro nosso.
- O banco guarda apenas o **hash** da URL do canal (`channel_ref`), nunca a URL
  com as credenciais do provedor.

## Atualização do app (fora da Play Store)

O app consulta `GET /app/version` uma vez por dia. Para publicar uma versão:

1. Suba o APK em algum lugar público (GitHub Releases serve) e copie a URL.
2. No Render → Environment, ajuste:

| Variável | Exemplo | Uso |
|---|---|---|
| `APP_LATEST_VERSION_CODE` | `11` | Tem que ser **maior** que o `versionCode` instalado |
| `APP_LATEST_VERSION_NAME` | `1.1.9` | Texto mostrado no diálogo |
| `APP_APK_URL` | `https://github.com/.../app-release.apk` | Link direto do arquivo |
| `APP_UPDATE_NOTES` | `Correções no player` | Aparece abaixo da mensagem |
| `APP_UPDATE_MANDATORY` | `false` | `true` = sem botão "Depois" |

Sem `APP_APK_URL` (ou com code `0`) o endpoint devolve
`update_available_from: false` e o app não pergunta nada.

## Avisos automáticos por e-mail

`send_lifecycle_emails` roda a cada 6 h:

- **Teste acabando** (24 h antes): manda o link de assinatura. Marca
  `subscriptions.trial_reminder_sent_at` para não repetir.
- **Cartão recusado** (`past_due`): pede atualização do cartão. Marca
  `payment_failed_notified_at`.
- **Cancelamento**: e-mail na hora da rota, com a data até quando o acesso vale.

Se o provedor de e-mail falhar, a marca **não** é gravada: o aviso tenta de
novo no próximo ciclo.

## Erros e travamentos do app

- App: handler global envia `POST /app/crashes` (versão, aparelho, Android,
  stacktrace). Tempo máximo de espera: 2 s, para não travar o fechamento.
- Backend: grava em `client_errors` e escreve um `WARNING` no log.
- Suporte: `GET /admin/crashes?page=1&page_size=20` (admin).
- Desligar sem deploy: `CLIENT_ERRORS_ENABLED=false`.

## Painel admin (suporte)

| Endpoint | Uso |
|---|---|
| `GET /admin/payments` | "O cliente pagou?" — cobranças com e-mail, status e id do MP |
| `GET /admin/users/{id}` | Usuário + assinaturas + **cobranças** + aparelhos |
| `POST /admin/subscriptions/{id}/sync` | Concilia na hora com o MP (cliente pagou e não liberou) |
| `GET /admin/stats` | Totais: usuários, assinaturas ativas |
| `GET /admin/crashes` | Travamentos relatados pelo app (mais recentes primeiro) |

## Checagens de saúde

- `https://eftv.onrender.com/health` → `mercadopago_configured: true`,
  `mercadopago_token_kind: "production"`, `mercadopago_sandbox: false`,
  `mercadopago_account.is_test_user: false`.

## Segredos e backup

- `android/eftv-release.jks` + `android/keystore.properties` **não estão no
  Git** (nunca devem estar). Backup local:
  `C:\Users\evert\Documents\EFTV-keystore-backup\` (+ zip datado).
  Copiar também para nuvem/pen drive — sem essa chave não há como atualizar
  quem já instalou o app.
- `MERCADOPAGO_ACCESS_TOKEN` e `SECRET_KEY` vivem só no Render.

## Limite da conta de teste do MP

Conta coletora de teste não cobra cliente real ("Both payer and collector
must be real or test users"). O backend detecta via `is_test_user` e devolve
503 `payments_unavailable` em vez de mandar o cliente para um checkout que
sempre falha.
