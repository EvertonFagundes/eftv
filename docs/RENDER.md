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

## Quando o plano free serve

O free nao e "servidor de producao de graca", e sim um **ambiente de teste
publico** com HTTPS. Ele serve para:

- validar o app no celular usando 4G (sem depender do PC ligado na mesma rede);
- testar login, catalogo, vinculo/revogacao de aparelho e o player;
- mostrar o produto para um cliente ou socio antes de fechar;
- desenvolver o frontend/checkout sem gastar nada.

Ele **nao** serve para cliente pagante por tres motivos objetivos:

| Limitacao | Efeito no cliente |
| --- | --- |
| Hiberna apos 15 min sem trafego | Primeiro acesso do dia demora ~1 min ou o app parece fora do ar |
| Postgres expira em 30 dias | Perda de usuarios, assinaturas e vinculos de aparelho |
| Sem Shell e sem pre-deploy | Nao da para rodar migracao/seed pelo dashboard |

Se o objetivo for so testar agora, use o [`render.free.yaml`](../render.free.yaml):
ele cria os mesmos servicos no plano free e roda `alembic upgrade head` junto
com a inicializacao (o free nao tem pre-deploy command).

1. Render: **New > Blueprint** > repositorio.
2. Em **Blueprint Path**, informe `render.free.yaml`.
3. Preencha `IPTV_PLAYLIST_URL` e clique em **Apply**.
4. Use `https://eftv.onrender.com` no app, como no passo 4 abaixo.

Criar o assinante de teste sem Shell (na sua maquina):

```bash
cd backend
DATABASE_URL='<External Database URL do Render>' \
  python scripts/seed_subscriber.py --email teste@eftv.com.br --admin --days 30
```

O `External Database URL` fica em *eftv-db > Connect*. Em *Access Control*,
libere o IP da sua maquina (ou `0.0.0.0/0` temporariamente).

Quando for atender cliente de verdade, aplique o [`render.yaml`](../render.yaml)
(mesmos nomes de servico): o Render troca os planos e o banco e preservado.

## Manter a API acordada (opcional, so para teste)

O workflow [`.github/workflows/keepalive.yml`](../.github/workflows/keepalive.yml)
faz `GET /health` a cada 10 minutos. E o suficiente para o Render nao hibernar,
entao o primeiro acesso do cliente deixa de esperar ~1 minuto.

Ele roda sozinho, sem servico externo. Para conferir: aba **Actions** >
**Manter API acordada** > **Run workflow**.

Limites dessa abordagem:

- consome as 750 horas de instancia free do mes (~730h em um mes de 31 dias);
- nao impede o Postgres free de expirar em 30 dias;
- o GitHub pode atrasar execucoes agendadas em horarios de pico;
- se o repositorio ficar 60 dias sem atividade, o GitHub desativa o agendamento.

Se o plano for atender cliente pagante, troque para Starter + Basic: sai mais
barato do que manter esse esquema e nao tem esses riscos.

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

A API esta publicada em `https://eftv.onrender.com`.

```bash
curl -fsS https://eftv.onrender.com/health
# {"status":"ok","version":"1.0.0"}
```

Teste o login:

```bash
curl -s -X POST https://eftv.onrender.com/auth/login \
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
EFTV_API_URL=https://eftv.onrender.com
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
