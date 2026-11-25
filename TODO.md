# Pendências — correções de 25/11/2026

Estado no momento do registro: 1.5.13 (versionCode 38) instalada no aparelho.
Importação do catálogo em andamento (240.000+ registros, ~9.700 séries
distintas) e aba **Séries** presa em "Carregando...".

## Prioridade alta

- [ ] **Aba Séries não carrega durante a importação.**
  `MainActivity.refreshCatalog` chama `applyCatalog(partial)` a cada 5.000
  registros importados. `applyCatalog` chama `resetCategorySelection()` e
  `filterChannels()`, o que reinicia a consulta pesada de séries várias vezes
  por minuto. A consulta nunca termina e a grade fica só com placeholders.
  - Correção: durante a importação, atualizar apenas o contador/subtítulo.
    Não resetar categoria, não refazer a lista. Aplicar o catálogo completo
    só no fim.
  - Opcional: limitar a atualização de progresso a cada 15–30 s.

- [ ] **Consulta de séries pesada (CTE + window functions em ~240 mil linhas).**
  `CatalogStore.seriesPage` agrupa o catálogo inteiro a cada página, com
  `ROW_NUMBER() OVER (PARTITION BY ...)` e `COUNT(DISTINCT season)`.
  Evidência: PSS de ~500–650 MB, native heap ~489 MB e páginas que não
  terminam durante a importação.
  - Correção: paginar primeiro os `series_key` distintos usando o índice
    `idx_channels_series(kind, series_key, season, episode)` e só depois
    buscar contagem/capa dos itens da página.
  - Alternativa: tabela materializada `series_cards` atualizada no fim da
    importação.

- [ ] **Contador enganoso durante a importação.**
  O subtítulo mostra `meta.total` (todas as linhas, incluindo episódios) com
  o substantivo da aba ("240.000 séries"). Trocar por "Importando N itens..."
  enquanto importa e exibir a contagem real de séries no fim.

- [ ] **Verificar capas de série no aparelho depois da importação.**
  A grade ainda não carregou nenhum card real, então o TVMaze não foi testado
  nesta versão. Confirmar capa, fallback e rolagem sem crash.

## Prioridade média

- [ ] **Memória alta.** PSS ~644 MB e native heap ~489 MB durante
  importação/consulta. Reavaliar após otimizar `seriesPage`; se continuar,
  limitar o cache de memória do Coil (`maxSizePercent`) e conferir cursores.

- [ ] **Skeletons com sobra de capa.** Os cards de "Carregando..." herdam o
  `background` gerado de itens anteriores. Limpar o background no estado de
  carregamento.

- [ ] **Desempenho da importação.** 240 mil registros em ~10 min (~400/s).
  Avaliar lote maior (500 -> 2.000) e reduzir gravações de metadado parcial.

- [ ] **Horário do catálogo.** `updated_at` é gravado no início da importação;
  no fim o app mostra o horário de início (20:42), não o de conclusão.

## Operação

- [ ] **Render:** atualizar `APP_LATEST_VERSION_CODE=38`,
  `APP_LATEST_VERSION_NAME=1.5.13` e `APP_APK_URL` para o APK da 1.5.13.
  O painel do Render tem prioridade sobre o `render.yaml`; `/app/version`
  ainda responde 1.5.7/32.
