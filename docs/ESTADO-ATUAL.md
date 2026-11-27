# Estado atual do EFTV â€” handoff

Ãšltima atualizaÃ§Ã£o: 27/11/2026, ~20:00 (America/Sao_Paulo).

Este arquivo existe para continuar o trabalho em outra mÃ¡quina sem perder
contexto. Leia junto com `TODO.md`.

---

## 1. VersÃµes

| Item | Valor |
| --- | --- |
| App Android instalado no aparelho de teste | **1.5.23 (`versionCode 48`)** |
| Ãšltima tag/release | `v1.5.23` |
| APK de release | https://github.com/EvertonFagundes/eftv/releases/download/v1.5.23/eftv-v1.5.23.apk |
| Backend | Render, `https://eftv.onrender.com` |
| Dispositivo ADB usado | `mfuwk78xwcjf7h9t` |

Commits recentes:

```
385022c docs: atualiza versao instalada para 1.5.23
a5dfc2d chore(android): 1.5.23 (versionCode 48) sem log de conteudo da playlist
6dcfef1 docs: registra validacao em 4G e URL da playlist no Render
fd7888d chore(android): bump versionCode 47 / 1.5.22
6135db7 debug: registra corpo da playlist devolvida pelo backend
4ab350a fix(android): preserva catalogo se playlist vier vazia e registra fallback do backend
```

---

## 2. O que jÃ¡ estÃ¡ funcionando

### CatÃ¡logo local (nÃ£o reimporta a cada abertura)

- A importaÃ§Ã£o sÃ³ roda na primeira vez ou quando o catÃ¡logo salvo Ã© invÃ¡lido.
- Abrir o app com o catÃ¡logo salvo mostra a lista na hora, sem "Importando".
- ImportaÃ§Ã£o interrompida Ã© recuperada por `CatalogStore.recoverInterruptedImport()`.
- **CorreÃ§Ã£o desta rodada:** `CatalogStore.replace()` sÃ³ apaga o catÃ¡logo quando
  chega o **primeiro canal**. Se a origem devolver texto vazio (ex.: pÃ¡gina de
  erro do provedor), a lista salva permanece intacta.
  - Arquivo: `android/app/src/main/java/com/eftv/android/data/CatalogStore.kt`
  - Commit: `4ab350a`

### ImportaÃ§Ã£o progressiva

- Lotes de 2.000 itens commitados no SQLite.
- O primeiro lote libera a lista; os seguintes sÃ³ atualizam contagem e pÃ¡ginas.
- `series_cards` Ã© alimentado lote a lote com `INSERT OR IGNORE` + `UPDATE`.

### Fallback de dados mÃ³veis

Ordem de tentativa em `PlaylistRepository`:

1. Proxy local com DoH (2 tentativas, a segunda com `&doh=1`).
2. **Backend** `GET /player/playlist-text` (autenticado, HTTPS).
3. Download direto (Ãºltimo recurso).

O endpoint do backend estÃ¡ implementado e deployado:

- `backend/app/routes/player.py` â†’ `get_playlist_text()`
- Sem token responde **401** (nÃ£o 404), confirmando que existe em produÃ§Ã£o.
- Segue atÃ© 5 redirecionamentos, valida SSRF e limita a 32 MB.

### Keepalive do Render

- `.github/workflows/keepalive.yml`: corrente de `workflow_dispatch` a cada
  ~9 min (`inputs.delay=540`); cron `*/5 * * * *` apenas como reserva.
- ExecuÃ§Ãµes em cadeia confirmadas no GitHub Actions.
- `backend/app/main.py` tambÃ©m tem `self_ping` a cada 5 min.

---

## 3. ImportaÃ§Ã£o em 4G (resolvida em 27/11)

### Sintoma

Com Wi-Fi desligado e 4G ligado, ao tocar em **Atualizar lista**:

