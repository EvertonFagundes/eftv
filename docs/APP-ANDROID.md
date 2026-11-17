# EFTV Android — documentação técnica

App do assinante para celular, tablet e **Android TV / TV box** (o mesmo APK).
Versão atual: **1.4.5** (`versionCode 20`) · `minSdk 24` · `targetSdk 34` ·
Media3/ExoPlayer 1.3.1 · Kotlin.

> Regra do projeto: o usuário **não** cadastra playlist no app. O catálogo vem
> da playlist licenciada que o backend entrega. Trocar a URL do provedor não
> exige novo APK.

---

## 1. Estrutura do código

```
android/app/src/main/java/com/eftv/android/
├── EftvApplication.kt      # startup, Timber, crash reporter
├── EftvServerService.kt    # servidor local (proxy + catálogo), sem notificação
├── LoginActivity.kt        # login, cadastro, verificação de e-mail, recuperação
├── EmailVerificationActivity.kt
├── MainActivity.kt         # catálogo, abas, busca, categorias, atualização
├── CategoriesActivity.kt   # escolha de categoria com busca e contagem (1.2.1)
├── CastSendActivity.kt     # transmitir a tela do celular para a TV (1.4.1)
├── CastReceiveActivity.kt  # receber a tela na TV / outro aparelho (1.4.1)
├── SeriesActivity.kt       # temporadas/episódios
├── PlayerActivity.kt       # player, sessão de stream, áudio/qualidade
├── SubscriptionActivity.kt # plano, status, assinar, cancelar
├── SettingsActivity.kt     # configurações (inclui conteúdo adulto)
├── cast/                    # transmissão de tela (protocolo, encoder, decoder)
├── data/
│   ├── api/EftvApi.kt      # cliente HTTP do backend (sem libs externas)
│   ├── CatalogStore.kt     # SQLite do catálogo, favoritos, histórico, progresso
│   ├── PlaylistRepository.kt
│   ├── SessionStore.kt     # tokens (access/refresh) + e-mail
│   ├── DeviceIdentity.kt   # id do aparelho (hash do ANDROID_ID)
│   ├── FreeTv.kt           # categoria virtual "Abertos" (filtro por nome)
│   └── LocalServer.kt / PlaylistConfig.kt
├── ui/                     # adapters e views
└── res/                    # layouts, strings, tema
```

Bibliotecas: `core-ktx`, `appcompat`, Material 3, `recyclerview`, `swiperefresh`,
`media3` (exoplayer + hls + ui), Coil (capas), coroutines, Timber, Chaquopy
(Python embutido no servidor local).

---

## 2. Login e sessão

1. `LoginActivity` → `POST /auth/login` → guarda **access** (15 min) e **refresh**
   (dias) em `SessionStore` (SharedPreferences privado).
2. E-mail novo → `POST /auth/register` → 7 dias de teste após confirmar o e-mail
   (`verify-email.html` ou deep link `eftv://verify-email?token=...`).
3. Quando o access expira, o app renova sozinho com `POST /auth/refresh`
   (`tryRefresh()` em `MainActivity`, `SubscriptionActivity` e `PlayerActivity`).
4. Recuperação de senha: `POST /auth/forgot-password` + `POST /auth/reset-password`
   com código por e-mail.

**Aparelhos:** toda requisição autenticada leva `X-Device-Id`
(hash do `ANDROID_ID` — estável entre reinstalações, sem IMEI). O plano permite
2 aparelhos; `GET /player/device` mostra o status e há "desvincular aparelhos"
(`POST /player/device/revoke-all`).

**TV:** o backend já expõe login por código (`/auth/device-code`,
`/auth/device-code/poll`, `/auth/device-code/approve`) para o dia em que a tela
de TV pedir o código. Ver `docs/TV.md`.

---

## 3. Catálogo e navegação

- `PlaylistRepository.refresh()` baixa o catálogo autorizado e grava no SQLite
  (`CatalogStore`) — útil offline e para abrir o app rápido.
- Cache válido por 6 h; depois o app atualiza em segundo plano
  (`swipeRefresh` para puxar na hora).
- **Abas**: Ao Vivo / Filmes / Séries. Canais em lista; filmes e séries em grade
  de capas.
- **Busca**: nome do canal **e** nome do grupo, sem acento/maiúsculas
  (`name_key`, `group_key`), com *debounce* de 250 ms.
- **Categorias (1.2.1)**: o botão abre `CategoriesActivity` — cartões com ícone,
  nome e **quantidade de itens**, busca dentro das categorias, destaque da atual.
  Substituiu o menu suspenso que empilhava dezenas de grupos sem contexto.
  Os ícones são do **Material Symbols** (Apache 2.0), baixados do repositório
  oficial `google/material-design-icons` e convertidos para vector drawable com
  `viewportWidth/Height = 960` + `translateY = 960` (o SVG original usa
  `viewBox="0 -960 960 960"`). Prefixo "Canais | " do provedor é removido só na
  exibição; o filtro continua usando o nome completo do grupo.
