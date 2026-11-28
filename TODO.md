# Pendências — correções de 25/11/2026

> **Retomada em outra máquina:** leia `docs/ESTADO-ATUAL.md`. Ele tem versões,
> comandos de teste em 4G, hipóteses e o que falta para concluir.

## Correção de 27/11/2026 — keepalive e importação em dados móveis

- [x] **Backend dormindo.** O cron do GitHub agendava 5 min, mas entregava só
  ~3 execuções/dia (buracos de até 16h). O `self_ping` morria junto com o
  processo e não acordava a instância. Agora o keepalive é uma corrente contínua
  de `workflow_dispatch` a cada ~9 min; o cron virou reserva. `self_ping` usa a
  URL pública e registra falhas.
- [x] **Aviso do tempo de importação.** A tela informa que pode levar alguns
  minutos e que o que já chegou pode ser assistido.
- [x] **Lista progressiva.** Cada lote commitado (2.000 itens) atualiza a UI.
  O primeiro lote libera a lista; os seguintes só atualizam contagem e páginas
  já carregadas, sem reiniciar a paginação/aba Séries.
- [x] **Séries durante a importação.** `series_cards` passa a ser alimentado
  lote a lote (com `INSERT OR IGNORE` + `UPDATE`, compatível com SQLite antigo).
- [x] **Importação em dados móveis.** O proxy local agora é esperado por até 30 s,
  tem segunda tentativa com DoH forçado (`&doh=1`) e só depois cai para o
  download direto. `resolveSource` tenta de novo se o Render estiver acordando
  e o timeout de leitura subiu para 120 s. Redirecionamentos mantêm cookies e
  não permitem `https -> http`.

- [x] **Importação repetida ao abrir o app.** O catálogo agora só é importado
  na primeira vez (ou quando o usuário toca em "Atualizar lista"). Se o app
  for fechado no meio de uma importação, `recoverInterruptedImport()` valida os
  lotes já commitados como cache, em vez de apagar tudo e recomeçar.

Estado: 1.5.25 (`versionCode 50`), 251 testes do backend, 62 testes JVM do
Android e APK de release assinado OK.

### Validação em 4G (aparelho conectado)

- Wi-Fi desligado, dados móveis ligados: conectividade OK (`ping 8.8.8.8`).
- O app abriu e carregou o catálogo salvo sem importar de novo (meta confirmada).
- Ao forçar "Atualizar lista": proxy local deu timeout nas duas tentativas e o
  download direto falhou com `UnknownHostException` para `rtv30t.com` (DNS da
  operadora bloqueado) — era exatamente o cenário que o fallback do backend
  resolve.
- **Bloqueio encontrado:** o backend acessa a URL configurada, mas ela devolve
  uma página padrão do nginx ("Welcome to nginx!", 235 bytes), não uma playlist.
  O URL licenciado está no painel do Render (`IPTV_PLAYLIST_URL`, `sync: false`)
  e precisa ser corrigido pelo usuário. Com URL válida, o fallback por HTTPS do
  backend completa a importação em dados móveis.
- `CatalogStore.replace()` agora só limpa o catálogo quando chega o primeiro
  canal: uma playlist vazia não apaga mais a lista salva no aparelho.
- **Reteste após o usuário trocar `IPTV_PLAYLIST_URL` no Render:** ainda retornou
  235 bytes de página padrão do nginx. O fallback autentica (HTTP 200), então o
  problema é a URL/conteúdo, não o caminho em 4G. Suspeita principal: a
  assinatura da conta de teste tem `provider_playlist_url` (linha própria)
  cadastrada, que tem precedência sobre a env var em `player.py`. Detalhes em
  `docs/ESTADO-ATUAL.md`.

- [x] **Reteste em 4G concluído (27/11, ~19:57).** Com o backend 1.2.2, Wi-Fi
  desligado e LTE da Claro, "Atualizar lista" importou **234.000 itens** em
  cerca de 2 minutos. O catálogo final ficou com **2.264 canais**,
  **33.162 filmes** e **9.738 séries**, horário **19:57** e status `online`.
  As capas de série carregaram em 4G (007, 011ZE etc.). PSS ~208 MB. Wi-Fi
  restaurado e dados móveis desligados no fim.
  - O build de release só registra WARN+ no logcat (`EftvApplication`), então
    a importação bem-sucedida não aparece no log; a validação foi visual.

