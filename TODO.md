# Pendências — correções de 25/11/2026

Estado: 1.5.14 (`versionCode 39`) compilada, testada em unidade e instalada no
aparelho. A sessão do app expirou (HTTP 401) e a tela de login apareceu; falta
entrar na conta para validar as capas de série no aparelho.

## Concluído nesta rodada

- [x] **Aba Séries não carrega durante a importação.**
  `refreshCatalog` não reaplica mais o catálogo a cada 5.000 registros. Durante
  a importação apenas o contador/subtítulo é atualizado; a lista é recarregada
  uma única vez ao terminar.

- [x] **Consulta de séries pesada (CTE + window functions).**
  Criada a tabela materializada `series_cards` (uma linha por série, com
  episódios, temporadas e a melhor capa). A aba Séries agora faz `COUNT(*)` e
  `LIMIT/OFFSET` nela, sem varrer os ~240 mil episódios a cada página.
  - Banco migrado para a versão 6; o índice é montado no fim da importação ou
    sob demanda na primeira abertura da aba.
  - Simulação com 240.000 linhas e 16.210 séries: índice montado em ~1,8 s.

- [x] **Contador enganoso durante a importação.**
  O subtítulo mostra "Importando N itens" enquanto importa e a contagem real
  da aba ao terminar.

- [x] **Capas de série.**
  Ordem nova: `channel.logo` do provedor (quando existe) → IMDb suggestions →
  TVMaze → capa gerada com as iniciais. O IMDb cobre os títulos reais do
  provedor, inclusive com prefixo ("007 Estrada para o Milhao [L]" →
  "007: Road to a Million"); o TVMaze ficou como reserva.
  - A busca externa usa proxy local nos dados móveis e não envia o Referer do
    provedor para o CDN.
  - Falha de capa nunca derruba o app.

- [x] **Crash do `LruCache` ao não encontrar capa.**
  Sentinela de string vazia para "sem capa"; cache não recebe `null`.

## Pendente de validação

- [ ] **Entrar na conta no aparelho e conferir as capas de série.**
  A release 1.5.14 está instalada; a sessão anterior expirou. Depois do login:
  abrir a aba **Séries**, confirmar capas reais (não só as geradas), rolar
  várias páginas e abrir uma série.

- [ ] **Tempo de montagem do índice no aparelho.**
  Medir a primeira abertura da aba após a migração v5 → v6. Se passar de
  ~20 s, avaliar montar o índice em segundo plano já na abertura do app.

## Prioridade média

- [ ] **Memória alta.** PSS chegou a ~644 MB e native heap ~489 MB durante a
  importação/consulta antiga. Reavaliar depois do índice materializado; se
  continuar, limitar o cache de memória do Coil (`maxSizePercent`) e revisar
  cursores.

- [ ] **Skeletons com sobra de capa.** Os cards de "Carregando..." herdam o
  `background` gerado de itens anteriores. Limpar o background no estado de
  carregamento.

- [ ] **Desempenho da importação.** 240 mil registros em ~10 min (~400/s).
  Avaliar lote maior (500 → 2.000) e reduzir gravações de metadado parcial.

- [ ] **Horário do catálogo.** `updated_at` é gravado no início da importação;
  no fim o app mostra o horário de início, não o de conclusão.

- [ ] **Cache persistente de capas.** O cache do IMDb/TVMaze é só em memória;
  ao reiniciar o app as capas são buscadas de novo. Persistir as URLs
  encontradas evitaria tráfego repetido.

## Operação

- [ ] **Render:** atualizar no painel `APP_LATEST_VERSION_CODE=39`,
  `APP_LATEST_VERSION_NAME=1.5.14` e `APP_APK_URL` para o APK da 1.5.14.
  O painel do Render tem prioridade sobre o `render.yaml`; `/app/version`
  ainda responde 1.5.7/32.

- [ ] **Publicar a release v1.5.14** com o APK assinado e atualizar o
  `ANDROID_RELEASE.md` com o SHA-256 gerado pelo workflow.
