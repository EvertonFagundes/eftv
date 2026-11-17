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

## Painel admin (suporte)

| Endpoint | Uso |
|---|---|
| `GET /admin/payments` | "O cliente pagou?" — cobranças com e-mail, status e id do MP |
| `GET /admin/users/{id}` | Usuário + assinaturas + **cobranças** + aparelhos |
| `POST /admin/subscriptions/{id}/sync` | Concilia na hora com o MP (cliente pagou e não liberou) |
| `GET /admin/stats` | Totais: usuários, assinaturas ativas |

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
