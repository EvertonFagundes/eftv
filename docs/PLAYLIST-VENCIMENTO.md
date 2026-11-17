# Vencimento da playlist licenciada

A `.m3u` **não carrega a data de validade**: ela é só uma lista de canais
(`#EXTM3U`, `#EXTINF`, URLs). O vencimento existe na conta do provedor, não no
arquivo. Estas são as formas de descobrir, da mais confiável para a menos.

## 1. API do provedor (Xtream Codes)

Quando o link tem `get.php?username=...&password=...`, o mesmo servidor expõe
uma API de conta. Troque `get.php` por `player_api.php`, mantendo usuário e
senha:

```
http://HOST:PORTA/player_api.php?username=USUARIO&password=SENHA
```

```json
"user_info": {
  "auth": 1,
  "status": "Active",
  "exp_date": "1798761600",
  "is_trial": "0",
  "active_cons": "1",
  "max_connections": "1"
}
```

- `exp_date` é Unix em **segundos** (às vezes vem `null` em conta sem prazo).
- `status` resume a resposta: `Active`, `Expired` ou `Banned`.
- `max_connections` diz quantos aparelhos o plano permite de fato — é o que
  limita o "2 aparelhos" do EFTV.

No PowerShell:

```powershell
$u = "USUARIO"; $p = "SENHA"; $h = "http://HOST:PORTA"
$r = Invoke-RestMethod "$h/player_api.php?username=$u&password=$p"
$r.user_info | Select-Object status, exp_date, is_trial, max_connections
[DateTimeOffset]::FromUnixTimeSeconds([int64]$r.user_info.exp_date).ToLocalTime()
```

## 2. Procurar no arquivo

Muitos provedores publicam o vencimento como se fosse um canal ou um grupo:

```powershell
Select-String -Path .\lista.m3u -Pattern "vencim|expira|v[aá]lido" -CaseSensitive:$false
```

Aparece algo como `#EXTINF:-1 tvg-name="VENCIMENTO 20/12/2026"`.

## 3. Teste do stream (último recurso)

Se todos os canais param ao mesmo tempo com `401/403`, a conta venceu. É o
sintoma, não a informação: o app só mostra "canal indisponível" e o assinante
descobre antes de nós.

---

## No backend (`GET /admin/playlist/expiry`)

Implementado em `app/services/playlist_expiry.py`. O endpoint:

1. troca `get.php` por `player_api.php` mantendo usuário/senha e lê
   `user_info.exp_date`, `status`, `max_connections` e `is_trial`;
2. se a API de conta falhar, baixa o início do `.m3u` e procura
   `VENCIMENTO`/`Validade: dd/mm/aaaa`;
3. guarda o resultado em memória por **6 horas** (`?refresh=true` ignora);
4. devolve apenas o host do provedor — nunca usuário, senha ou URL completa.

```
GET https://eftv.onrender.com/admin/playlist/expiry
Authorization: Bearer <token de admin>
```

```json
{
  "expires_at": "2026-12-31T23:59:00Z",
  "days_remaining": 44,
  "expired": false,
  "active": true,
  "status": "Active",
  "max_connections": 2,
  "is_trial": false,
  "source": "player_api",
  "provider_host": "pthdtv.top",
  "error": null,
  "from_cache": false
}
```

**Restrito** a `evertonfagundes1510@gmail.com` (ajustável por
`PLAYLIST_EXPIRY_EMAILS`, lista separada por vírgula). Qualquer outro admin
recebe `403`; sem `IPTV_PLAYLIST_URL` no servidor, `503`.

## Pendência conhecida

- O endpoint depende do `IPTV_PLAYLIST_URL` configurado no Render. Enquanto o
  provedor estiver com DNS fora do ar, a resposta vem `source: "unavailable"`
  com o motivo em `error` — é diagnóstico, não vencimento.
- Aviso automático por e-mail alguns dias antes do vencimento ainda não existe:
  por ora a data aparece no painel quando consultada.

