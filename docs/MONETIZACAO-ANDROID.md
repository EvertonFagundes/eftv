# Análise de monetização — app Android EFTV

> Revisão feita em novembro/2026, focada em **receita recorrente** (R$ 19,90/mês),
> retenção e riscos de distribuição. A versão web não foi tratada como canal
> comercial (uso pessoal).

## 1. Resumo executivo

O app já tem a base certa: login, trial de 7 dias, assinatura recorrente no
Mercado Pago, limite de aparelhos, limite de telas e bloqueio de catálogo para
quem não paga. O que estava faltando eram os **fechamentos do ciclo**:

| Risco encontrado | Impacto | Situação |
|---|---|---|
| Player ignorava 401/403 e continuava tocando o canal em cache | Assinatura vencida continuava assistindo | **Corrigido** |
| Retorno do Mercado Pago não reabria o app (deep link sem tratamento) | Cliente pagava e não sabia se liberou; perda de conversão | **Corrigido** |
| Tokens de sessão em texto puro no `SharedPreferences` | Cópia de sessão / conta compartilhada | **Corrigido** (Keystore) |
| Nenhum aviso de fim do trial dentro do app | Cliente descobria o vencimento só quando o canal parava | **Corrigido** |
| Botão "Continuar sem assinatura (demonstração)" sem ação no login | Sugeria acesso grátis e não fazia nada | **Removido** |
| Sem keystore de release no repositório | Sem chave não há atualização para quem já instalou | **Pendente (bloqueador)** |
| Trial pode ser repetido com contas novas no mesmo aparelho | Receita perdida de forma sistemática | **Pendente (backend)** |
| Proxy local em `127.0.0.1:8124` sem autenticação | Outro app do aparelho pode usar o proxy / ler a playlist local | **Recomendado** |
| Endpoint público de crash sem rate limit | Spam no banco | **Recomendado** |

## 2. O que foi alterado nesta rodada

### Dinheiro entrando

- `android/.../PlayerActivity.kt`
  - `/player/play` e heartbeat com **401/403** agora pausam o vídeo e abrem o
    diálogo de assinatura (com renovação automática de token antes de bloquear).
  - Falha de rede continua liberada: cliente pagante não é punido por internet
    instável.
- `android/.../SubscriptionActivity.kt`
  - Checkout enviado com `app_platform = "android"` e token renovado na hora.
- `android/.../LoginActivity.kt`
  - Trata `eftv://open` (volta do pagamento) e `eftv://verify-email?token=...`.
  - Abre o catálogo com `CLEAR_TOP|SINGLE_TOP` e cai direto em **Minha
    assinatura** quando veio do checkout.
- `android/.../MainActivity.kt`
  - Aviso de fim de teste nos últimos **3 dias**, no máximo 1x por dia, com
    botão "Assinar agora" e preço real do plano.
  - `onNewIntent` para o deep link quando o catálogo já estava aberto.
- `backend/app/schemas/payment.py` + `backend/app/routes/subscriptions.py`
  - Campo opcional `app_platform`; para Android a `back_url` vira
    `checkout.html?app=1`.
- `checkout.html`
  - Com `app=1`, reabre o app em `eftv://open` sozinho (com fallback para a
    página de download).

### Segurança / confiança

- `android/.../data/SessionStore.kt`
  - Access/refresh tokens cifrados com **AES/GCM + Android Keystore**.
  - Valores antigos em texto puro continuam válidos e são migrados.
  - Backup em nuvem já estava excluído em `backup_rules.xml` e
    `data_extraction_rules.xml`.
- `android/.../activity_login.xml`
  - Botão morto de demonstração removido da tela de produção.

### Já existente e validado nesta rodada

- R8 + `shrinkResources` no release (APK menor e mais difícil de adulterar).
- TLS obrigatório para os domínios do backend, cleartext só para streams IPTV.
- Link de atualização validado (HTTPS público, sem loopback/LAN/credenciais).
- Logs e relatórios de crash com URLs mascaradas.
- `testDebugUnitTest`, `assembleDebug`, `assembleRelease` e `lintVitalRelease`
  passaram; 39,7 MB no release (sem assinatura).

