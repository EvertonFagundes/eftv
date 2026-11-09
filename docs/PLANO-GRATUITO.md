# Plano de producao com custo zero

Registro das decisoes para colocar usuarios reais no EFTV sem gastar nada por
mes, e do que precisa ser feito em cada etapa. Atualizado em 2026-11-08.

> Regra que guia tudo: **nada que apague dados por tempo**. Cota mensal que
> suspende e aceitavel (volta no mes seguinte); banco que expira em 30 dias e
> perda de cliente. Foi por isso que o Postgres free do Render saiu do plano.

Ao retomar o trabalho, leia este arquivo, veja a proxima etapa desmarcada e
siga a ordem. As decisoes registradas aqui so mudam com justificativa escrita.

> **Prazo:** o Postgres free do Render (`eftv-db`, criado em 06/11/2026)
> expira em **06/12/2026**. Depois disso fica inacessivel e e apagado em 14
> dias. A etapa 1 precisa terminar antes dessa data.

## 1. Stack alvo

| Peca | Escolha | Custo | Limite free | Por que |
| --- | --- | --- | --- | --- |
| API | Render free | R$ 0 | 750 h/mes, 0,1 CPU, 512 MB | Ja esta no ar com HTTPS |
| Banco | **Supabase free** | R$ 0 | 500 MB, 5 GB de saida | Sem cota de horas de computacao; nao expira |
| E-mail | **Brevo free** | R$ 0 | 300 envios/dia | Aceita remetente verificado, sem dominio proprio |
| Web | GitHub Pages | R$ 0 | - | Ja publica `index.html` + `assets/` |
| APK | GitHub Releases | R$ 0 | - | Play Store cobra US$ 25 unico |
| Pagamento | Mercado Pago | % por venda | - | Sem mensalidade |
| Backup | GitHub Actions | R$ 0 | - | `pg_dump` diario criptografado |
| Ping | cron-job.org | R$ 0 | - | Mais pontual que o cron do GitHub |

Custo total enquanto estiver dentro das cotas: **R$ 0**.

## 2. Decisoes tomadas

1. **Sair do Postgres free do Render.** O banco atual foi criado em
   06/11/2026 e expira em **06/12/2026**: fica inacessivel e e apagado depois
   de 14 dias de carencia. Isso apaga usuarios, assinaturas, vinculos de
   aparelho e sessoes.
2. **Supabase e nao Neon.** O Neon free tem 100 CU-horas por projeto/mes. Com
   trafego continuo o compute fica acordado e a cota estoura, suspendendo o
   banco ate o dia 1. O Supabase free nao tem essa cota: so pausa apos 7 dias
   sem atividade, com os dados preservados por 1 ano e retomada manual. As
   tarefas agendadas da API (a cada 30 min e 1 h) ja consultam o banco, entao
   na pratica ele nunca fica 7 dias parado.
3. **Brevo e nao Resend.** Sem dominio proprio verificado, o Resend so entrega
   no e-mail do dono da conta. O Brevo aceita verificar um unico remetente.
   Como o Render free bloqueia as portas SMTP (25/465/587), a integracao tem
   que ser pela API HTTPS.
4. **APK por GitHub Releases.** Instalacao direta evita o custo unico da Play
   Store. O usuario precisa liberar "instalar de fontes desconhecidas".
5. **Ping no cron-job.org como principal.** O cron do GitHub atrasa em horario
   de pico e e desativado apos 60 dias sem commit no repositorio. O workflow
   do GitHub continua como reserva.
6. **Oracle Always Free descartado por ora.** Apesar de gratuito, a Oracle
   recupera instancia ociosa: CPU, rede e memoria abaixo de ~20% por 7 dias
   seguidos. Um backend pequeno fica em 1-2% de CPU. Em 2026 a cota tambem caiu
   para 2 OCPU / 12 GB. Nao e "ligar e esquecer".
7. **Aiven free fica como reserva do Supabase.** Tambem nao expira (1 GB de
   disco, sempre ligado, backups), mas limita a 20 conexoes e pode desligar o
   servico por inatividade, exigindo religar no painel. Se o Supabase pausar
   por algum motivo, e o plano B mais direto.

## 3. Limites e mitigacoes

