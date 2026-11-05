# Deploy no Render

O Render hospeda a API em Docker, cria o Postgres gerenciado e emite HTTPS
sozinho. E o caminho mais curto para sair do "so na rede local" sem cuidar de
VPS, DNS e Caddy.

## Custos (2026)

| Recurso | Plano | Observacao |
| --- | --- | --- |
| `eftv-api` | `0.5c-512mb` (Starter) | ~US$ 7/mes, nao hiberna |
| `eftv-db` | `0.1c-256mb` (Basic) | ~US$ 6/mes, backup diario |
| Total | | ~US$ 13/mes |

Evite o plano `free` em uso real: o servico hiberna apos 15 minutos sem
trafego (a primeira requisicao demora ~1 minuto) e o Postgres free expira 30
dias depois da criacao, com 14 dias de carencia antes da exclusao.

## 1. Subir pelo Blueprint

O arquivo [`render.yaml`](../render.yaml) ja descreve a API e o banco.

1. No Render: **New > Blueprint** e selecione o repositorio `EvertonFagundes/eftv`.
2. Confirme o servico `eftv-api` e o banco `eftv-db`.
3. O Render vai pedir os valores marcados com `sync: false`:
   - `IPTV_PLAYLIST_URL` - URL licenciada do provedor;
   - `IPTV_PLAYLIST_REFERER` - so se o provedor exigir.
4. Clique em **Apply**. O primeiro deploy roda `alembic upgrade head`
   automaticamente antes de subir a API.

`SECRET_KEY` e gerada pelo Render. Nao coloque segredos no repositorio.

## 2. Conferir

A URL fica no formato `https://eftv-api.onrender.com` (o nome pode variar se
ja existir outro servico com esse nome).

```bash
curl -fsS https://eftv-api.onrender.com/health
# {"status":"ok","version":"1.0.0"}
```

Teste o login:

```bash
curl -s -X POST https://eftv-api.onrender.com/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"SEU_EMAIL","password":"SUA_SENHA"}'
```

## 3. Criar assinante/admin

Com plano pago, use o **Shell** do servico no dashboard:

```bash
python scripts/seed_subscriber.py --email admin@eftv.com.br --admin --days 365
python scripts/seed_subscriber.py --email cliente@exemplo.com --days 30
```

O comando imprime o e-mail, a senha gerada e a validade. Guarde a senha e
troque no primeiro acesso.

No plano free nao existe Shell. Nesse caso rode o script da sua maquina
apontando `DATABASE_URL` para a **External Database URL** do Render (libere o
IP em *Postgres > Access Control*).

## 4. Apontar o app para o Render

No `android/local.properties` (ignorado pelo Git):

```properties
EFTV_API_URL=https://eftv-api.onrender.com
```

Depois:

```bash
cd android
./gradlew assembleDebug
```

Builds de release, sem `EFTV_API_URL`, usam `https://api.eftv.com.br`. Se
quiser usar outro dominio, defina `EFTV_API_URL` no ambiente do build.

## 5. Dominio proprio (opcional)

No dashboard do `eftv-api`: **Settings > Custom Domains**, adicione
`api.eftv.com.br` e crie o CNAME indicado no seu DNS. O certificado HTTPS e
emitido automaticamente.

## Checklist de seguranca

- [ ] `IPTV_PLAYLIST_URL` cadastrada so no Render (nunca no Git/APK).
- [ ] Credenciais antigas da playlist rotacionadas no provedor.
- [ ] `SECRET_KEY` gerada pelo Render e nunca reutilizada.
- [ ] Postgres com backup habilitado (plano Basic ja inclui).
- [ ] Acesso ao dashboard restrito a sua conta.