## 3. Bloqueadores antes de vender

### 3.1 Keystore de release (P0)

O build gera `app-release-unsigned.apk`. Não existe `android/eftv-release.jks`
nem `android/keystore.properties` na máquina/repositório.

- Sem a **mesma chave** usada na primeira versão publicada, o Android recusa a
  atualização ("aplicativo não instalado").
- Se ainda não existe versão publicada, gere a chave agora e guarde duas
  cópias offline (pendrive + cofre de senhas).
- Depois de gerar, use `assembleRelease` e publique com a mesma assinatura
  sempre.

### 3.2 Distribuição fora da Play (P1)

APK direto funciona, mas:

- Play Protect mostra aviso de "app desconhecido";
- atualização depende do navegador e de "instalar apps desconhecidos";
- não há cobrança pela Play (o Mercado Pago cobre, mas a Play exigiria Play
  Billing para assinatura digital).

Para TV box, o link curto `/tv` (302 para o APK) já resolve o caso sem
navegador. Um instalador interno (DownloadManager + FileProvider) reduziria o
abandono em updates, mas precisa de teste em aparelho real.

## 4. Vazamentos de receita que ainda existem

### 4.1 Trial por aparelho (P0 de produto)

Hoje o trial é por **conta**. A mesma pessoa pode criar outra conta e ganhar
mais 7 dias no mesmo aparelho. O `X-Device-Id` já chega ao backend no
`/player/playlist`, então a correção é viável:

1. guardar o `device_id` que ativou cada trial (tabela/coluna);
2. ao verificar o e-mail e ativar o trial, recusar se aquele `device_id` já
   consumiu trial;
3. manter o vínculo mesmo após cancelar/expirar.

Sem isso, qualquer campanha de aquisição pode ser neutralizada por recadastro.

### 4.2 Conta compartilhada

Limite de 2 aparelhos + 1 tela + tokens cifrados já encarecem o
compartilhamento. O próximo passo seria revogar o refresh token no servidor
no logout (hoje `/auth/logout` só apaga cookie) e permitir ao cliente ver
"aparelhos ativos" com data do último acesso (já existe a tela).

### 4.3 Atualização obrigatória

Funciona, mas o download abre o navegador. Em TV sem navegador o cliente fica
preso na versão antiga. O endpoint `/app/version` já devolve `mandatory`; falta
um instalador interno para cumprir a obrigatoriedade.

## 5. Segurança e privacidade

- **Proxy local sem token**: `server.py` roda em `127.0.0.1:8124`, mas qualquer
  app com INTERNET no mesmo aparelho alcança loopback. Hoje ele serve
  `/api/playlist.m3u` e `/api/proxy?url=...` sem autenticação. Recomendação:
  gerar um token aleatório por processo, exigir em `X-EFTV-Token`/query e
  injetá-lo nas URLs do player. Isso também protege a playlist local.
- **Crash público sem limite**: `POST /app/crashes` grava em banco sem rate
  limit. Aplicar o mesmo `rate_limit_dependency` das rotas de auth.
- **Permissões de cast**: o app declara `RECORD_AUDIO` e
  `FOREGROUND_SERVICE_MEDIA_PROJECTION`, mas o recurso está escondido na UI.
  Se não for vender cast, remover código/permissões reduz atrito e revisão de
  loja.
- **Sem Play Integrity / checagem de assinatura**: APK remontado pode ser
  distribuído como "EFTV grátis". R8 ajuda, mas não impede. Uma checagem de
  assinatura do pacote + validação server-side eleva a barreira.
- **Sem exclusão de conta no app**: LGPD/Play pedem fluxo de exclusão. Hoje o
  cliente depende de suporte.

## 6. Recomendações por prioridade

### P0 — antes da próxima venda

1. Gerar/guardar o keystore e assinar o release.
2. Testar em aparelho real: cadastro → e-mail → trial → checkout → retorno ao
   app → assinatura ativa → cancelamento.
