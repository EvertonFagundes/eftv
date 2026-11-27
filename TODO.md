# PendÃªncias â€” correÃ§Ãµes de 25/11/2026

> **Retomada em outra mÃ¡quina:** leia `docs/ESTADO-ATUAL.md`. Ele tem versÃµes,
> comandos de teste em 4G, hipÃ³teses e o que falta para concluir.

## CorreÃ§Ã£o de 27/11/2026 â€” keepalive e importaÃ§Ã£o em dados mÃ³veis

- [x] **Backend dormindo.** O cron do GitHub agendava 5 min, mas entregava sÃ³
  ~3 execuÃ§Ãµes/dia (buracos de atÃ© 16h). O `self_ping` morria junto com o
  processo e nÃ£o acordava a instÃ¢ncia. Agora o keepalive Ã© uma corrente contÃ­nua
  de `workflow_dispatch` a cada ~9 min; o cron virou reserva. `self_ping` usa a
  URL pÃºblica e registra falhas.
- [x] **Aviso do tempo de importaÃ§Ã£o.** A tela informa que pode levar alguns
  minutos e que o que jÃ¡ chegou pode ser assistido.
- [x] **Lista progressiva.** Cada lote commitado (2.000 itens) atualiza a UI.
  O primeiro lote libera a lista; os seguintes sÃ³ atualizam contagem e pÃ¡ginas
  jÃ¡ carregadas, sem reiniciar a paginaÃ§Ã£o/aba SÃ©ries.
- [x] **SÃ©ries durante a importaÃ§Ã£o.** `series_cards` passa a ser alimentado
  lote a lote (com `INSERT OR IGNORE` + `UPDATE`, compatÃ­vel com SQLite antigo).
- [x] **ImportaÃ§Ã£o em dados mÃ³veis.** O proxy local agora Ã© esperado por atÃ© 30 s,
  tem segunda tentativa com DoH forÃ§ado (`&doh=1`) e sÃ³ depois cai para o
  download direto. `resolveSource` tenta de novo se o Render estiver acordando
  e o timeout de leitura subiu para 120 s. Redirecionamentos mantÃªm cookies e
  nÃ£o permitem `https -> http`.

- [x] **ImportaÃ§Ã£o repetida ao abrir o app.** O catÃ¡logo agora sÃ³ Ã© importado
  na primeira vez (ou quando o usuÃ¡rio toca em "Atualizar lista"). Se o app
  for fechado no meio de uma importaÃ§Ã£o, `recoverInterruptedImport()` valida os
  lotes jÃ¡ commitados como cache, em vez de apagar tudo e recomeÃ§ar.

Estado: 1.5.23 (`versionCode 48`), 230 testes do backend e 6 do servidor local
passando, compilaÃ§Ã£o Android OK.

### ValidaÃ§Ã£o em 4G (aparelho conectado)

- Wi-Fi desligado, dados mÃ³veis ligados: conectividade OK (`ping 8.8.8.8`).
- O app abriu e carregou o catÃ¡logo salvo sem importar de novo (meta confirmada).
- Ao forÃ§ar "Atualizar lista": proxy local deu timeout nas duas tentativas e o
  download direto falhou com `UnknownHostException` para `rtv30t.com` (DNS da
  operadora bloqueado) â€” era exatamente o cenÃ¡rio que o fallback do backend
  resolve.
- **Bloqueio encontrado:** o backend acessa a URL configurada, mas ela devolve
  uma pÃ¡gina padrÃ£o do nginx ("Welcome to nginx!", 235 bytes), nÃ£o uma playlist.
  O URL licenciado estÃ¡ no painel do Render (`IPTV_PLAYLIST_URL`, `sync: false`)
  e precisa ser corrigido pelo usuÃ¡rio. Com URL vÃ¡lida, o fallback por HTTPS do
  backend completa a importaÃ§Ã£o em dados mÃ³veis.
- `CatalogStore.replace()` agora sÃ³ limpa o catÃ¡logo quando chega o primeiro
  canal: uma playlist vazia nÃ£o apaga mais a lista salva no aparelho.
- **Reteste apÃ³s o usuÃ¡rio trocar `IPTV_PLAYLIST_URL` no Render:** ainda retornou
  235 bytes de pÃ¡gina padrÃ£o do nginx. O fallback autentica (HTTP 200), entÃ£o o
  problema Ã© a URL/conteÃºdo, nÃ£o o caminho em 4G. Suspeita principal: a
  assinatura da conta de teste tem `provider_playlist_url` (linha prÃ³pria)
  cadastrada, que tem precedÃªncia sobre a env var em `player.py`. Detalhes em
  `docs/ESTADO-ATUAL.md`.