| Limite | Efeito | Mitigacao |
| --- | --- | --- |
| Render: 750 h/mes | 24/7 consome ~744 h em mes de 31 dias | Um unico servico free no workspace; ping 24/7 |
| Render: 0,1 CPU / 512 MB | Aguenta dezenas a ~200 usuarios ativos | Video nao passa pela API; medir antes de divulgar |
| Render: 5 GB de saida/mes | Estourou sem cartao, suspende ate o dia 1 | Nao baixar playlist/stream no backend |
| Render: dorme em 15 min | Primeiro acesso demora ~1 min | Ping a cada 5 min (cron-job.org + GitHub) |
| Supabase: 500 MB | Insercao falha ao encher | Texto e URLs do catalogo sao poucos MB; monitorar |
| Supabase: pausa apos 7 dias | Banco offline ate retomar no painel | Com usuario real nao acontece; alerta por e-mail |
| Supabase: sem backup | Um erro pode apagar tudo | `pg_dump` diario criptografado (etapa 3) |
| Brevo: 300/dia | Cadastros param no limite | Suficiente para centenas de cadastros |
| GitHub: cron desativado | Keepalive para sozinho | cron-job.org nao depende de commit |
| Provedor: painel diz **1 conexao** | Nao bloqueia: o provedor libera mais (confirmado) | Monitorar `active_cons` e manter 1 aparelho por assinatura |
| Provedor: 8 conexoes ativas | Pode ser uso normal ou credencial compartilhada | Se crescer sem uso proprio, trocar a senha e derrubar sessoes |

## 4. Capacidade esperada

Base inicial: **ate 5 usuarios**. Com esse volume, cota nao e o problema —
0,1 CPU e 512 MB sobram. O risco real, nessa ordem, e:

1. perder dados (banco sem backup ou com prazo de validade);
2. o app dormir e o usuario achar que esta fora do ar;
3. o trial vencer e nao haver caminho de assinatura.

O gargalo de infraestrutura so aparece perto de ~200 ativos. Medir mesmo
assim: tempo de resposta de `/health`, `/auth/login` e `/channels`, e o consumo
em *Billing > Included usage* no Render.

O painel do provedor informa `max_connections = 1` e `active_cons = 8`, mas o
provedor confirmou que libera **mais conexoes simultaneas** do que o painel
mostra (informado em 08/11/2026). Portanto isso **nao e bloqueio** para os 5
usuarios. O que continua valendo:

1. monitorar `active_cons`; se crescer sem uso proprio, trocar a senha;
2. um aparelho por assinatura (`MAX_DEVICES_PER_SUBSCRIPTION=1`) para manter o
   custo por usuario previsivel.

## 5. Etapas

### Etapa 0 - ja feita

- [x] API publica em `https://eftv.onrender.com`
- [x] Ping de `/health` a cada 10 min pelo GitHub Actions
- [x] Documentacao de deploy atualizada
- [x] Consulta da configuracao real pela API do Render (servico em Oregon;
      `eftv-db` expira em 06/12/2026)

### Etapa 0.5 - alinhar a conta da playlist

- [ ] Confirmar com o provedor quantas conexoes simultaneas o plano permite
      (o painel diz **1**).
- [ ] Trocar a senha e derrubar as sessoes ativas (o painel mostra **8 em uso**).
- [ ] Decidir o modelo: plano com 5 conexoes ou uma conta por assinante.
- [ ] Atualizar `IPTV_PLAYLIST_URL` no Render e no `.env` local.

### Etapa 1 - migrar o banco para o Supabase

- [ ] Concluir **antes de 06/12/2026** (expiracao do banco atual).
- [ ] Criar projeto no Supabase, regiao **West US (North California)**: o
      Render esta em Oregon (confirmado na API), entao e a regiao mais proxima
      disponivel.
- [ ] Nao e preciso criar organizacao nova: um projeto novo pode entrar na
      organizacao Free existente (o plano Free permite 2 projetos ativos por
      conta, somando todas as organizacoes em que voce e Owner/Admin).
      Excecao: se a organizacao existente for paga (Pro), o projeto novo
      tambem sera pago — nesse caso crie uma organizacao Free separada.
      Projetos pausados nao contam no limite.
- [ ] Copiar a connection string do **pooler** (IPv4, porta 6543) e nao a
      conexao direta (IPv6).