3. Trial por `device_id` no backend.

### P1 — próximas 2 semanas

4. Rate limit em `/app/crashes` e token no proxy local.
5. Instalador interno de APK (ou pelo menos um passo a passo dentro do app).
6. Métrica de funil: trial iniciado, checkout aberto, pagamento aprovado
   (hoje não há como medir onde o cliente desiste).

### P2 — evolução

7. Exclusão de conta e exportação de dados.
8. Play Integrity/assinatura.
9. Avaliar Play Store/Amazon Appstore (exige Play Billing para assinatura).
10. Atualizar `targetSdk` (34 → 35/36) e dependências (media3 1.3.1 etc.)
    quando houver tempo para testar Chaquopy/AGP.

## 7. Checklist manual de aceitação

- [ ] Instalar o APK assinado em aparelho limpo.
- [ ] Criar conta, receber e-mail, confirmar pelo link.
- [ ] Ver o aviso de trial e o preço de R$ 19,90.
- [ ] Abrir o checkout, pagar (sandbox), voltar pelo `eftv://open`.
- [ ] Confirmar que "Minha assinatura" mostra ativa e o catálogo abre.
- [ ] Abrir o mesmo canal em dois aparelhos: o segundo deve receber limite de
      tela.
- [ ] Cancelar: acesso continua até o fim do período.
- [ ] Simular assinatura vencida: catálogo bloqueado e player interrompido.
- [ ] Ativar modo avião durante o player: reprodução não deve ser bloqueada.
- [ ] Rotacionar/atualizar o app: sessão continua válida (tokens cifrados).

---

## 8. Segunda passada (continuação da análise)

Revisão do backend inteiro e do app já com as mudanças da seção 2 aplicadas.
Aqui estão os achados que **não** estavam na primeira rodada, em ordem de
impacto na receita.

### 8.1 A playlist é uma URL única para todos (P0 — o maior vazamento)

`backend/app/routes/player.py:112` devolve `settings.IPTV_PLAYLIST_URL`
(`config.py:118`) para todo assinante ativo. É a **mesma** URL, com o
usuário/senha do provedor, para todos os clientes.

- Quem assinar um mês (ou usar o trial) vê essa URL no tráfego HTTP do
  aparelho e pode usá-la em qualquer player, para sempre, sem o EFTV.
- Basta uma pessoa publicar essa URL para o produto virar gratuito: não há
  como revogar um cliente sem trocar a credencial de todos.
- Limite de aparelho e de tela só valem dentro do app; fora dele não há
  controle nenhum (o provedor limita `max_connections`, não assinantes).

Correção de verdade: subconta/linha por assinante no provedor (API de
revenda Xtream), devolvendo credencial própria e revogável. Alternativa
parcial: relay/CDN com token curto por usuário (custa banda — inviável na
instância atual de 0,5 CPU).

### 8.2 Trial por conta também no fluxo do app (P0 — já mapeado, agora com o ponto exato)

- O trial nasce em `backend/app/routes/auth.py:176-190`, no `verify-email`,
  sem qualquer identificador de aparelho.
- `EmailVerificationActivity.kt:36` cria `EftvApi()` **sem** `deviceId`, então
  nem o header `X-Device-Id` vai nessa chamada.
- O `device_id` do app é derivado do `ANDROID_ID` (`DeviceIdentity.kt:44-59`),
  ou seja, sobrevive a reinstalação — é uma chave boa para amarrar o trial.

Implementação sugerida (fecha os dois caminhos, app e web):
1. `verify-email` aceita `X-Device-Id` opcional e grava o trial vinculado a ele.
2. Tabela `trial_devices` (`device_id` único, `user_id`, `subscription_id`).
3. No `GET /player/playlist`, se a assinatura é `trial` e o `device_id` já
   consumiu trial em outra conta, revogar o trial e devolver
   `403 trial_device_used`.
4. O passo 3 é o que fecha o furo de quem confirma o e-mail pelo navegador.

### 8.3 Retorno do pagamento não funciona no fluxo por plano (P1 — regressão da rodada anterior)

