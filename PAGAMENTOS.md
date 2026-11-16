# Pagamentos (Mercado Pago)

## Situacao atual (16/11/2026)

**Producao ativa.** A conta coletora e real (`is_test_user: false`) e o
checkout ja abre com o plano *EFTV - Mensal*, R$ 19,90/mes.

Confira em `https://eftv.onrender.com/health`:

```json
"mercadopago_token_kind": "production",
"mercadopago_sandbox": false,
"mercadopago_account": { "is_test_user": false, "site_id": "MLB", "country_id": "BR" }
```

Se `is_test_user` voltar a `true`, o checkout responde
`503 payments_unavailable` e o app mostra a mensagem de indisponibilidade em
vez de abrir uma tela de pagamento que o Mercado Pago recusaria no fim.

## Fluxo

1. O app chama `POST /subscriptions/checkout` e recebe `init_point`.
2. O cliente paga no navegador (o Mercado Pago coleta o cartao).
3. O Mercado Pago chama o webhook; o backend busca a assinatura na fonte e
   grava `mercadopago_subscription_id`, status e fim do periodo.
4. O botao **Atualizar status** do app forca a sincronizacao, caso o webhook
   atrase. No fluxo por plano a assinatura e localizada pelo
   `external_reference` do app ou pelo e-mail do pagador.

## Duas formas de criar o checkout

- **Preapproval direta** (`/preapproval`): exige `payer_email` de uma conta
  Mercado Pago existente. Usada primeiro, porque ja amarra a assinatura ao
  usuario na criacao.
- **Plano** (`/preapproval_plan`): fallback quando a direta e recusada. Gera
  um link reutilizavel onde o Mercado Pago pede o e-mail e o cartao. O id do
  plano fica em `plans.mercadopago_plan_id`.

Ao trocar o token (teste -> producao), o plano antigo pertence ao coletor
anterior e e **recriado automaticamente** na proxima chamada, porque o
backend valida `collector_id` contra a conta atual.

## Webhook

URL a cadastrar no painel da aplicacao:

```
https://eftv.onrender.com/subscriptions/webhook/mercadopago?source_news=webhooks
```

Eventos: `subscription_preapproval` e `subscription_authorized_payment`.
Se o painel mostrar uma chave secreta, coloque em
`MERCADOPAGO_WEBHOOK_SECRET`.

## Plano

- Nome: Mensal
- Preco: R$ 19,90
- 2 aparelhos, 1 stream simultaneo
- Trial: 7 dias (`FREE_TRIAL_DAYS=7`)

Trocar o preco exige criar um plano novo no Mercado Pago: o plano antigo
continua valendo para quem ja assinou. Para forcar a recriacao, zere
`plans.mercadopago_plan_id` no banco.

## Variaveis no Render

- `MERCADOPAGO_ACCESS_TOKEN` — token de **producao** da aplicacao
- `MERCADOPAGO_SANDBOX=false`
- `FRONTEND_URL` — site que hospeda `checkout.html`
- `API_BASE_URL` — usada no `notification_url` do webhook