- **Abertos (1.2.1)**: categoria virtual (`data/FreeTv.kt`) que reúne por **nome
  do canal** as emissoras abertas (Globo, Record, SBT, Band, RedeTV, Cultura, TV
  Brasil, Gazeta, Aparecida, Canção Nova, Rede Vida, TV Senado/Câmara/Justiça
  etc.), mesmo que a playlist as espalhe em "Canais | Globos Sudeste",
  "Canais | RecordTV"... Os canais **continuam nas categorias originais** e
  aparecem também em Abertos. Famílias pagas são excluídas (GloboNews, Globoplay,
  Premiere, Telecine, Band Sports, Band News); o grupo da playlist com "aberto"
  no nome também entra, para não perder emissora local.
- **Barra A-Z (1.2.0)**: `AlphabetIndexView` na lateral da lista ao vivo
  (aparece com 80+ itens, escondida na TV). Tocar/arrastar pula para a primeira
  letra via `CatalogStore.firstIndexForLetter` — resolve "rolar 2 mil canais".
  A lista reserva `paddingEnd="26dp"` e a barra tem fundo próprio para não cobrir
  as estrelas de favorito. Em 1.2.1 o SQL do salto foi corrigido (gerava
  `WHERE WHERE` e derrubava o app) e o salto roda em `runCatching`.
- **Transmitir tela (1.4.1)**: menu ⋮ → **Transmitir tela** no celular e
  **Receber tela** na TV. O celular captura com `MediaProjection`, codifica em
  H.264 (720p, 4 Mbps, 30 fps) e envia por TCP; a TV acha o celular por PIN +
  mDNS (`_eftvcast._tcp`) e decodifica com `MediaCodec` direto na `Surface`.
  O som vai no mesmo socket em AAC-LC (44,1 kHz estéreo, 128 kbps) e toca num
  `AudioTrack` (`AacPlayer`), capturado com `AudioPlaybackCaptureConfiguration`
  — Android 10+ e permissão `RECORD_AUDIO`; negada, transmite só imagem.
  **Sincronia (1.4.1)**: as duas trilhas usam o mesmo carimbo de tempo
  (`System.nanoTime()`) e a TV agenda cada amostra num `PresentationClock`
  comum (âncora na primeira amostra + 150 ms); atraso acima de 400 ms (vídeo)
  ou 250 ms (som) é descartado em vez de virar fila. O som só começa depois do
  primeiro quadro de vídeo, para herdar a base de tempo da imagem.
  No **Android 14+** o diálogo do sistema traz "Share one app" por padrão:
  é preciso trocar para **Tela inteira**, senão só o EFTV aparece na TV (o
  texto da tela avisa isso desde a 1.4.4).
  Não depende de Miracast/Chromecast, então funciona em aparelhos sem
  espelhamento nativo. A captura fica em `CastService`
  (`foregroundServiceType="mediaProjection"`) e continua com o app em segundo
  plano. Limites: mesma rede Wi-Fi, DRM (Netflix/Gloplay) pode ficar preto ou
  mudo, um celular por vez e a orientação não pode mudar no meio.
  Protocolo e servidor têm testes JVM (`CastProtocolTest`, `CastServerTest`
  sobem socket de verdade; `PresentationClockTest` cobre o agendamento).
- **Continuar assistindo**: carrossel com filmes/séries em andamento
  (progresso salvo a cada 5 s).
- **Favoritos** e **Recentes** aparecem como categorias quando têm itens.
- **Conteúdo adulto**: liberado em Configurações; enquanto desligado, grupos e
  itens adultos são filtrados no SQL e nas categorias
  (`ChannelKind.ADULT_GROUP_KEYWORDS`).

---

## 4. Player

`PlayerActivity` (Media3/ExoPlayer, HLS):

- Buffer 15–40 s; até 6 recarregamentos e 2 *soft recoveries*.
- Ao vivo: retoma no ponto ao vivo (offset 8 s) em vez de voltar ao início.
- Filmes/séries: "Continuar assistindo" (não retoma nos primeiros 5 s nem nos
  últimos 10 s) e grava progresso a cada 5 s.
- Controles: play/pause, seek 10 s, faixa de progresso, **áudio** e
  **qualidade** (`TrackSelectionDialogBuilder`), legenda quando o stream oferece.
- Controle remoto de TV: **OK** mostra os controles quando estão escondidos.
- Fechar o player não trava a interface: a liberação da vaga de stream roda fora
  da thread principal.

### Limite de 1 tela (aplicado no servidor)

| Momento | Chamada | Efeito |
|---|---|---|
| Abre o player | `POST /player/play` | abre/reaproveita a sessão do aparelho; se outra tela está ativa → **403 `stream_limit`** e diálogo explicativo |
| Assistindo | `POST /player/heartbeat` (~45 s) | renova a vaga; `409 session_closed` encerra |
| Sai do player | `POST /player/stop` | libera a vaga na hora |
| Esqueceu aberto | tarefa horária no backend | expira em 120 s sem heartbeat |

Se a API falhar (rede/erro), o app **não bloqueia** a reprodução.
O banco guarda só o hash da URL do canal, nunca a URL do provedor.

---

## 5. Assinatura e pagamento