O `app=1` só é aplicado à **preapproval direta**
(`subscriptions.py:264-267`). Quando o Mercado Pago recusa a preapproval e o
código cai no fluxo por `preapproval_plan`, a `back_url` é a do plano, criada
sem `app=1` (`mercadopago.py:196`). Resultado: nesse caminho o cliente paga e
cai em `checkout.html` sem reabertura automática do app (só no botão manual).

Opções: (a) recriar o plano com `back_url=.../checkout.html?app=1`; (b) no
`checkout.html`, abrir o app automaticamente também quando o user-agent é
Android (a versão web é uso pessoal).

### 8.4 Refresh token não é revogável (P1)

- `/auth/refresh` (`auth.py:360-422`) rotaciona o par, mas não invalida o
  refresh antigo: não existe tabela de `jti`.
- `/auth/logout` (`auth.py:425-429`) só apaga o cookie.

Quem copiar o refresh token (TV box compartilhada, backup, aparelho com root)
continua renovando acesso por `REFRESH_TOKEN_EXPIRE_DAYS` mesmo depois de
"deslogar". Correção: tabela de refresh ativo (`jti`, `user_id`, `device_id`,
revogado em) e checar no refresh/logout.

### 8.5 Rate limit global compartilhado atrás do proxy (P1 — disponibilidade)

`dependencies.py:192-225` é um contador **em memória** por processo, e
`client_ip` (`258-275`) usa o `X-Forwarded-For` — o próprio arquivo admite que
no Render todos os clientes chegam como o mesmo IP.

- `RATE_LIMIT_REQUESTS=100` por 60 s vira um balde **da base inteira** para
  cadastro, reenvio de e-mail e recuperação de senha: um abusador derruba o
  cadastro de todo mundo e o contador zera a cada deploy.
- O limite de login por conta (`230-255`) também é em memória: reiniciar o
  serviço devolve as 10 tentativas.

### 8.6 Recuperação de senha por código de 6 dígitos sem limite por conta (P1)

`user.py:95-101` gera 6 dígitos; `auth.py:281-305` só tem o rate limit por IP
(que, pela 8.5, é compartilhado). Falta contador de tentativas por conta e o
código é gravado em texto puro.

### 8.7 Trial "trial" nunca expira no banco (P2)

`subscription_checker.py:29-35` só olha `status == "active"`. O trial vence e
continua `trial` para sempre: sem e-mail de "seu teste acabou", sem estado
correto no painel. O acesso é bloqueado só pelo `has_access`
(`models/subscription.py:92-115`).

### 8.8 Webhook aceito sem assinatura quando o segredo não está configurado (P1 de configuração)

`mercadopago.py:87-92`: sem `MERCADOPAGO_WEBHOOK_SECRET`, qualquer POST é
aceito (só loga aviso). O efeito é limitado porque o handler consulta o
Mercado Pago antes de liberar, mas permite replay/força de chamadas. O
`render.yaml` não declara essa variável — fácil esquecer no deploy.

### 8.9 Permissão de notificação nunca é pedida (regressão da rodada anterior)

A remoção de `requestNotificationPermission()` em `LoginActivity.kt` não foi
substituída em nenhum lugar (não há `requestPermissions` no projeto). Com
`POST_NOTIFICATIONS` no manifesto e alvo 34, no Android 13+ o app fica sem
notificação (inclusive as dos serviços em primeiro plano).

### 8.10 Proxy local aberto na loopback (P2)

`server.py:1456+` serve `/api/proxy?url=...` sem token e `server.py:1028-1033`
devolve `/api/playlists` **com a URL crua do provedor** (usuário/senha). O
CORS público (`978-983`) vale para as rotas de leitura do site. Qualquer app
com INTERNET no aparelho lê as credenciais; um site aberto no navegador pode
usar o proxy como relay para a rede local (SSRF). Correção: token por
processo + CORS restrito à origem do GitHub Pages.

### 8.11 Outros (P3)

- `streams.py:24-28` não tem teto para `max_simultaneous_streams` (o de
  aparelhos tem, em `devices.py:40-51`).