- [x] Ajustar o backend para o pooler (ver secao 6).
- [x] Projeto Supabase criado e schema aplicado com `alembic upgrade head`
      (Postgres 17.11, tres migracoes). O projeto ficou em **East US 2
      (Ohio)**, e nao em North California como previsto: a distancia extra
      para o Render em Oregon custa dezenas de milissegundos por consulta,
      irrelevante para 5 usuarios. Trocar de regiao exigiria recriar o
      projeto, entao ficou assim.
- [x] Dados copiados do Postgres atual do Render: 3 usuarios, 1 plano,
      2 assinaturas e 6 vinculos de aparelho. Catalogo estava vazio
      (`/channels` e `/categories` em 0). Os aparelhos foram revogados na
      copia para o primeiro aparelho que abrir o app assumir a vaga.
- [x] Trocar `DATABASE_URL` no Render e validar login/catalogo. Validado em
      08/11/2026: login da conta migrada, `/subscriptions`, `/player/playlist`
      e vinculo de aparelho funcionando direto no Supabase.
- [ ] Manter o Postgres do Render como copia de seguranca ate o backup
      cifrado + restore da etapa 3 estarem testados. So depois apagar
      (ele expira em 06/12/2026 de qualquer forma).

### Etapa 2 - e-mail pela Brevo (concluida em 08/11/2026)

- [x] Criar conta e verificar um remetente (remetente `EFTV`, conta
      compartilhada com o ControlFin).
- [x] Implementar envio via API `https://api.brevo.com/v3/smtp/email`
      (`EMAIL_PROVIDER=brevo`; Resend continua como alternativa).
- [x] Variaveis: `BREVO_API_KEY` e `EMAIL_FROM`; Resend como opcao.
- [x] `FRONTEND_URL=https://evertonfagundes.github.io/eftv` no Render (sem ela
      o link sai como `http://localhost:3000`).
- [x] Pagina estatica `verify-email.html` no GitHub Pages para o link do e-mail.
- [x] Liberar as faixas de saida do Render em *Authorized IPs* no Brevo.
- [x] Testar cadastro de um e-mail externo de ponta a ponta.
- [ ] Remover o IP temporario `2804:1b94:494:1000:936b:383c:dc4d:d12f` de
      *Authorized IPs* no Brevo (foi liberado so para o teste manual).

Teste de ponta a ponta (08/11/2026): conta criada com um alias
`+eftvtest` do Gmail, e-mail entregue pelo Brevo, link abrindo
`https://evertonfagundes.github.io/eftv/verify-email.html?token=...`, pagina
mostrando "E-mail confirmado" e trial ativado. A API confirmou a assinatura
com `status=trial`, periodo de `2026-11-08T18:39:21Z` a
`2026-11-15T18:39:21Z` e `is_trial=true`. A senha da conta de teste nao e
registrada no repositorio (ele e publico); quem precisar dela pede ao
responsavel.

O teste revelou um bug junto com a validacao: o trial era criado, mas o
`get_current_active_subscription` aceitava `status in ("active", "trial")` na
consulta e logo depois exigia `subscription.is_active`, que so cobre
`status="active"`. Resultado: o usuario confirmava o e-mail, o trial aparecia
ativo e o player respondia `403 subscription_expired`. Corrigido com a
propriedade `Subscription.has_access`, que cobre plano pago e trial (com o fim
do periodo como limite comum) e e usada pelo controle de acesso. `is_active`
continua com o significado estrito de assinatura paga, para os campos da API.

### Etapa 3 - backup

- [x] Workflow noturno com `pg_dump -Fc`, cifrado com `gpg --symmetric`
      (`.github/workflows/backup.yml`, artefato de 90 dias).
- [x] Segredo `BACKUP_PASSPHRASE` no GitHub; nunca subir dump sem cifra
      (o repositorio e publico).
- [x] Testar o restore em banco local antes de confiar no backup: dump
      cifrado restaurado em `postgres:17-alpine` com os dados e o Alembic.
      O dump passou a usar `--schema=public` por causa dos schemas internos
      do Supabase.
- [x] Primeira execucao real do workflow concluida com sucesso em 08/11/2026
      (run 4), gerando o artefato cifrado.

### Etapa 4 - ping redundante

- [ ] Criar monitor no cron-job.org: `GET /health`, 5 min, com alerta por
      e-mail em caso de falha.