- [x] **Reteste em 4G concluÃ­do (27/11, ~19:57).** Com o backend 1.2.2, Wi-Fi
  desligado e LTE da Claro, "Atualizar lista" importou **234.000 itens** em
  cerca de 2 minutos. O catÃ¡logo final ficou com **2.264 canais**,
  **33.162 filmes** e **9.738 sÃ©ries**, horÃ¡rio **19:57** e status `online`.
  As capas de sÃ©rie carregaram em 4G (007, 011ZE etc.). PSS ~208 MB. Wi-Fi
  restaurado e dados mÃ³veis desligados no fim.
  - O build de release sÃ³ registra WARN+ no logcat (`EftvApplication`), entÃ£o
    a importaÃ§Ã£o bem-sucedida nÃ£o aparece no log; a validaÃ§Ã£o foi visual.

- [ ] **Playlist bloqueada para o Render (geobloqueio).** O backend 1.2.5
  confirmou: o Render sai por Portland (`cf-ray -PDX`) e o provedor devolve a
  pÃ¡gina padrÃ£o do nginx (235 bytes), inclusive para `player_api.php`; a mesma
  URL no Brasil entrega `#EXTM3U` com ~84,6 MB. NÃ£o Ã© DNS, tamanho nem
  credenciais. OpÃ§Ãµes: pedir liberaÃ§Ã£o ao provedor, cache da playlist no
  Postgres com upload local, ou relay em IP brasileiro. Detalhes em
  `docs/ESTADO-ATUAL.md`.
  - O sucesso do reteste 4G das 19:57 pode ter vindo do proxy local do celular
    (IP brasileiro), nÃ£o do Render; o log de release nÃ£o registra a fonte.
  - Depois de resolver, restringir os detalhes de `/health.playlist_probe`
    (IPs/tentativas) a admin ou remover; hoje ficam pÃºblicos para diagnÃ³stico.
  - [x] **Contorno implementado (1.2.7):** cache persistente em
    `playlist_cache`, upload admin em `PUT /admin/playlist/cache` e fallback em
    `/player/playlist-text`. Script: `backend/scripts/upload_playlist_cache.py`.
  - [x] **Backend 1.2.7 em produÃ§Ã£o** em 27/11; `/admin/playlist/cache` sem
    token responde 401 e o `/health` confirma a versÃ£o.
  - [ ] **Rodar o upload local** em uma rede que alcance o provedor e validar
    `/player/playlist-text` com o app/web. Comparar o fingerprint da URL do
    script com `/health.playlist_probe.configured.url_fingerprint`.

- [x] **Fallback do backend robusto (1.2.2).**
  `/player/playlist-text` agora tenta a linha prÃ³pria e, se ela devolver
  HTML/erro, tenta a `IPTV_PLAYLIST_URL`. SÃ³ aceita resposta que comece com
  `#EXTM3U`/`#EXTINF`; a mensagem de erro nÃ£o expÃµe URL nem credenciais.
  Assim, uma linha prÃ³pria quebrada nÃ£o bloqueia mais o 4G quando a playlist
  compartilhada estÃ¡ correta.

## CorreÃ§Ã£o de 27/11/2026 â€” capas de sÃ©rie pela API

- [x] **Imagens aleatÃ³rias na aba SÃ©ries.** O logo da playlist era priorizado
  sobre a capa da API e costuma apontar para arte de outro tÃ­tulo. Agora as
  sÃ©ries ignoram esse logo: cards da aba, itens em "Continuar assistindo" e a
  tela de detalhes buscam a capa pelo tÃ­tulo limpo (IMDb â†’ TVMaze). Canais e
  filmes continuam usando o logo original do provedor.
- [x] **Casamento com a API.** O TVMaze nÃ£o pega mais o primeiro resultado da
  lista; escolhe o melhor casamento com o tÃ­tulo. O cache de URLs migrou para
  `series_cover_urls_v2`, descartando capas antigas erradas.

Estado: 1.5.15 (`versionCode 40`) compilada, testada e instalada no aparelho.
Capas reais validadas na aba SÃ©ries (007, 011ZE, 100 Code, 100 Coisas..., 100
Days Wild), na busca por "Wandinha" (pÃ´ster de *Wednesday*) e na abertura da
sÃ©rie (temporadas, episÃ³dios e botÃµes de reproduÃ§Ã£o).

## ConcluÃ­do nesta rodada

- [x] **Capas de sÃ©rie nÃ£o apareciam no aparelho.**
  O `findViewTreeLifecycleOwner()` devolvia `null` no momento do bind e a busca
  nunca iniciava. Agora o dono do ciclo de vida Ã© localizado subindo pelo
  `ContextWrapper` atÃ© a Activity; a capa externa (IMDb/TVMaze) Ã© carregada e o
  provedor continua tendo prioridade quando entrega logo prÃ³pria.

- [x] **Cache persistente de capas.**
  As URLs encontradas ficam em `SharedPreferences` (`series_cover_urls`), alÃ©m
  do cache em memÃ³ria de 2.048 entradas. Reiniciar o app nÃ£o refaz a busca no
  IMDb para as capas jÃ¡ visitadas.

