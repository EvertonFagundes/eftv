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

## Pendência de produto

Hoje nem o app nem o backend conhecem essa data. Ideia registrada: o backend
consultar o `player_api.php` **uma vez por dia**, guardar `exp_date` e avisar o
admin (e-mail/painel) alguns dias antes do vencimento, para renovar antes de o
serviço cair. Enquanto isso não existe, a checagem é manual pelo item 1.
