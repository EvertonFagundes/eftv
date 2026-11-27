# Estado atual do EFTV — handoff

Última atualização: 27/11/2026, ~20:00 (America/Sao_Paulo).

Este arquivo existe para continuar o trabalho em outra máquina sem perder
contexto. Leia junto com `TODO.md`.

---

## 1. Versões

| Item | Valor |
| --- | --- |
| App Android instalado no aparelho de teste | **1.5.23 (`versionCode 48`)** |
| Última tag/release | `v1.5.23` |
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

## 2. O que já está funcionando

### Catálogo local (não reimporta a cada abertura)

- A importação só roda na primeira vez ou quando o catálogo salvo é inválido.
- Abrir o app com o catálogo salvo mostra a lista na hora, sem "Importando".
- Importação interrompida é recuperada por `CatalogStore.recoverInterruptedImport()`.
- **Correção desta rodada:** `CatalogStore.replace()` só apaga o catálogo quando
  chega o **primeiro canal**. Se a origem devolver texto vazio (ex.: página de
  erro do provedor), a lista salva permanece intacta.
  - Arquivo: `android/app/src/main/java/com/eftv/android/data/CatalogStore.kt`
  - Commit: `4ab350a`

### Importação progressiva

- Lotes de 2.000 itens commitados no SQLite.
- O primeiro lote libera a lista; os seguintes só atualizam contagem e páginas.
- `series_cards` é alimentado lote a lote com `INSERT OR IGNORE` + `UPDATE`.

### Fallback de dados móveis

Ordem de tentativa em `PlaylistRepository`:

1. Proxy local com DoH (2 tentativas, a segunda com `&doh=1`).
2. **Backend** `GET /player/playlist-text` (autenticado, HTTPS).
3. Download direto (último recurso).

O endpoint do backend está implementado e deployado:

- `backend/app/routes/player.py` → `get_playlist_text()`
- Sem token responde **401** (não 404), confirmando que existe em produção.
- Segue até 5 redirecionamentos, valida SSRF e limita a 32 MB.

### Keepalive do Render

- `.github/workflows/keepalive.yml`: corrente de `workflow_dispatch` a cada
  ~9 min (`inputs.delay=540`); cron `*/5 * * * *` apenas como reserva.
- Execuções em cadeia confirmadas no GitHub Actions.
- `backend/app/main.py` também tem `self_ping` a cada 5 min.

---

## 3. Importação em 4G (resolvida em 27/11)

### Sintoma

Com Wi-Fi desligado e 4G ligado, ao tocar em **Atualizar lista**:

```
W/EFTV: Proxy local falhou na tentativa 1: java.net.SocketTimeoutException: timeout
W/EFTV: Proxy local falhou na tentativa 2: java.net.SocketTimeoutException: Read timed out
W/EFTV: Playlist pelo backend: 235 bytes, formato=desconhecido
E/EFTV: Falha ao baixar/processar a playlist: java.io.IOException: A playlist nao retornou nenhum canal.
```

- O proxy local falha porque a operadora (Claro) bloqueia o DNS de `rtv30t.com`
  (em teste anterior: `UnknownHostException`), e o DoH também não passa.
- O fallback pelo backend **autentica e responde 200**, mas o conteúdo tem
  **235 bytes** e é a página padrão do nginx:

```html
<!DOCTYPE html><html><head><title>Welcome to nginx!</title></head>...
```

Ou seja: o caminho técnico do 4G funciona; **a URL configurada no servidor não
aponta para a playlist**.

### O que o usuário fez

O usuário informou que trocou `IPTV_PLAYLIST_URL` no painel do Render e que o
deploy estava em andamento. O reteste após o deploy ainda devolveu os mesmos
235 bytes (página do nginx) no momento em que este documento foi escrito.
Uma última tentativa de reteste ficou **inconclusiva**: o aparelho foi
desconectado do PC (PC sendo desligado) e o ADB perdeu o dispositivo.

### Hipótese principal a verificar

`backend/app/routes/player.py` usa **duas fontes**, nesta ordem:

```python
url = (_provider_url(subscription) or settings.IPTV_PLAYLIST_URL).strip()
```

- `_provider_url()` devolve `subscription.provider_playlist_url` quando existe e
  não foi revogada (linha própria do assinante, definida no painel admin).
- **Se a conta de teste tiver uma linha própria cadastrada, ela tem precedência
  sobre `IPTV_PLAYLIST_URL`** — trocar a env var não muda nada para essa conta.
- Verificar no painel admin a assinatura da conta usada no aparelho e limpar o
  campo de linha própria, ou corrigir a URL dela.
- Rotas relacionadas em `backend/app/routes/admin.py` (linhas ~604-666).

### Correção aplicada em 27/11 (backend 1.2.2)

`GET /player/playlist-text` não usa mais uma única URL sem validação. Ele tenta,
nesta ordem:

1. linha própria da assinatura;
2. `IPTV_PLAYLIST_URL` (se for diferente).