- [ ] Manter o workflow do GitHub como reserva.

### Etapa 5 - abrir para os 5 primeiros

- [ ] 5 usuarios, com suporte por WhatsApp/Telegram.
- [ ] Acompanhar erros, tempo de resposta e consumo das cotas por uma semana.
- [ ] Corrigir o que aparecer antes de divulgar mais.

### Etapa 6 - gatilho de migracao para pago

Migrar quando a receita pagar a infra, nao antes:

- Render Starter (~US$ 7) = sem hibernar e sem cota de horas;
- banco do Render Basic (~US$ 6) ou Supabase Pro (~US$ 25), conforme o caso.

Com 5 assinantes de R$ 19,90, sao R$ 99,50/mes, que ja cobrem a infra paga
(~R$ 75) com folga.

## 6. Detalhes tecnicos da migracao do banco

### URL de conexao

O provedor entrega algo como:

```
postgresql://postgres.<ref>:SENHA@aws-0-us-east-1.pooler.supabase.com:6543/postgres
```

O `backend/app/config.py` ja converte `postgresql://` para
`postgresql+asyncpg://` e `sslmode=require` para `ssl=require`, e remove
`channel_binding`/`pgbouncer` (parametros do libpq que o asyncpg recusa).

O pooler e detectado pela porta **6543** ou pelo host
`*.pooler.supabase.com`; nesse caso o `app/database.py` liga
`statement_cache_size=0`, `prepared_statement_cache_size=0` e ainda pede
**nome vazio** de statement (`prepared_statement_name_func`). Sem o nome
vazio o asyncpg prepara statements nomeados, que colidem com os de outro
cliente na mesma conexao fisica do pooler
(`DuplicatePreparedStatementError`). Dá para forçar com
`DATABASE_POOLER=true|false` se o provedor mudar.

Teste local contra a porta 6543 (08/11/2026): login, `/subscriptions` e
`/player/playlist` responderam 200 com os dados restaurados.

Para migrations e seed, usar a porta **5432** (modo session) ou a conexao
direta, porque o modo transaction nao suporta todos os recursos. O modo
session do pooler ja resolve isso por IPv4, sem contratar o add-on IPv4 do
Supabase (que e pago).

### Pool

Manter `DATABASE_POOL_SIZE=3` e `DATABASE_MAX_OVERFLOW=2`. O Supabase free tem
limite de conexoes por compute; pool pequeno evita erro de `too many
connections`.

### E-mail

O Render free bloqueia SMTP; por isso o envio e por HTTPS. Com
`EMAIL_PROVIDER=brevo` e `BREVO_API_KEY`, o
`backend/app/services/email_service.py` chama
`POST https://api.brevo.com/v3/smtp/email`. O `EMAIL_FROM` precisa ser um
remetente verificado no Brevo; sem dominio proprio, verifique um e-mail seu.

O link de confirmacao aponta para `{FRONTEND_URL}/verify-email.html`. Essa
pagina fica na raiz do repositorio (GitHub Pages publica o site de catalogo,
nao o `frontend/dist`): ela le o `token` da URL, chama `POST /auth/verify-email`
e mostra o resultado. Se o CORS bloquear o GitHub Pages, a pagina exibe erro
de conexao — por isso `CORS_ORIGINS` precisa conter a origem exata.

Sem chave, o provedor cai em modo `dev`: registra o conteudo no log (util para
testar, inutil em producao). Resend continua disponivel com
`EMAIL_PROVIDER=resend` e `RESEND_API_KEY`.

**Conta compartilhada com o ControlFin.** O limite de 300 envios/dia e **por
conta**, nao por remetente: os dois projetos somam na mesma cota. Para o volume
do EFTV (verificacao + boas-vindas, no maximo alguns e-mails por cadastro) isso
e folgado, entao nao vale criar outra conta. Recomendacoes:

- criar um remetente **EFTV** verificado; se o ControlFin ja tem dominio
  autenticado no Brevo, um endereco desse dominio ja sai verificado;
- criar uma **API key separada** (SMTP & API > API Keys), para revogar sem
  afetar o ControlFin;
- **cuidado com o tipo de chave**: a chave SMTP (`xsmtpsib-...`) nao funciona
  na API v3; use a API key (`xkeysib-...`), que fica na aba *API Keys*;