```
W/EFTV: Proxy local falhou na tentativa 1: java.net.SocketTimeoutException: timeout
W/EFTV: Proxy local falhou na tentativa 2: java.net.SocketTimeoutException: Read timed out
W/EFTV: Playlist pelo backend: 235 bytes, formato=desconhecido
E/EFTV: Falha ao baixar/processar a playlist: java.io.IOException: A playlist nao retornou nenhum canal.
```

- O proxy local falha porque a operadora (Claro) bloqueia o DNS de `rtv30t.com`
  (em teste anterior: `UnknownHostException`), e o DoH tambÃ©m nÃ£o passa.
- O fallback pelo backend **autentica e responde 200**, mas o conteÃºdo tem
  **235 bytes** e Ã© a pÃ¡gina padrÃ£o do nginx:

```html
<!DOCTYPE html><html><head><title>Welcome to nginx!</title></head>...
```

Ou seja: o caminho tÃ©cnico do 4G funciona; **a URL configurada no servidor nÃ£o
aponta para a playlist**.

### O que o usuÃ¡rio fez

O usuÃ¡rio informou que trocou `IPTV_PLAYLIST_URL` no painel do Render e que o
deploy estava em andamento. O reteste apÃ³s o deploy ainda devolveu os mesmos
235 bytes (pÃ¡gina do nginx) no momento em que este documento foi escrito.
Uma Ãºltima tentativa de reteste ficou **inconclusiva**: o aparelho foi
desconectado do PC (PC sendo desligado) e o ADB perdeu o dispositivo.

### HipÃ³tese principal a verificar

`backend/app/routes/player.py` usa **duas fontes**, nesta ordem:

```python
url = (_provider_url(subscription) or settings.IPTV_PLAYLIST_URL).strip()
```

- `_provider_url()` devolve `subscription.provider_playlist_url` quando existe e
  nÃ£o foi revogada (linha prÃ³pria do assinante, definida no painel admin).
- **Se a conta de teste tiver uma linha prÃ³pria cadastrada, ela tem precedÃªncia
  sobre `IPTV_PLAYLIST_URL`** â€” trocar a env var nÃ£o muda nada para essa conta.
- Verificar no painel admin a assinatura da conta usada no aparelho e limpar o
  campo de linha prÃ³pria, ou corrigir a URL dela.
- Rotas relacionadas em `backend/app/routes/admin.py` (linhas ~604-666).

### CorreÃ§Ã£o aplicada em 27/11 (backend 1.2.2)

`GET /player/playlist-text` nÃ£o usa mais uma Ãºnica URL sem validaÃ§Ã£o. Ele tenta,
nesta ordem:

1. linha prÃ³pria da assinatura;
2. `IPTV_PLAYLIST_URL` (se for diferente).

Para cada uma, sÃ³ aceita resposta cujo conteÃºdo comece com `#EXTM3U` ou
`#EXTINF`. Uma pÃ¡gina do nginx, login do provedor ou HTTP 200 vazio Ã© descartado
e a prÃ³xima fonte Ã© tentada. Os logs mostram apenas o rÃ³tulo da fonte e o
motivo/tamanho, nunca a URL com credenciais. Com isso, uma linha prÃ³pria errada
nÃ£o bloqueia mais o 4G quando a playlist compartilhada estÃ¡ correta; se as duas
estiverem erradas, o retorno Ã© 502 com o motivo de cada uma.

### Reteste em 4G: concluÃ­do em 27/11/2026

Com o backend **1.2.2** em produÃ§Ã£o, Wi-Fi desligado e **LTE da Claro**:

- "Atualizar lista" mostrou "Importando 0 itens" e evoluiu atÃ© **234.000
  itens** em cerca de 2 minutos.
- Status final: **2.264 canais Â· 19:57 Â· online**.
- Abas: **33.162 filmes** e **9.738 sÃ©ries**.
- As capas reais de sÃ©rie carregaram em 4G (007, 011ZE, entre outras).
- PSS ~208 MB durante a importaÃ§Ã£o. No fim, o Wi-Fi foi restaurado e os dados
  mÃ³veis desligados.