- `SubscriptionActivity` = "Minha assinatura": status, dias restantes,
  pagamento (bandeira + últimos 4), **Assinar**, **Cancelar**, "Atualizar status".
- Checkout: `POST /subscriptions/checkout` → abre `init_point` no navegador.
  Só **cartão de crédito**; R$ 19,90/mês; 2 aparelhos e 1 tela.
- Volta do navegador: deep link **`eftv://open`** reabre o app.
- Conciliação do Mercado Pago roda a cada 5 min no backend e também ao abrir a
  tela — o webhook é otimização, não dependência.
- Cancelamento mantém o acesso até o fim do período pago.

Ver `PAGAMENTOS.md` para o runbook completo.

---

## 6. Atualização e telemetria

**Atualização (fora da Play Store):** `GET /app/version` é consultado no máximo
1×/dia (SharedPreferences `eftv_updates`). Se `APP_APK_URL` estiver configurado no
Render e o `versionCode` for maior, aparece o diálogo (obrigatório ou com
"Depois"). Sem `APP_APK_URL` o app não pergunta nada.

**Erros/travamentos:** handler global em `EftvApplication` envia
`POST /app/crashes` (versão, aparelho, Android, stacktrace; espera máx. 2 s).
Suporte lê em `GET /admin/crashes`.

---

## 7. Build, assinatura e instalação

Pré-requisitos: JDK 17, Android SDK 34, Python 3 (Chaquopy).

```bat
cd C:\Users\evert\eftv\android
.\gradlew.bat assembleRelease
```

- APK: `android\app\build\outputs\apk\release\app-release.apk`
- Conferir versão: `aapt dump badging app-release.apk | findstr version`
- Ao publicar: **suba `versionCode` e `versionName`** em `app/build.gradle.kts`.

**Keystore (nunca no Git):** `android/eftv-release.jks` + `android/keystore.properties`.
Backup em `Documents\EFTV-keystore-backup*` **e na nuvem** — sem essa chave não há
como atualizar quem já instalou.

**Instalar por USB:**

```bat
adb devices
adb install -r android\app\build\outputs\apk\release\app-release.apk
adb shell dumpsys package com.eftv.android | findstr version
```

`INSTALL_FAILED_USER_RESTRICTED` (Xiaomi): aceitar no aparelho e repetir o
`adb install -r`.

**Logs/erros:**

```bat
adb logcat -d -b crash
adb exec-out screencap -p > tela.png
```

---

## 8. Android TV / Fire TV

Já habilitado no manifest: `LEANBACK_LAUNCHER`, `android:banner`, touchscreen
opcional, `uses-feature` de TV. O mesmo APK serve celular e TV.

O que já está pronto na TV:
1. login por **código** ("Entrar pelo celular") — implementado no app e no backend;
2. assinatura por **QR code** (pagar no celular e a TV se libera) — implementado;
3. foco/10-foot UI — parcial (cartões focáveis e OK do controle no player).

Pendente: revisar foco em 1280×720, expor Configurações no menu (hoje é toque
longo) e publicar em Google Play / Amazon Appstore. Detalhes em `docs/TV.md`.

---

## 9. Limitações conhecidas

- Distribuição por APK: atualização automática depende de `APP_APK_URL` no Render.
- Sem Play Store: sem cobrança pela loja e sem instalação automática.
- **Log no APK de release (1.4.4)**: o `Timber` é plantado sempre, não só em
  build de debug. Sem isso um problema no aparelho do cliente ("não conecta",
  "fecha sozinho") chegava sem pista nenhuma e a investigação era às cegas.
  `adb logcat` continua sendo leitura privada do sistema desde o Android 4.1.
- **Erro de conexão do cast (1.4.5)**: antes a mensagem real ("não foi possível
  conectar", "PIN incorreto") era trocada por "o Android encerrou a captura" e
  o serviço morria em ~100 ms. Agora a causa aparece na tela e fica 6 s.
- O receptor (`CastServer`) loga tentativas, PIN errado, quedas e abertura do
  socket com a tag `Receber tela:`. Ao conferir a porta, lembre que o Java pode
  abrir o `ServerSocket` em IPv6: nesse caso ele aparece em `/proc/net/tcp6`,
  não em `/proc/net/tcp`.
- O servidor local embutido (proxy) existe para contornar bloqueio de DNS em
  dados móveis; em TV box ele sobe igual. Desde a 1.4.2 ele **não** é mais um
  serviço de primeiro plano, então não aparece notificação fixa — em troca, o
  Android pode encerrá-lo junto com o app muito tempo em segundo plano (ele
  volta quando o app abre).
- Desde a 1.4.3 o servidor embutido escuta **apenas em `127.0.0.1`**: outro
  aparelho na rede Wi-Fi não alcança mais o `:8124`. O que deixa de funcionar é
  abrir a EFTV no navegador de uma TV/PC apontando para o IP do celular — nesse
  caso use o app da TV. A versão web (`server.py`) no PC continua com `--lan`
  quando você quiser expor de propósito.
- Sem EPG, zapping por número, legendas embutidas do provedor e PIN infantil
  (dependem dos dados do provedor).
