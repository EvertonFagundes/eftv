# API EFTV — referência rápida

Base: `https://eftv.onrender.com` · FastAPI · docs interativas em `/docs`
(somente com `DEBUG=true`).

Autenticação: `Authorization: Bearer <access_token>` (15 min) + renovação em
`/auth/refresh`. App Android envia também `X-Device-Id` (obrigatório nas rotas de
player e de assinatura).

---

## Autenticação — `/auth`

| Método | Rota | Uso |
|---|---|---|
| POST | `/auth/register` | cria conta (7 dias de teste após confirmar e-mail) |
| POST | `/auth/verify-email` | confirma e-mail pelo token |
| POST | `/auth/resend-verification` | reenvia confirmação |
| POST | `/auth/forgot-password` | envia código de recuperação |
| POST | `/auth/reset-password` | troca a senha com o código |
| POST | `/auth/login` | e-mail + senha → tokens |
| POST | `/auth/refresh` | renova o access (body JSON ou cookie `HttpOnly`) |
| POST | `/auth/logout` | limpa o cookie de refresh |
| GET/PATCH | `/auth/me` | dados da conta |
| POST | `/auth/device-code` | **TV** pede um código de 8 caracteres |
| POST | `/auth/device-code/poll` | TV pergunta se já foi autorizada (tokens saem uma vez) |
| POST | `/auth/device-code/approve` | celular logado autoriza a TV |

Código da TV: sem `0/O` e `1/I`, exibido como `ABCD-EFGH`, expira em
`DEVICE_CODE_TTL_MINUTES` (10) e só vale uma vez.

---

## Player — `/player`

| Método | Rota | Uso |
|---|---|---|
| GET | `/player/playlist` | URL autorizada da playlist + user-agent/referer |
| GET | `/player/device` | status do vínculo deste aparelho |
| POST | `/player/device/revoke` | desvincula este aparelho |
| POST | `/player/device/revoke-all` | desvincula todos (troca/reinstalação) |
| POST | `/player/play` | abre a sessão de tela; `403 stream_limit` se já houver outra |
| POST | `/player/heartbeat` | renova a sessão (~45 s) |
| POST | `/player/stop` | encerra e libera a vaga |

Erros do limite de tela vêm como `detail.code`: `stream_limit`,
`session_closed`.

---

## Assinaturas — `/subscriptions`

| Método | Rota | Uso |
|---|---|---|
| GET | `/subscriptions` | histórico do usuário |
| GET | `/subscriptions/current` | status, dias restantes, pagamento |
| GET | `/subscriptions/{id}` | detalhe |
| POST | `/subscriptions/checkout` | cria a preferência do Mercado Pago (`init_point`) |
| POST | `/subscriptions/{id}/cancel` | cancela local **e** no MP (acesso até o fim do período) |
| POST | `/subscriptions/webhook/mercadopago` | webhook (otimização; conciliação cobre a falta) |

Conciliação: `sync_pending_subscriptions` a cada 5 min; renovação/expiração:
`check_expired_subscriptions` a cada 30 min.

---

## App — `/app`

| Método | Rota | Uso |
|---|---|---|
| GET | `/app/version` | última versão publicada (atualização por APK) |
| POST | `/app/crashes` | relato de erro/travamento do app (público, limitado por tamanho) |

`/app/version` devolve `update_available_from: false` quando `APP_APK_URL` não
está configurado.

---

## Planos, canais e categorias

| Método | Rota | Uso |
|---|---|---|
| GET | `/plans` | planos públicos |
| GET | `/plans/{id}` | detalhe |
| GET | `/channels` | catálogo paginado/filtrado |
| GET | `/channels/{slug}` | detalhe |
| GET | `/channels/{slug}/play` | URL de reprodução autorizada |
| GET | `/categories` | categorias |
| GET | `/categories/{id}` | detalhe |

Rotas de criação/edição de plano, canal e categoria exigem admin.

---

## Admin — `/admin` (somente admin)

| Método | Rota | Uso |
|---|---|---|
| GET | `/admin/stats` | totais de usuários/assinaturas |
| GET | `/admin/users` | lista de usuários |
| GET | `/admin/users/{id}` | usuário + assinaturas + cobranças + aparelhos |
| GET | `/admin/payments` | "o cliente pagou?" |
| GET | `/admin/crashes` | travamentos relatados pelo app |
| GET | `/admin/streams` | quem está assistindo agora (limite de telas) |
| POST | `/admin/subscriptions/{id}/sync` | concilia na hora com o MP |
| POST | `/admin/users/{id}/devices/revoke` | libera aparelhos do cliente |
| PATCH | `/admin/users/{id}/toggle-admin` | promove/remove admin |
| PATCH | `/admin/users/{id}/toggle-active` | bloqueia/desbloqueia conta |
| POST | `/admin/users/{id}/make-owner` | transfere a propriedade |
| POST | `/admin/claim-ownership` | primeiro admin |

---

## Saúde e diagnóstico

`GET /health` — sem autenticação: status, versão, ambiente, `frontend_url`,
`checkout_back_url`, configuração/validade do Mercado Pago, `client_ip` visto pelo
servidor, limite de aparelhos e versão publicada do app.

---

## Modelos relevantes

- `users` — conta, e-mail verificado, admin, ativo.
- `subscriptions` — status (`trial`, `active`, `past_due`, `cancelled`, `expired`),
  período, `cancel_at_period_end`, avisos enviados (`trial_reminder_sent_at`,
  `payment_failed_notified_at`).
- `payments` — cobranças do Mercado Pago (bandeira + últimos 4).
- `subscription_devices` — aparelhos vinculados (máx. 2).
- `stream_sessions` — telas ativas (hash da URL do canal, heartbeat).
- `device_login_codes` — códigos de login da TV.
- `client_errors` — travamentos relatados pelo app.
