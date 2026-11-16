# Pagamentos (Mercado Pago)

## Situacao atual (16/11/2026)

O checkout esta **bloqueado de proposito** para clientes reais, porque a
credencial configurada no Render pertence a um **usuario de teste** do
Mercado Pago (`TESTUSER...`, tag `test_user`).

O Mercado Pago recusa qualquer cobranca quando o coletor e de teste e o
pagador e real:

```
400 {"message":"Both payer and collector must be real or test users"}
```

Enquanto isso, `POST /subscriptions/checkout` responde:

```
503 {"detail":{"code":"payments_unavailable","message":"O pagamento esta temporariamente indisponivel..."}}
```

e o app mostra exatamente essa mensagem. Nada e cobrado e ninguem fica com
uma tela de pagamento que sempre falha.

Confira a qualquer momento em `https://eftv.onrender.com/health`:

```json
"mercadopago_token_kind": "production",
"mercadopago_sandbox": true,
"mercadopago_account": { "is_test_user": true, "site_id": "MLB", "country_id": "BR" }
```

`mercadopago_token_kind` ser `production` **nao** garante conta real: o que
vale e `mercadopago_account.is_test_user`.

## Como liberar o pagamento (passo a passo)

1. Saia da conta de teste no Mercado Pago (ou use uma janela anonima).
2. Entre em <https://www.mercadopago.com.br/developers/panel> com a **conta
   Mercado Pago real** que vai receber o dinheiro (a mesma do CNPJ/CPF).
3. Crie (ou abra) a aplicacao `EFTV`.
4. Em **Credenciais de producao**, copie o **Access Token** (comeca com
   `APP_USR-`).
5. No Render, servico `eftv` > **Environment**:
   - `MERCADOPAGO_ACCESS_TOKEN` = o token copiado
   - `MERCADOPAGO_SANDBOX` = `false`
6. Salve e aguarde o redeploy (~2 min).
7. Confirme em `/health` que `mercadopago_account.is_test_user` virou
   `false`.
8. No painel da aplicacao, cadastre a URL de notificacao (webhook):
   `https://eftv.onrender.com/subscriptions/webhook/mercadopago?source_news=webhooks`
   e os eventos `subscription_preapproval` e `subscription_authorized_payment`.
9. Se o painel mostrar uma **chave secreta do webhook**, coloque em
   `MERCADOPAGO_WEBHOOK_SECRET`.
10. Faca uma compra real de R$ 19,90 com seu cartao, confirme que:
    - o webhook chega (logs do Render),
    - `GET /subscriptions/current` fica `status=active` e `has_access=true`,
    - o app libera o catalogo sem reiniciar.

> A conta real precisa ter identidade verificada e meio de recebimento
> cadastrado, senao o Mercado Pago recusa criar a assinatura.

## Como o fluxo funciona

1. O app chama `POST /subscriptions/checkout` e recebe `init_point`.
2. O cliente paga no navegador (Mercado Pago coleta o cartao).
3. O Mercado Pago chama o webhook; o backend busca a assinatura na fonte e
   grava `mercadopago_subscription_id`, status e fim do periodo.
4. O botao **Atualizar status** do app forca a sincronizacao, caso o webhook
   atrase. No fluxo por plano a assinatura e localizada pelo
   `external_reference` do app ou pelo e-mail do pagador.

## Plano

- Nome: Mensal
- Preco: R$ 19,90
- 2 aparelhos, 1 stream simultaneo
- Trial: 7 dias (`FREE_TRIAL_DAYS=7`)

O plano do Mercado Pago (`preapproval_plan`) e criado automaticamente no
primeiro checkout e guardado em `plans.mercadopago_plan_id`. Trocar preco
exige atualizar o valor no Mercado Pago (o plano antigo continua valendo para
quem ja assinou).