- `mercadopago.py:488-505` casa pagamento por `payer_email`: cadastrar o
  e-mail de outra pessoa (conta não verificada) pode capturar o pagamento dela.
- `/health` (`main.py:117-143`) expõe `client_ip`, URLs e id da conta MP.
- `POST /app/crashes` segue sem rate limit.
- Sem exclusão de conta / exportação de dados (LGPD e Play).
- Atualização continua abrindo o navegador (`MainActivity.kt:216-221`).

## 9. Status da correcao (rodada P0 -> P3)

Tudo abaixo esta implementado e coberto por testes de backend (206 passando) e
build/testes Android (`testDebugUnitTest` + `assembleDebug`). Nada foi commitado.

### P0
- **8.1 playlist unica**: cada assinatura agora tem `provider_playlist_url`
  (`subscriptions.provider_playlist_url`), com `POST/DELETE
  /admin/subscriptions/{id}/line` para vincular/revogar a linha do provedor.
  `player.py` entrega a linha propria quando existe e cai na compartilhada
  quando nao. *Pendente de produto*: provisionar a subconta no painel do
  provedor (a API de reseller nao existe/documentada).
- **4.1/8.2 trial por aparelho**: tabela `trial_devices`; `verify-email` amarra
  o `X-Device-Id` e `/player/playlist` revoga o trial quando o aparelho ja
  consumiu o teste em outra conta. Android passou a enviar o id em
  `EmailVerificationActivity`.
- **8.3 retorno do checkout**: o fallback `preapproval_plan` voltou a levar
  `?app=1`; `checkout.html` tambem tenta abrir o app em qualquer retorno
  Android, entao o cliente nao fica preso no navegador.

### P1
- **8.4 refresh revogavel**: tabela `refresh_tokens`; logout e rotacao
  revogam o `jti`, e `DELETE /auth/me` derruba todas as sessoes. Tokens
  antigos (sem `jti` registrado) sao aceitos uma vez e registrados, para nao
  deslogar a base no deploy.
- **8.5 rate limit por identidade**: `rate_limit_counters` no banco, chave por
  e-mail/conta (`register`, login, reenvio, recuperacao, reset, crashes).
  Deixa de ser um balde por IP compartilhado pela base inteira.
- **8.6 codigo de recuperacao**: limite de tentativas por conta e codigo
  gravado como SHA-256 (comparacao em texto puro so para codigos legados de
  30 min).
- **8.8 webhook**: `MERCADOPAGO_WEBHOOK_SECRET` obrigatorio em producao e
  janela de 600 s contra replay. Declarado em `render.yaml`/`render.free.yaml`.
- **8.9 notificacao**: `LoginActivity` pede `POST_NOTIFICATIONS` no Android 13+.
- **5. conta tomada / pagamento**: cadastro novo sobre e-mail nao verificado
  assume a conta; webhook so casa `payer_email` de conta verificada.
- **atualizacao**: `UpdateInstaller` baixa o APK com progresso e abre o
  instalador via `FileProvider` (nao vai mais para o navegador).

### P2
- **8.7 trial expirado**: `subscription_checker` marca `expired` e
  `lifecycle_emails` envia o e-mail de winback uma unica vez
  (`trial_expired_notified_at`).
- **8.10 proxy local**: CORS restrito a origem do GitHub Pages/origem local,
  checagem de `Host` contra DNS rebinding, URLs de playlist mascaradas em
  `/api/playlists` e alvos privados/loopback bloqueados no `/api/proxy`
  (redirects validados; `EFTV_PROXY_ALLOW_PRIVATE=1` para quem usa provedor
  na LAN).

### P3
- Teto `MAX_STREAMS_PER_SUBSCRIPTION` em `streams.py`.
- `/health` sem IP, URLs internas ou id da conta MP.
- `POST /app/crashes` com rate limit por IP.
- `GET /auth/me/export` e `DELETE /auth/me` (LGPD/Play), com a acao
  "Excluir minha conta" em `SettingsActivity`.