- **bloqueio por IP**: se a conta tiver *Settings > Security > Authorized IPs*
  com bloqueio ativo (o Brevo ativa sozinho depois de 30 dias sem IP novo), o
  Render recebe HTTP 401 mesmo com a chave certa. Copie as faixas de saida em
  *Render > servico > Connect > Outbound* e cadastre em *Authorized IPs*; nao
  e preciso desativar o bloqueio. Servicos free usam faixas fixas compartilhadas
  por regiao, exceto workspaces de Oregon criados antes de 23/01/2022.
  Faixas do servico `eftv` (Oregon, conferidas em 08/11/2026):
  `74.220.48.0/24` e `74.220.56.0/24`;
- lembrar que a reputacao de envio e compartilhada: muitas rejeicoes em um
  projeto podem respingar no outro.

Depois de 300 envios no dia, o Brevo ainda segura ate 1.000 transacionais numa
fila de reenvio; mesmo assim, o normal e nunca chegar perto disso.

### Backup

`.github/workflows/backup.yml` roda todo dia as 03:17 (Brasilia), gera
`pg_dump -Fc` num container `postgres:17-alpine` e cifra com GPG simetrico
(AES256) usando `BACKUP_PASSPHRASE`. O arquivo vira artefato por 90 dias.

O dump usa `--schema=public`. Sem isso ele inclui os schemas internos do
Supabase (`vault`, `auth`, `storage`), que nao existem num Postgres comum e
fazem o restore falhar. Nossas tabelas sao todas em `public`.

Teste de restore feito em 08/11/2026 com `postgres:17-alpine`: o dump cifrado
de 29 KB restaurou 3 usuarios, 1 plano, 2 assinaturas, os vinculos de aparelho
e a versao do Alembic. Aparece o aviso `schema "public" already exists`, que e
esperado e inofensivo.

Segredos necessarios no GitHub (Settings > Secrets and variables > Actions):
`DATABASE_URL` (URL libpq do **session pooler**, porta 5432, com
`?sslmode=require`) e `BACKUP_PASSPHRASE` (senha longa, guardada tambem num
gerenciador de senhas). Sem eles o job nao falha: apenas avisa que falta
configuracao. Para restaurar:

```bash
gpg --decrypt eftv-AAAA.dump.gpg | pg_restore --no-owner --no-acl -d postgresql://...
```

### Descobrir o limite de conexoes da playlist

O provedor nao publica esse numero. Se a playlist for Xtream Codes (a nossa e
`get.php?type=m3u_plus`), o proprio painel costuma expor o dado em
`player_api.php`:

```bash
cd backend
python scripts/playlist_account.py
```

O script le a `IPTV_PLAYLIST_URL` do `.env`, mascara usuario e senha e mostra
status, vencimento, conexoes em uso e o maximo permitido. Se o servidor nao
tiver `player_api.php`, resta o teste pratico: abrir dois streams ao mesmo
tempo e ver o codigo de erro (403/458/509 costuma ser limite atingido).

Consulta feita em 08/11/2026, usando a URL que esta **no Render** (a do `.env`
local estava desatualizada e dava 404):

| Campo | Valor |
| --- | --- |
| Status | Active (nao e trial) |
| Vencimento da conta | 06/03/2027 |
| Conexoes permitidas | **1** |
| Conexoes em uso | **8** |
| Servidor | IP fixo, protocolo http, fuso America/Sao_Paulo |

O Render e a **fonte da verdade** da URL da playlist. O `.env` local foi
sincronizado com ele em 08/11/2026 e nao deve ser copiado para o repositorio.

Enquanto o numero for desconhecido, a regra de produto e **1 stream por
conta**: `MAX_DEVICES_PER_SUBSCRIPTION=1` ja e o padrao. Isso evita surpresa
com o provedor e mantem o custo por usuario previsivel.

O limite efetivo e o **menor** entre o `max_devices` do plano e
`MAX_DEVICES_PER_SUBSCRIPTION`. O plano existente ("Dono do App", criado como
default antes do modelo comercial) declara 10 aparelhos e 5 streams; sem o
teto, todo trial sairia com 10 aparelhos e poderia ser compartilhado. Quando
existir um plano pago com mais aparelhos, basta subir a variavel. A criacao do
plano mensal (nome, preco e limites) entra junto com o Mercado Pago.