- [ ] **Playlist bloqueada para o Render (geobloqueio).** O backend 1.2.5
  confirmou: o Render sai por Portland (`cf-ray -PDX`) e o provedor devolve a
  página padrão do nginx (235 bytes), inclusive para `player_api.php`; a mesma
  URL no Brasil entrega `#EXTM3U` com ~84,6 MB. Não é DNS, tamanho nem
  credenciais. Opções: pedir liberação ao provedor, cache da playlist no
  Postgres com upload local, ou relay em IP brasileiro. Detalhes em
  `docs/ESTADO-ATUAL.md`.
  - O sucesso do reteste 4G das 19:57 pode ter vindo do proxy local do celular
    (IP brasileiro), não do Render; o log de release não registra a fonte.
  - Depois de resolver, restringir os detalhes de `/health.playlist_probe`
    (IPs/tentativas) a admin ou remover; hoje ficam públicos para diagnóstico.
  - [x] **Contorno implementado (1.2.7):** cache persistente em
    `playlist_cache`, upload admin em `PUT /admin/playlist/cache` e fallback em
    `/player/playlist-text`. Script: `backend/scripts/upload_playlist_cache.py`.
  - [x] **Backend 1.2.7 em produção** em 27/11; `/admin/playlist/cache` sem
    token responde 401 e o `/health` confirma a versão.
  - [ ] **Rodar o upload local** em uma rede que alcance o provedor e validar
    `/player/playlist-text` com o app/web. Comparar o fingerprint da URL do
    script com `/health.playlist_probe.configured.url_fingerprint`.

- [x] **Fallback do backend robusto (1.2.2).**
  `/player/playlist-text` agora tenta a linha própria e, se ela devolver
  HTML/erro, tenta a `IPTV_PLAYLIST_URL`. Só aceita resposta que comece com
  `#EXTM3U`/`#EXTINF`; a mensagem de erro não expõe URL nem credenciais.
  Assim, uma linha própria quebrada não bloqueia mais o 4G quando a playlist
  compartilhada está correta.

## Correção de 27/11/2026 — atualização pelo próprio app (1.5.25)

- [x] **Tela "Atualizar app"** acessível pelo menu ⋮ e por Configurações → Sobre.
  Mostra versão instalada, versão nova, novidades, progresso do download e
  permite reabrir o instalador se o cliente voltar sem concluir.
- [x] **Permissão de instalação contínua:** se o Android exigir "Instalar apps
  desconhecidos", ao voltar da tela de permissão o download continua sozinho.
- [x] **Download verificado:** só HTTPS, no máximo 5 redirecionamentos,
  conferência do `Content-Length`, do pacote `com.eftv.android` e do
  `versionCode` anunciado antes de abrir o instalador.
- [x] **Aviso automático diário** passou a abrir a tela nova e, quando o cliente
  toca em "Atualizar", já inicia o download.
- [x] **Consulta diária só é marcada após resposta** do servidor; uma falha de
  rede não esconde mais a atualização por 24 h.
- [x] **Release 1.5.25 (50)** assinada e publicada:
  https://github.com/EvertonFagundes/eftv/releases/tag/v1.5.25
  - SHA-256 `513e2a8b2a288ef8e343da0a36607d55de366ad365e3a6a00b6d943cf2f9188b`
    (40.022.407 bytes), conferido no asset baixado do GitHub.
  - Documentação do fluxo e checklist: `docs/ATUALIZACAO-APP.md`.
- [ ] **Atualizar o Render** para `APP_LATEST_VERSION_CODE=50`,
  `APP_LATEST_VERSION_NAME=1.5.25` e a URL da release (`render.yaml` já
  atualizado; falta o sync das env vars).
- [ ] **Testar o ciclo completo no aparelho:** menu → Atualizar app → download →
  autorizar instalação → instalar por cima, mantendo login e dispositivos.
- [ ] **Validar no aparelho que falhava** (herdado da 1.5.24): série, filme e
  canal ao vivo em Wi-Fi e 4G.

## Correção de 27/11/2026 — reprodução em aparelho secundário (1.5.24)

- [x] **Tela preta em séries/filmes e canal travado.** O proxy local entrega
  uma URL sem extensão; sem MIME explícito o ExoPlayer tratava HLS como vídeo
  progressivo. Agora o `MediaItem` leva o MIME da extensão original, o decoder
  de hardware tem fallback para software e, ao falhar, o app alterna entre
  proxy e acesso direto e tenta forçar HLS antes de reconectar.
- [x] **AVI/WMV/RMVB e protocolos sem suporte.** O app avisa o formato e oferece
  "Abrir com outro player" (com `<queries>` para achar VLC/mpv no Android 11+).
- [x] **Diagnóstico.** O relato de falha inclui rede, proxy, MIME, código do
  erro e codec/resolução selecionados, sem expor a URL completa.
- [x] **Release 1.5.24 (49)** assinada e publicada:
  https://github.com/EvertonFagundes/eftv/releases/tag/v1.5.24
- [ ] **Validar no aparelho que falhava:** série, filme e canal ao vivo em
  Wi-Fi e 4G; anotar modelo/Android e o texto de erro/diagnóstico se persistir.
- [x] ~~Refletir a versão no Render em 49/1.5.24~~ — substituído pela 1.5.25
  (item na seção acima).

## Correção de 27/11/2026 — capas de série pela API

- [x] **Imagens aleatórias na aba Séries.** O logo da playlist era priorizado
  sobre a capa da API e costuma apontar para arte de outro título. Agora as
  séries ignoram esse logo: cards da aba, itens em "Continuar assistindo" e a
  tela de detalhes buscam a capa pelo título limpo (IMDb → TVMaze). Canais e
  filmes continuam usando o logo original do provedor.
