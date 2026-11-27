# Pendências — correções de 25/11/2026

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

Estado: 1.5.18 (`versionCode 43`), 230 testes do backend e 6 do servidor local
passando, compilação Android OK.

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

- [ ] **Próxima importação completa.** Conferir o ganho real dos lotes de 2.000
  e se o horário final do catálogo aparece correto.

- [ ] **Primeira montagem do índice em instalação limpa (v5 → v6).**
  Medir em um aparelho sem o índice pronto; se passar de ~20 s, montar em
  segundo plano na abertura do app.

## Operação

- [ ] **Render:** o painel ainda responde 1.5.13/38. Atualizar
  `APP_LATEST_VERSION_CODE=40`, `APP_LATEST_VERSION_NAME=1.5.15` e
  `APP_APK_URL` para o APK da 1.5.15. O painel tem prioridade sobre o
  `render.yaml`.
  - [ ] Fazer o deploy do backend 1.2.1: o código passa a remover espaços da
    URL do APK; o painel estava devolvendo a URL com `\n` no final.
