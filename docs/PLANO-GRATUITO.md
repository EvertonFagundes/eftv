# Plano de producao com custo zero

Registro das decisoes para colocar usuarios reais no EFTV sem gastar nada por
mes, e do que precisa ser feito em cada etapa. Atualizado em 2026-11-07.

> Regra que guia tudo: **nada que apague dados por tempo**. Cota mensal que
> suspende e aceitavel (volta no mes seguinte); banco que expira em 30 dias e
> perda de cliente. Foi por isso que o Postgres free do Render saiu do plano.

Ao retomar o trabalho, leia este arquivo, veja a proxima etapa desmarcada e
siga a ordem. As decisoes registradas aqui so mudam com justificativa escrita.

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

1. **Sair do Postgres free do Render.** Ele expira 30 dias apos a criacao,
   fica inacessivel e e apagado depois de 14 dias de carencia. Isso apaga
   usuarios, assinaturas, vinculos de aparelho e sessoes.
2. **Supabase e nao Neon.** O Neon free tem 100 CU-horas por projeto/mes. Com
   trafego continuo o compute fica acordado e a cota estoura, suspendendo o
   banco ate o dia 1. O Supabase free nao tem essa cota: so pausa apos 7 dias
   sem atividade, com os dados preservados por 1 ano e retomada manual.
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

## 4. Capacidade esperada

O gargalo nao e o video (o aparelho baixa direto do provedor), e sim login,
catalogo, heartbeat de aparelho e tarefas agendadas. Com 0,1 CPU:

- confortavel: dezenas de usuarios ativos simultaneos;
- apertado: ~200 ativos, dependendo do tamanho do catalogo;
- acima disso: primeira coisa a pagar e o Render Starter.

Medir antes de ampliar: tempo de resposta de `/health`, `/auth/login` e
`/channels`, e o consumo em *Billing > Included usage* no Render.

## 5. Etapas

### Etapa 0 - ja feita

- [x] API publica em `https://eftv.onrender.com`
- [x] Ping de `/health` a cada 10 min pelo GitHub Actions
- [x] Documentacao de deploy atualizada

### Etapa 1 - migrar o banco para o Supabase

- [ ] Criar projeto no Supabase, regiao **East US (North Virginia)**: o Render
      esta em Ohio, entao e a regiao mais proxima disponivel.
- [ ] Copiar a connection string do **pooler** (IPv4, porta 6543) e nao a
      conexao direta (IPv6).
- [ ] Ajustar o backend (ver secao 6).
- [ ] Rodar `alembic upgrade head` e o seed.
- [ ] Trocar `DATABASE_URL` no Render e validar login/catalogo.
- [ ] So depois de validar, apagar o Postgres free do Render.

### Etapa 2 - e-mail pela Brevo

- [ ] Criar conta e verificar um remetente.
- [ ] Implementar envio via API `https://api.brevo.com/v3/smtp/email`.
- [ ] Variaveis: `BREVO_API_KEY` e `EMAIL_FROM`; manter Resend como opcao.
- [ ] Testar cadastro de um e-mail externo.

### Etapa 3 - backup

- [ ] Workflow noturno com `pg_dump -Fc`, cifrado com `gpg --symmetric`.
- [ ] Segredo `BACKUP_PASSPHRASE` no GitHub; nunca subir dump sem cifra
      (o repositorio e publico).
- [ ] Testar o restore em banco local antes de confiar no backup.

### Etapa 4 - ping redundante

- [ ] Criar monitor no cron-job.org: `GET /health`, 5 min, com alerta por
      e-mail em caso de falha.
- [ ] Manter o workflow do GitHub como reserva.

### Etapa 5 - abrir para um grupo pequeno

- [ ] 10 a 20 usuarios, com suporte por WhatsApp/Telegram.
- [ ] Acompanhar erros, tempo de resposta e consumo das cotas por uma semana.
- [ ] Corrigir o que aparecer antes de divulgar mais.

### Etapa 6 - gatilho de migracao para pago

Migrar quando a receita pagar a infra, nao antes:

- Render Starter (~US$ 7) = sem hibernar e sem cota de horas;
- banco do Render Basic (~US$ 6) ou Supabase Pro (~US$ 25), conforme o caso.

Com 3 a 5 assinantes de R$ 20-30, a infra ja se paga.

## 6. Detalhes tecnicos da migracao do banco

### URL de conexao

O provedor entrega algo como:

```
postgresql://postgres.<ref>:SENHA@aws-0-us-east-1.pooler.supabase.com:6543/postgres
```

O `backend/app/config.py` ja converte `postgresql://` para
`postgresql+asyncpg://` e `sslmode=require` para `ssl=require`. Falta:

1. remover `channel_binding=require` (o asyncpg nao aceita esse parametro);
2. para o pooler em modo transaction (porta 6543), desligar o cache de
   prepared statements: `statement_cache_size=0` e
   `prepared_statement_cache_size=0` no `connect_args`.

Para migrations e seed, usar a porta **5432** (modo session) ou a conexao
direta, porque o modo transaction nao suporta todos os recursos.

### Pool

Manter `DATABASE_POOL_SIZE=3` e `DATABASE_MAX_OVERFLOW=2`. O Supabase free tem
limite de conexoes por compute; pool pequeno evita erro de `too many
connections`.

### O que ja ajuda

- `/health` nao consulta o banco, entao o ping nao gasta computacao do
  Supabase.
- O campo `DATABASE_URL` e o unico ponto de configuracao: nenhuma rota precisa
  mudar.

### Arquivos que mudam em cada etapa

| Etapa | Arquivos |
| --- | --- |
| 1. Banco | `backend/app/config.py`, `backend/app/database.py`, `render.free.yaml`/`render.yaml`, `android/local.properties` (nao versionado) |
| 2. E-mail | `backend/app/services/email_service.py`, `backend/app/config.py` |
| 3. Backup | `.github/workflows/backup.yml` (novo) |
| 4. Ping | `.github/workflows/keepalive.yml` (ajuste de 10 para 5 min) |
| 5. Go-live | `docs/PLANO-GRATUITO.md` (checklist), `README.md` |

## 7. Riscos aceitos

- Sem SLA e sem backup do provedor: a copia e a nossa (etapa 3).
- O Render pode reiniciar o servico free a qualquer momento.
- Se estourar banda ou horas, os servicos free ficam suspensos ate o proximo
  mes; e a principal razao para abrir devagar.
- Sem dominio proprio: a URL e `eftv.onrender.com` e os e-mails saem com o
  remetente do Brevo. Isso e aceitavel para testar com conhecidos, nao para
  marca.

## 8. Checklist de go-live

- [ ] Banco migrado e restore do backup testado
- [ ] Cadastro e verificacao de e-mail funcionando com e-mail externo
- [ ] Ping redundante ativo e alertando
- [ ] APK assinado publicado em Releases
- [ ] Admin com senha forte e 2FA no GitHub/Render/Supabase
- [ ] Politica de privacidade e termos (LGPD) publicados
- [ ] Mercado Pago com webhook testado em sandbox
- [ ] Consumo das cotas anotado semanalmente

## 9. Pendencias

- Quantos usuarios sao esperados no primeiro mes.
- O app sera cobrado desde o inicio ou tera periodo gratuito.
- O provedor da playlist permite quantas conexoes simultaneas (isso e custo
  por usuario, independente da hospedagem).
- Vale registrar um dominio proprio depois da primeira receita.

## 10. Historico

| Data | Mudanca |
| --- | --- |
| 2026-11-07 | Criacao do plano; stack R$ 0 definida; etapas 1 a 6 |