- [x] **Skeleton com sobra de capa.**
  Cards em "Carregando..." limpam background e a chave da busca de capa; uma
  busca antiga nÃ£o pinta mais o item reciclado.

- [x] **Aba SÃ©ries nÃ£o carrega durante a importaÃ§Ã£o.**
  `refreshCatalog` nÃ£o reaplica mais o catÃ¡logo a cada 5.000 registros. Durante
  a importaÃ§Ã£o apenas o contador/subtÃ­tulo Ã© atualizado; a lista Ã© recarregada
  uma Ãºnica vez ao terminar.

- [x] **Consulta de sÃ©ries pesada (CTE + window functions).**
  Tabela materializada `series_cards` (uma linha por sÃ©rie, com episÃ³dios,
  temporadas e a melhor capa). A aba SÃ©ries faz `COUNT(*)` e `LIMIT/OFFSET`
  nela. Com 9.730 sÃ©ries a aba abriu direto, sem "Carregando..." prolongado.
  - Banco na versÃ£o 6; Ã­ndice montado no fim da importaÃ§Ã£o ou sob demanda.
  - SimulaÃ§Ã£o com 240.000 linhas e 16.210 sÃ©ries: Ã­ndice em ~1,8 s no desktop.

- [x] **MemÃ³ria alta.**
  PSS medido no aparelho caiu para ~189 MB (pico anterior: ~644 MB) depois do
  Ã­ndice materializado e da carga em lotes.

- [x] **Desempenho da importaÃ§Ã£o.**
  Lote de commit subiu de 500 para 2.000 registros (1/4 dos commits e do WAL).

- [x] **HorÃ¡rio do catÃ¡logo.**
  `updated_at` passa a ser gravado na conclusÃ£o da importaÃ§Ã£o, nÃ£o no inÃ­cio.

- [x] **Capas de sÃ©rie (ordem e resiliÃªncia).**
  `channel.logo` do provedor â†’ IMDb suggestions â†’ TVMaze â†’ capa gerada.
  A busca externa usa proxy local nos dados mÃ³veis e nÃ£o envia o Referer do
  provedor para o CDN. Falha de capa nunca derruba o app.

- [x] **Crash do `LruCache` ao nÃ£o encontrar capa.**
  Sentinela de string vazia para "sem capa"; cache nÃ£o recebe `null`.

- [x] **Release v1.5.15** com o APK assinado.
  Release: https://github.com/EvertonFagundes/eftv/releases/tag/v1.5.15
  SHA-256: `287adc6e580166e2148869d29911b00c03fe1fcfd2b7aa1424d5b6564a8a0bbe`
  APK publicado baixado, conferido e instalado por cima da 1.5.15 local.

## Pendente de validaÃ§Ã£o

- [x] **Capas em dados mÃ³veis.**
  Wi-Fi desligado e dados mÃ³veis ativos: a busca "Round 6" carregou as capas
  reais de *Round 6* e *Round 6 O Desafio*. O Wi-Fi foi religado e os dados
  mÃ³veis desligados em seguida.
  - ObservaÃ§Ã£o: a capa de *Round 6 O Desafio* nÃ£o Ã© a do IMDb (*Squid Game:
    The Challenge*); como o provedor entrega logo prÃ³pria, ela tem prioridade.
    Vale investigar se o logo do provedor estÃ¡ trocado.

- [x] **ImportaÃ§Ã£o completa (27/11, ~19:57).** 234.000 itens importados em
  ~2 min; catÃ¡logo final com 2.264 canais, 33.162 filmes e 9.738 sÃ©ries. O
  horÃ¡rio do status foi atualizado para 19:57 e a lista apareceu
  progressivamente durante os lotes. PSS ~208 MB.

- [ ] **Primeira montagem do Ã­ndice em instalaÃ§Ã£o limpa (v5 â†’ v6).**
  Medir em um aparelho sem o Ã­ndice pronto; se passar de ~20 s, montar em
  segundo plano na abertura do app.

## OperaÃ§Ã£o

- [x] **Render / versÃ£o do APK:** `/app/version` jÃ¡ responde
  `1.5.23` (`versionCode 48`) com a URL do APK correto.
- [x] **Backend 1.2.2 no ar:** `/health` responde `version=1.2.2`, e o
  `/player/playlist-text` sem token continua retornando 401.

- [x] **Reteste da importaÃ§Ã£o em 4G:** concluÃ­do em 27/11 (~19:57), com LTE
  da Claro e o backend 1.2.2. A playlist compartilhada foi entregue e o
  catÃ¡logo importou 234.000 itens. Detalhes em "ValidaÃ§Ã£o em 4G" acima.
  - O build de release sÃ³ loga WARN+, entÃ£o nÃ£o hÃ¡ linha `Playlist ... OK`
    no logcat; a confirmaÃ§Ã£o foi pelo status e pelas contagens na tela.