Para cada uma, só aceita resposta cujo conteúdo comece com `#EXTM3U` ou
`#EXTINF`. Uma página do nginx, login do provedor ou HTTP 200 vazio é descartado
e a próxima fonte é tentada. Os logs mostram apenas o rótulo da fonte e o
motivo/tamanho, nunca a URL com credenciais. Com isso, uma linha própria errada
não bloqueia mais o 4G quando a playlist compartilhada está correta; se as duas
estiverem erradas, o retorno é 502 com o motivo de cada uma.

### Reteste em 4G: concluído em 27/11/2026

Com o backend **1.2.2** em produção, Wi-Fi desligado e **LTE da Claro**:

- "Atualizar lista" mostrou "Importando 0 itens" e evoluiu até **234.000
  itens** em cerca de 2 minutos.
- Status final: **2.264 canais · 19:57 · online**.
- Abas: **33.162 filmes** e **9.738 séries**.
- As capas reais de série carregaram em 4G (007, 011ZE, entre outras).
- PSS ~208 MB durante a importação. No fim, o Wi-Fi foi restaurado e os dados
  móveis desligados.
- O build de release só registra WARN+ no logcat (`EftvApplication`), então a
  importação bem-sucedida não gera linha de log; a validação foi visual.

### Outras hipóteses, em ordem

1. Deploy do Render ainda não concluído quando o teste rodou (retestar depois).
2. `IPTV_PLAYLIST_URL` salva com caminho incompleto (ex.: só o domínio, sem
   `/get.php?username=...&password=...`), retornando o site padrão do nginx.
3. Provedor exige `IPTV_PLAYLIST_USER_AGENT` / `IPTV_PLAYLIST_REFERER`
   diferentes dos configurados e responde a página padrão.

---

## 4. Como retestar (passo a passo)

### Pré-requisitos

- Celular conectado e autorizado no ADB (`adb devices` mostra `device`).
- App 1.5.23 instalado.
- Wi-Fi desligado e dados móveis ligados.

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
| `Catalogo importado` | Importação concluída |
| `Falha ao baixar/processar a playlist` | Nenhum canal no texto recebido |

O log mostra apenas tamanho e formato — **não** imprime o conteúdo da playlist
(que contém credenciais).

### Verificação na tela

O status deve mostrar algo como `●  33.162 filmes • HH:MM • online` e a aba
"Ao Vivo" por volta de `2.264 canais`. Depois de uma importação bem-sucedida o
horário do status é atualizado.

---

## 5. Variáveis do Render a conferir

Atualizar para a versão atual (o usuário faz isso manualmente no painel):

```
APP_LATEST_VERSION_CODE=48
APP_LATEST_VERSION_NAME=1.5.23
APP_APK_URL=https://github.com/EvertonFagundes/eftv/releases/download/v1.5.23/eftv-v1.5.23.apk
```

E, para a importação em 4G:

```
IPTV_PLAYLIST_URL=<URL completa da M3U, com usuário e senha>
IPTV_PLAYLIST_USER_AGENT=<se o provedor exigir>
IPTV_PLAYLIST_REFERER=<se o provedor exigir>
```

`IPTV_PLAYLIST_URL` é `sync: false` no `render.yaml`: **nunca** vai para o
repositório. Não commitar credenciais.

---

## 6. Estado do aparelho de teste

- O aparelho foi **desconectado do PC** no fim da sessão (o PC foi desligado).
  Pode ter ficado com **Wi-Fi desligado e dados móveis ligados**. Ao retomar,
  restaurar com os comandos da seção 4.
- O catálogo salvo tem ~33.162 filmes e ~2.264 canais ao vivo; a lista **não**
  é apagada quando a importação falha.

---

## 7. Pendências

1. [x] Importação em 4G validada em 27/11 (~19:57), com o backend 1.2.2:
   234.000 itens, 2.264 canais, 33.162 filmes, 9.738 séries e capas em 4G.
2. [x] `APP_LATEST_*` confirmado no Render (`/app/version` responde
   1.5.23/48 em 27/11).
3. [ ] Primeira montagem do índice em instalação limpa (v5 → v6): medir em um
   aparelho sem o índice pronto. Se passar de ~20 s, montar em segundo plano.
4. [ ] Opcional: investigar o logo trocado de "Round 6 O Desafio" (o provedor
   entrega uma capa que não é a do IMDb).

## 8. Arquivos-chave

| Arquivo | Papel |
| --- | --- |
| `backend/app/routes/player.py` | `/player/playlist`, `/player/playlist-text`, precedência da URL |
| `backend/app/routes/admin.py` | linha própria do assinante (`provider_playlist_url`) |
| `android/.../data/PlaylistRepository.kt` | proxy local, fallback e timeouts |
| `android/.../data/CatalogStore.kt` | importação atômica e recuperação de cache |
| `android/.../MainActivity.kt` | `configureRepository`, `refreshCatalog`, log do backend |
| `android/.../data/LocalServer.kt` | `remotePlaylistUrl(target, forceDoh)` |
| `android/.../python/server.py` | handler `/api/playlist-remote` (parâmetro `doh=1`) |
| `.github/workflows/keepalive.yml` | corrente de pings do Render |
| `docs/RENDER.md` | documentação do keepalive |
