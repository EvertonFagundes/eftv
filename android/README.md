# EFTV Android

App nativo de IPTV: lista de canais, categorias, busca e player (ExoPlayer).
Não há WebView como interface principal e o usuário **não escolhe** a playlist.

## Fonte da playlist (única)

A URL **não fica no repositório nem no código-fonte**. Ela é lida de
`local.properties` (arquivo local, ignorado pelo Git) e o build gera
`PlaylistConfig.kt` automaticamente:

```properties
# android/local.properties
EFTV_PLAYLIST_URL=https://sua-fonte-licenciada/...
EFTV_PLAYLIST_USER_AGENT=VLC/3.0.20 LibVLC/3.0.20
EFTV_MAX_CHANNELS=100000
```

- O arquivo `PlaylistConfig.kt` é **gerado em `app/build/`** a cada build e
  está no `.gitignore`; não precisa (nem deve) ser editado à mão.
- O app sempre usa essa constante; não existe tela de configuração.
- Formato aceito: **M3U / M3U8** (`#EXTM3U` + `#EXTINF`), inclusive o padrão
  Xtream Codes (`get.php?...&type=m3u_plus`).
- Se `EFTV_PLAYLIST_URL` ficar vazio, o app carrega
  `app/src/main/assets/sample_playlist.m3u` (streams públicos de demonstração)
  e mostra `• demo` no subtítulo.

### Passo a passo para usar a sua lista

1. Abra `android/local.properties`.
2. Preencha `EFTV_PLAYLIST_URL` com a URL licenciada.
3. Rode o build e instale o APK.

Observação: a URL fica compilada dentro do APK. Qualquer pessoa com o APK
consegue extraí-la — use credenciais que você possa revogar/trocar. No modo
comercial, a URL vem do backend (`GET /player/playlist`), não do APK.

## O que o app faz

- Baixa e interpreta a playlist (linha a linha, sem carregar o arquivo inteiro).
- Deduplica por URL, guarda cache local (`catalog.tsv`) e abre instantaneamente
  nas próximas execuções. O cache é invalidado sozinho quando você troca a
  `PLAYLIST_URL`.
- Se o cache tiver mais de 6 horas, tenta atualizar em segundo plano sem
  esconder a lista.
- Lista canais com logo, nome e categoria; busca por nome (sem acento) e
  filtro por categoria. A busca é pré-calculada por canal para não travar com
  listas grandes.
- Abre o canal no `PlayerActivity` com ExoPlayer (HLS, MPEG-TS, MP4), com
  áudio foco, pausa ao tirar o fone, tela sempre ligada e botão de tentar de novo.
- **Reconexão automática ao vivo**: se o servidor encerrar o stream ou houver
  queda de rede, o player reabre o canal sozinho (espera 1s, 2s, 4s, 8s e
  depois 15s entre tentativas) e volta para o ponto ao vivo, em vez de parar
  no fim do vídeo. Ao sair e voltar para a tela, ele também retoma ao vivo.
- Respeita `#EXTVLCOPT:http-user-agent=` e `http-referrer=` por canal.
- Suporta gzip e redirecionamentos ao baixar a lista.
- Atualização manual pelo ícone no topo ou arrastando a lista para baixo.
- Itens navegáveis por controle remoto (Android TV / D-pad).

### Limite de segurança

`PlaylistConfig.MAX_CHANNELS` (100.000) evita `OutOfMemory` em listas
gigantes. Ao chegar no limite o app avisa que a lista foi truncada; aumente o
valor em `local.properties` se o aparelho tiver memória suficiente.

## Build

```bash
cd android
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 ./gradlew assembleDebug
```

APK: `app/build/outputs/apk/debug/app-debug.apk`

Rodar os testes do parser (não precisa de aparelho):

```bash
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 ./gradlew testDebugUnitTest
```

## Teste

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb logcat | grep -Ei "EFTV|ExoPlayer|AndroidRuntime"
```

## Estrutura

```
app/src/main/java/com/eftv/android/
├── MainActivity.kt          # lista, busca, categorias
├── LoginActivity.kt         # login do assinante
├── PlayerActivity.kt        # ExoPlayer em tela cheia
├── data/
│   ├── Channel.kt
│   ├── M3uParser.kt
│   ├── CatalogCache.kt
│   ├── PlaylistRepository.kt
│   ├── PlaylistSource.kt
│   ├── SessionStore.kt
│   ├── api/EftvApi.kt       # backend central
│   └── TextUtils.kt
└── ui/
    ├── ChannelAdapter.kt
    └── CategoryAdapter.kt
```

`PlaylistConfig.kt` é gerado em `app/build/generated/source/playlistConfig/`
com os valores de `local.properties`.

## Versão antiga (Python/Chaquopy)

A tentativa anterior com Chaquopy + aiohttp + WebView foi movida para
`legacy/` e **não faz parte do build**. Veja `legacy/README.md`.
