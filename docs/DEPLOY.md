# Deploy do backend EFTV

Guia para publicar a API com PostgreSQL, Redis e HTTPS na sua VPS.
Todo o processo usa Docker; nao e preciso instalar Python no servidor.

> Prefere nao administrar VPS? Veja [`RENDER.md`](RENDER.md): sobe API +
> Postgres com HTTPS em poucos minutos (a partir de ~US$ 13/mes).

## 1. Pre-requisitos

- VPS Linux (Ubuntu 22.04/24.04, Debian ou similar) com acesso SSH e `sudo`.
- Um dominio (ex.: `api.eftv.com.br`).
- DNS: registro `A` do dominio apontando para o IP da VPS.
- Portas `80` e `443` liberadas no firewall.

Teste o DNS antes de subir o Caddy:

```bash
dig +short api.eftv.com.br
```

## 2. Instalar Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker
docker --version
docker compose version
```

## 3. Obter o projeto

```bash
git clone https://github.com/EvertonFagundes/eftv.git
cd eftv
```

## 4. Configurar os segredos

### 4.1 Variaveis do compose

```bash
cp deploy/.env.example deploy/.env
nano deploy/.env
```

Preencha:

```properties
DOMAIN=api.eftv.com.br
POSTGRES_PASSWORD=uma-senha-longa-e-aleatoria
```

### 4.2 Variaveis da aplicacao

```bash
cp backend/.env.example backend/.env
chmod 600 backend/.env
nano backend/.env
```

Preencha no minimo:

```properties
SECRET_KEY=<saida de: openssl rand -hex 32>
IPTV_PLAYLIST_URL=<url licenciada do provedor>
IPTV_PLAYLIST_USER_AGENT=VLC/3.0.20 LibVLC/3.0.20
MAX_DEVICES_PER_SUBSCRIPTION=1
CORS_ORIGINS=["https://app.eftv.com.br"]
FRONTEND_URL=https://app.eftv.com.br
```

> `backend/.env` e `deploy/.env` sao ignorados pelo Git. Nunca faca commit
> deles. O `DATABASE_URL` e sobrescrito automaticamente pelo compose para
> apontar ao container `postgres`.

## 5. Subir os servicos

```bash
docker compose --env-file deploy/.env -f docker-compose.prod.yml up -d --build
```

O Caddy emite o certificado HTTPS sozinho na primeira subida (pode levar
alguns segundos). Acompanhe:

```bash
docker compose --env-file deploy/.env -f docker-compose.prod.yml ps
docker compose --env-file deploy/.env -f docker-compose.prod.yml logs -f caddy
```

## 6. Criar as tabelas

```bash
docker compose --env-file deploy/.env -f docker-compose.prod.yml \
  exec api alembic upgrade head
```

## 7. Criar o primeiro assinante

```bash
docker compose --env-file deploy/.env -f docker-compose.prod.yml \
  exec api python scripts/seed_subscriber.py
```

O comando imprime o e-mail e a senha gerada. Para definir os dados:

```bash
docker compose --env-file deploy/.env -f docker-compose.prod.yml \
  exec -e SEED_EMAIL=cliente@exemplo.com -e SEED_PASSWORD='senha-forte' \
  api python scripts/seed_subscriber.py --days 30
```

Adicione `--admin` para conceder acesso administrativo.

## 8. Validar

```bash
curl https://api.eftv.com.br/health

curl -X POST https://api.eftv.com.br/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@eftv.com.br","password":"SENHA"}'

curl https://api.eftv.com.br/player/playlist \
  -H "Authorization: Bearer <access_token>"
```

O ultimo comando deve retornar `playlist_url` quando a assinatura estiver ativa.

## 9. Apontar o app Android para a API

```bash
cd android
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
  ./gradlew assembleDebug -PEFTV_API_URL=https://api.eftv.com.br
```

Para release assinada, configure o keystore e use `assembleRelease`.

## 10. Atualizar uma versao

```bash
git pull
docker compose --env-file deploy/.env -f docker-compose.prod.yml up -d --build
docker compose --env-file deploy/.env -f docker-compose.prod.yml \
  exec api alembic upgrade head
```

## 11. Backup e restauracao

Backup do banco:

```bash
docker compose --env-file deploy/.env -f docker-compose.prod.yml \
  exec -T postgres pg_dump -U postgres eftv | gzip > eftv-$(date +%F).sql.gz
```

Restauracao:

```bash
gunzip -c eftv-AAAA-MM-DD.sql.gz | \
  docker compose --env-file deploy/.env -f docker-compose.prod.yml \
  exec -T postgres psql -U postgres -d eftv
```

## 12. Seguranca

- O Postgres e o Redis **nao** expoem porta no host; so a 80/443 (Caddy) e a
  8000 em `127.0.0.1`.
- Mantenha `backend/.env` com permissao `600`.
- Troque a credencial da playlist se ela ja tiver sido exposta.
- Use `sudo ufw allow OpenSSH && sudo ufw allow 80,443/tcp && sudo ufw enable`.
- O `SECRET_KEY` invalida todos os tokens quando trocado; faca isso apenas se
  necessario.