### O que ja ajuda

- `/health` nao consulta o banco, entao o ping nao gasta computacao do
  Supabase.
- O campo `DATABASE_URL` e o unico ponto de configuracao: nenhuma rota precisa
  mudar.

### Arquivos que mudam em cada etapa

| Etapa | Arquivos |
| --- | --- |
| 1. Banco | `backend/app/config.py`, `backend/app/database.py`, `render.free.yaml`/`render.yaml`, `android/local.properties` (nao versionado) |
| 2. E-mail | `backend/app/services/email_service.py`, `backend/app/config.py`, `verify-email.html` |
| 3. Backup | `.github/workflows/backup.yml` (novo) |
| 4. Ping | `.github/workflows/keepalive.yml` (ajuste de 10 para 5 min) |
| 5. Go-live | `docs/PLANO-GRATUITO.md` (checklist), `README.md` |
| Playlist | `backend/scripts/playlist_account.py` (novo), `backend/.env` (nao versionado) |

## 7. Riscos aceitos

- Sem SLA e sem backup do provedor: a copia e a nossa (etapa 3).
- O Render pode reiniciar o servico free a qualquer momento.
- Se estourar banda ou horas, os servicos free ficam suspensos ate o proximo
  mes; e a principal razao para abrir devagar.
- Sem dominio proprio: a URL e `eftv.onrender.com` e os e-mails saem com o
  remetente do Brevo. Isso e aceitavel para testar com conhecidos, nao para
  marca.

## 8. Checklist de go-live

- [x] Banco migrado e restore do backup testado
- [x] Cadastro e verificacao de e-mail funcionando com e-mail externo
- [ ] Ping redundante ativo e alertando
- [ ] APK assinado publicado em Releases
- [ ] Admin com senha forte e 2FA no GitHub/Render/Supabase
- [ ] Politica de privacidade e termos (LGPD) publicados
- [ ] Mercado Pago com webhook testado em sandbox
- [ ] Consumo das cotas anotado semanalmente

## 9. Respostas registradas (2026-11-07)

- Base inicial: **no maximo 5 usuarios**.
- Modelo: **trial gratis de 7 dias** e, se gostar, assinatura **mensal**. So
  existe plano mensal; nada de trimestral ou anual.
- Conexoes da playlist: painel informa 1 simultanea, mas o provedor confirmou
  que libera mais; os 8 ativos no momento da consulta nao sao bloqueio.
- Preco da mensalidade: **R$ 19,90** (definido em 2026-11-09).

## 10. Modelo comercial

O trial de 7 dias ja esta implementado (`FREE_TRIAL_DAYS=7`, assinatura com
status `trial`). Depois dele, o job `check_expired_subscriptions` roda a cada
30 minutos, marca a assinatura como expirada e o app bloqueia o player.

- **Plano unico: mensal.** Menos tela, menos suporte e menos regra de
  renovacao do que ter trimestral/anual agora.
- **Preco: R$ 19,90/mes** (definido em 09/11/2026). Fica em
  `app/services/plans.py` e na migration `004`; o trial usa o mesmo plano,
  mudando apenas o status da assinatura. Com 5 assinantes, sao R$ 99,50/mes,
  o que ja cobre a infra paga.
- **Mercado Pago**: sem mensalidade, so taxa por venda (PIX costuma ser mais
  barato que cartao). E o unico custo variavel do negocio.
- **Renovacao**: sem plano anual, toda cobranca e mensal; se o pagamento
  falhar, o job expira a assinatura no ciclo seguinte.

## 11. Pendencias

- Criar o monitor no cron-job.org: `GET /health` a cada 5 min com alerta.
- Remover o IPv6 temporario das *Authorized IPs* do Brevo.
- Provedor confirmou que libera mais conexoes simultaneas que o painel indica;
  o limite de 1 nao e bloqueio (informado em 08/11/2026).
- Monitorar `active_cons`: se subir sem uso proprio, trocar a senha da playlist.
- Conferir no Render as variaveis que hoje so existem com default:
  `CORS_ORIGINS`, `MAX_DEVICES_PER_SUBSCRIPTION` e
  `IPTV_PLAYLIST_USER_AGENT`.
- Assinar e publicar o APK em Releases.
- Vale registrar um dominio proprio depois da primeira receita.