- O build de release sÃ³ registra WARN+ no logcat (`EftvApplication`), entÃ£o a
  importaÃ§Ã£o bem-sucedida nÃ£o gera linha de log; a validaÃ§Ã£o foi visual.

### DiagnÃ³stico definitivo: bloqueio geogrÃ¡fico do provedor (27/11)

O backend **1.2.5** passou a expor em `/health.playlist_probe` (sem URL nem
credenciais) o IP resolvido, o servidor e a primeira linha de cada tentativa.
Com o probe de 27/11 ~23:13 UTC (20:13 em BrasÃ­lia):

- `IPTV_PLAYLIST_URL` Ã© Xtream Codes sobre **HTTP**, porta padrÃ£o, com
  `get.php` e `type` na query (fingerprint seguro da URL: `841cbbca80bd`).
- O Render resolve para `45.134.142.152`/`138.199.11.65`; os dois respondem
  `HTTP 200`, `server: nginx`, **235 bytes** ("Welcome to nginx!").
- Pela borda Cloudflare (`172.67.143.94`/`104.21.87.130`), o `cf-ray` termina
  em `-PDX` (Portland) e a resposta Ã© a mesma pÃ¡gina do nginx. Ou seja, a
  origem recebe a requisiÃ§Ã£o, mas devolve a pÃ¡gina padrÃ£o.
- `player_api.php` pela mesma URL tambÃ©m devolve a pÃ¡gina do nginx: o bloqueio
  atinge o host inteiro, nÃ£o sÃ³ o `get.php`.
- Na rede local no Brasil, a mesma URL devolve `#EXTM3U` e ~84,6 MB.

ConclusÃ£o: o provedor (ou a regra de WAF/geolocalizaÃ§Ã£o na frente dele) nÃ£o
entrega a playlist para IPs de datacenter nos EUA. **NÃ£o Ã© DNS, tamanho,
HTTPS, User-Agent, credenciais nem cÃ³digo do backend.** O Render nÃ£o tem regiÃ£o
na AmÃ©rica do Sul (Oregon/Ohio/Virginia/Frankfurt/Singapura) e o IP dedicado
custaria US$ 100/mÃªs (plano Pro), entÃ£o mudar de regiÃ£o/IP nÃ£o resolve de graÃ§a.

O sucesso do reteste 4G das 19:57 **nÃ£o prova** que o Render entregou a lista:
o app tenta primeiro o proxy local do celular (IP brasileiro) e sÃ³ depois o
backend; o log de release nÃ£o registra qual fonte venceu. Ã‰ provÃ¡vel que o
celular tenha baixado direto pelo proxy/DoH.

SaÃ­das possÃ­veis:

1. Pedir ao provedor para liberar a regiÃ£o/IPs do Render (melhor correÃ§Ã£o; o IP
   de saÃ­da do Render gratuito muda a cada restart).
2. Guardar uma cÃ³pia vÃ¡lida da playlist no backend (Postgres) e servi-la quando
   o provedor bloquear; atualizar por um script local no Brasil. Funciona jÃ¡,
   mas a lista fica defasada atÃ© a prÃ³xima atualizaÃ§Ã£o.
3. Relay em IP residencial/brasileiro (VPS no Brasil ou tÃºnel para a mÃ¡quina
   local), mantendo a atualizaÃ§Ã£o automÃ¡tica; mais infraestrutura.

### Contorno implementado: cache persistente (backend 1.2.7)

- Tabela `playlist_cache` (linha Ãºnica, conteÃºdo gzip) criada no startup por
  `Base.metadata.create_all`.
- `PUT /admin/playlist/cache` (admin) recebe a M3U comprimida; `GET` mostra
  tamanho/idade e `DELETE` limpa. O corpo Ã© validado (`#EXTM3U`/`#EXTINF`) e
  tem limite de 128 MiB descomprimido / 32 MiB comprimido.