- [x] **Casamento com a API.** O TVMaze não pega mais o primeiro resultado da
  lista; escolhe o melhor casamento com o título. O cache de URLs migrou para
  `series_cover_urls_v2`, descartando capas antigas erradas.

Estado: 1.5.15 (`versionCode 40`) compilada, testada e instalada no aparelho.
Capas reais validadas na aba Séries (007, 011ZE, 100 Code, 100 Coisas..., 100
Days Wild), na busca por "Wandinha" (pôster de *Wednesday*) e na abertura da
série (temporadas, episódios e botões de reprodução).

## Concluído nesta rodada

- [x] **Capas de série não apareciam no aparelho.**
  O `findViewTreeLifecycleOwner()` devolvia `null` no momento do bind e a busca
  nunca iniciava. Agora o dono do ciclo de vida é localizado subindo pelo
  `ContextWrapper` até a Activity; a capa externa (IMDb/TVMaze) é carregada e o
  provedor continua tendo prioridade quando entrega logo própria.

- [x] **Cache persistente de capas.**
  As URLs encontradas ficam em `SharedPreferences` (`series_cover_urls`), além
  do cache em memória de 2.048 entradas. Reiniciar o app não refaz a busca no
  IMDb para as capas já visitadas.

- [x] **Skeleton com sobra de capa.**
  Cards em "Carregando..." limpam background e a chave da busca de capa; uma
  busca antiga não pinta mais o item reciclado.

- [x] **Aba Séries não carrega durante a importação.**
  `refreshCatalog` não reaplica mais o catálogo a cada 5.000 registros. Durante
  a importação apenas o contador/subtítulo é atualizado; a lista é recarregada
  uma única vez ao terminar.

- [x] **Consulta de séries pesada (CTE + window functions).**
  Tabela materializada `series_cards` (uma linha por série, com episódios,
  temporadas e a melhor capa). A aba Séries faz `COUNT(*)` e `LIMIT/OFFSET`
  nela. Com 9.730 séries a aba abriu direto, sem "Carregando..." prolongado.
  - Banco na versão 6; índice montado no fim da importação ou sob demanda.
  - Simulação com 240.000 linhas e 16.210 séries: índice em ~1,8 s no desktop.

- [x] **Memória alta.**
  PSS medido no aparelho caiu para ~189 MB (pico anterior: ~644 MB) depois do
  índice materializado e da carga em lotes.

- [x] **Desempenho da importação.**
  Lote de commit subiu de 500 para 2.000 registros (1/4 dos commits e do WAL).

- [x] **Horário do catálogo.**
  `updated_at` passa a ser gravado na conclusão da importação, não no início.

- [x] **Capas de série (ordem e resiliência).**
  `channel.logo` do provedor → IMDb suggestions → TVMaze → capa gerada.
  A busca externa usa proxy local nos dados móveis e não envia o Referer do
  provedor para o CDN. Falha de capa nunca derruba o app.

- [x] **Crash do `LruCache` ao não encontrar capa.**
  Sentinela de string vazia para "sem capa"; cache não recebe `null`.

- [x] **Release v1.5.15** com o APK assinado.
  Release: https://github.com/EvertonFagundes/eftv/releases/tag/v1.5.15
  SHA-256: `287adc6e580166e2148869d29911b00c03fe1fcfd2b7aa1424d5b6564a8a0bbe`
  APK publicado baixado, conferido e instalado por cima da 1.5.15 local.

## Pendente de validação

- [x] **Capas em dados móveis.**
  Wi-Fi desligado e dados móveis ativos: a busca "Round 6" carregou as capas
  reais de *Round 6* e *Round 6 O Desafio*. O Wi-Fi foi religado e os dados
  móveis desligados em seguida.
  - Observação: a capa de *Round 6 O Desafio* não é a do IMDb (*Squid Game:
    The Challenge*); como o provedor entrega logo própria, ela tem prioridade.
    Vale investigar se o logo do provedor está trocado.

- [x] **Importação completa (27/11, ~19:57).** 234.000 itens importados em
  ~2 min; catálogo final com 2.264 canais, 33.162 filmes e 9.738 séries. O
  horário do status foi atualizado para 19:57 e a lista apareceu
  progressivamente durante os lotes. PSS ~208 MB.

- [ ] **Primeira montagem do índice em instalação limpa (v5 → v6).**
  Medir em um aparelho sem o índice pronto; se passar de ~20 s, montar em
  segundo plano na abertura do app.

## Operação

- [ ] **Render / versão do APK:** env vars ainda respondem `1.5.23`
  (`versionCode 48`); atualizar para `1.5.25`/`50` e a URL da release
  `v1.5.25`.
- [x] **Backend 1.2.2 no ar:** `/health` responde `version=1.2.2`, e o
  `/player/playlist-text` sem token continua retornando 401.

- [x] **Reteste da importação em 4G:** concluído em 27/11 (~19:57), com LTE
  da Claro e o backend 1.2.2. A playlist compartilhada foi entregue e o
  catálogo importou 234.000 itens. Detalhes em "Validação em 4G" acima.
  - O build de release só loga WARN+, então não há linha `Playlist ... OK`
    no logcat; a confirmação foi pelo status e pelas contagens na tela.