### Onde ficam os segredos

As senhas de producao (banco, `DATABASE_URL` da aplicacao e do backup e a
frase do GPG) ficam em `~/.config/eftv/secrets.env`, com permissao `600` e
**fora do repositorio**. Nenhum valor de senha entra no Git. O arquivo
`.env` do backend tambem e ignorado pelo Git.

### Valores para colar no Render

```
CORS_ORIGINS=https://evertonfagundes.github.io
FRONTEND_URL=https://evertonfagundes.github.io/eftv
EMAIL_PROVIDER=brevo
BREVO_API_KEY=<chave gerada em app.brevo.com/settings/keys/api>
EMAIL_FROM=EFTV <remetente verificado no Brevo>
```

O `EMAIL_FROM` precisa ser um remetente verificado no Brevo; sem dominio
proprio, verifique um e-mail seu. A `DATABASE_URL` ja aponta para o Supabase.
O valor de cada segredo esta em `~/.config/eftv/secrets.env`, fora do repo.

**`FRONTEND_URL` e obrigatoria em producao.** Sem ela, o link de confirmacao
sai como `http://localhost:3000/verify-email.html` e o usuario nao consegue
abrir. O valor correto nao tem barra final:
`https://evertonfagundes.github.io/eftv`.

### Segredos no GitHub (backup)

- `DATABASE_URL`: URL libpq (`postgresql://...?sslmode=require`), sem
  `+asyncpg`.
- `BACKUP_PASSPHRASE`: senha longa e aleatoria. Sem ela o backup nao roda.

## 12. Historico

| Data | Mudanca |
| --- | --- |
| 2026-11-07 | Criacao do plano; stack R$ 0 definida; etapas 1 a 6 |
| 2026-11-07 | Base de 5 usuarios, trial de 7 dias e plano mensal unico; script de consulta da playlist |
| 2026-11-08 | Consulta real pela API do Render: servico em Oregon; banco expira 06/12/2026; playlist com 1 conexao e 8 em uso |
| 2026-11-08 | Backend pronto para o pooler do Supabase: limpa `channel_binding`/`pgbouncer` e desliga caches de prepared statements |
| 2026-11-08 | `CORS_ORIGINS` passa a aceitar virgula ou JSON (corrige boot com a URL do GitHub Pages) |
| 2026-11-08 | Envio de e-mail pela API HTTPS do Brevo, com Resend como alternativa e fallback dev |
| 2026-11-08 | Workflow noturno de backup cifrado (`pg_dump` + GPG) em artefato de 90 dias |
| 2026-11-08 | Teste real do Brevo: remetente EFTV ativo, envio HTTP 201 e faixas do Render autorizadas |
| 2026-11-08 | Pagina `verify-email.html` no GitHub Pages; link do e-mail deixa de cair em 404 |
| 2026-11-08 | CORS do GitHub Pages validado no Render (preflight 200) apos normalizar a origem |
| 2026-11-08 | Etapa 2 concluida: cadastro externo, e-mail pelo Brevo, link novo e trial de 7 dias validados de ponta a ponta |
| 2026-11-08 | Corrigido: trial era barrado no player (`subscription_expired`); acesso agora usa `Subscription.has_access` |
| 2026-11-08 | Limite de aparelhos passa a ter teto por `MAX_DEVICES_PER_SUBSCRIPTION` (1 por padrao), mesmo que o plano declare mais |
| 2026-11-08 | Schema criado no Supabase (Ohio) e dados copiados do Render: 3 usuarios, 1 plano, 2 assinaturas, 6 aparelhos |
| 2026-11-08 | Pooler do Supabase exige statement anonimo (nome vazio), alem dos caches desligados; login e playlist validados na porta 6543 |
| 2026-11-08 | Producao no Supabase: `DATABASE_URL` trocada no Render e login, assinatura, playlist e vinculo de aparelho validados |
| 2026-11-08 | Backup restrito ao schema `public` e restore cifrado testado em Postgres 17 local |
| 2026-11-08 | Etapa 3 concluida: secrets configurados e primeira execucao real do backup gerou o artefato cifrado |
| 2026-11-09 | Preco definido em R$ 19,90/mes; plano unico "Mensal" com 1 aparelho e 1 stream, criado por `app/services/plans.py` e migration `004` |