- `GET /player/playlist-text` tenta o provedor e, se falhar ou estiver em
  cooldown, serve o cache com `X-Playlist-Source: cache` e
  `X-Playlist-Cache-Age`. Cache com mais de 72 h leva `Warning: 110`.
- ApÃ³s uma falha completa, o backend evita repetir a sequÃªncia lenta por 10 min
  (`recently_failed`); o probe do `/health` continua testando o provedor a cada
  10 min e limpa o cooldown quando volta a funcionar.
- Upload local (rede que alcanÃ§a o provedor):

  ```powershell
  cd C:\Users\evert\eftv\backend
  $env:IPTV_PLAYLIST_URL = "<URL completa do painel do provedor>"
  .\.venv\Scripts\python.exe scripts\upload_playlist_cache.py
  ```

  O script pede e-mail/senha de admin, baixa a M3U, confere o cabeÃ§alho,
  comprime e envia. Ele mostra o **fingerprint** da URL (nunca a URL); compare
  com `/health.playlist_probe.configured.url_fingerprint`. Se for diferente, a
  URL configurada no Render estÃ¡ errada e deve ser corrigida antes do upload.
- O cache contÃ©m as credenciais do provedor nas URLs dos canais: nunca
  versionar, exportar ou colocar em log. O acesso Ã© sÃ³ de admin no upload e de
  assinantes ativos na entrega.
- Enquanto o provedor bloquear o Render, repita o upload periodicamente (ex.:
  semanal) para o catÃ¡logo nÃ£o ficar defasado.

Estado em 27/11: backend **1.2.7** em produÃ§Ã£o (`/health` = 1.2.7,
`/admin/playlist/cache` sem token = 401). O primeiro upload ainda depende de
rodar o script em uma rede que alcance o provedor; atÃ© lÃ¡, o endpoint continua
tentando o provedor e devolve 502 quando nÃ£o hÃ¡ cache.

### Outras hipÃ³teses, em ordem

1. Deploy do Render ainda nÃ£o concluÃ­do quando o teste rodou (retestar depois).
2. `IPTV_PLAYLIST_URL` salva com caminho incompleto (ex.: sÃ³ o domÃ­nio, sem
   `/get.php?username=...&password=...`), retornando o site padrÃ£o do nginx.
3. Provedor exige `IPTV_PLAYLIST_USER_AGENT` / `IPTV_PLAYLIST_REFERER`
   diferentes dos configurados e responde a pÃ¡gina padrÃ£o.

---

## 4. Como retestar (passo a passo)

### PrÃ©-requisitos

- Celular conectado e autorizado no ADB (`adb devices` mostra `device`).
- App 1.5.23 instalado.
- Wi-Fi desligado e dados mÃ³veis ligados.

### Comandos

```powershell
$adb = "C:\Users\Usuario\AppData\Local\Android\Sdk\platform-tools\adb.exe"

# 1. 4G ligado, Wi-Fi desligado
& $adb shell svc wifi disable
& $adb shell svc data enable
Start-Sleep -Seconds 8
& $adb shell dumpsys connectivity | Select-String "MOBILE\[LTE\]"
& $adb shell ping -c 2 8.8.8.8

# 2. Log limpo e app aberto
& $adb logcat -c
& $adb shell am force-stop com.eftv.android
& $adb shell monkey -p com.eftv.android -c android.intent.category.LAUNCHER 1
Start-Sleep -Seconds 12

# 3. Tocar em "Atualizar lista" (bounds 831,132 - 967,267)
& $adb shell input tap 899 199

# 4. Acompanhar o log do app (tag EFTV)
& $adb logcat -s EFTV:*

# 5. Restaurar a rede ao terminar
& $adb shell svc data disable
& $adb shell svc wifi enable
```

### O que procurar no log

| Linha | Significado |
| --- | --- |
| `Playlist pelo backend: N bytes, formato=m3u` | **Sucesso**: veio M3U do backend |
| `Playlist pelo backend: 235 bytes, formato=desconhecido` | URL do servidor ainda errada |
| `Proxy local falhou na tentativa 1/2` | Normal em 4G (DNS bloqueado) |
| `Catalogo importado` | ImportaÃ§Ã£o concluÃ­da |
| `Falha ao baixar/processar a playlist` | Nenhum canal no texto recebido |

O log mostra apenas tamanho e formato â€” **nÃ£o** imprime o conteÃºdo da playlist
(que contÃ©m credenciais).

### VerificaÃ§Ã£o na tela

O status deve mostrar algo como `â—  33.162 filmes â€¢ HH:MM â€¢ online` e a aba
"Ao Vivo" por volta de `2.264 canais`. Depois de uma importaÃ§Ã£o bem-sucedida o
horÃ¡rio do status Ã© atualizado.

---

## 5. VariÃ¡veis do Render a conferir

Atualizar para a versÃ£o atual (o usuÃ¡rio faz isso manualmente no painel):

```
APP_LATEST_VERSION_CODE=48
APP_LATEST_VERSION_NAME=1.5.23
APP_APK_URL=https://github.com/EvertonFagundes/eftv/releases/download/v1.5.23/eftv-v1.5.23.apk
```

E, para a importaÃ§Ã£o em 4G:

```
IPTV_PLAYLIST_URL=<URL completa da M3U, com usuÃ¡rio e senha>
IPTV_PLAYLIST_USER_AGENT=<se o provedor exigir>
IPTV_PLAYLIST_REFERER=<se o provedor exigir>
```

`IPTV_PLAYLIST_URL` Ã© `sync: false` no `render.yaml`: **nunca** vai para o
repositÃ³rio. NÃ£o commitar credenciais.

---

## 6. Estado do aparelho de teste

- O aparelho foi **desconectado do PC** no fim da sessÃ£o (o PC foi desligado).
  Pode ter ficado com **Wi-Fi desligado e dados mÃ³veis ligados**. Ao retomar,
  restaurar com os comandos da seÃ§Ã£o 4.
- O catÃ¡logo salvo tem ~33.162 filmes e ~2.264 canais ao vivo; a lista **nÃ£o**
  Ã© apagada quando a importaÃ§Ã£o falha.

---

## 7. PendÃªncias

1. [x] ImportaÃ§Ã£o em 4G validada em 27/11 (~19:57), com o backend 1.2.2:
   234.000 itens, 2.264 canais, 33.162 filmes, 9.738 sÃ©ries e capas em 4G.
2. [x] `APP_LATEST_*` confirmado no Render (`/app/version` responde
   1.5.23/48 em 27/11).
3. [ ] Primeira montagem do Ã­ndice em instalaÃ§Ã£o limpa (v5 â†’ v6): medir em um
   aparelho sem o Ã­ndice pronto. Se passar de ~20 s, montar em segundo plano.
4. [ ] Opcional: investigar o logo trocado de "Round 6 O Desafio" (o provedor
   entrega uma capa que nÃ£o Ã© a do IMDb).

## 8. Arquivos-chave

| Arquivo | Papel |
| --- | --- |
| `backend/app/routes/player.py` | `/player/playlist`, `/player/playlist-text`, precedÃªncia da URL |
| `backend/app/routes/admin.py` | linha prÃ³pria do assinante (`provider_playlist_url`) |
| `android/.../data/PlaylistRepository.kt` | proxy local, fallback e timeouts |
| `android/.../data/CatalogStore.kt` | importaÃ§Ã£o atÃ´mica e recuperaÃ§Ã£o de cache |
| `android/.../MainActivity.kt` | `configureRepository`, `refreshCatalog`, log do backend |
| `android/.../data/LocalServer.kt` | `remotePlaylistUrl(target, forceDoh)` |
| `android/.../python/server.py` | handler `/api/playlist-remote` (parÃ¢metro `doh=1`) |
| `.github/workflows/keepalive.yml` | corrente de pings do Render |
| `docs/RENDER.md` | documentaÃ§Ã£o do keepalive |
