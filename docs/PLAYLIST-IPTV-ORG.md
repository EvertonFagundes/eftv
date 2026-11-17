# Playlist pública iptv-org (`br.m3u`) — análise

Análise feita em **17/11/2026** sobre
`https://iptv-org.github.io/iptv/countries/br.m3u`.

> Decisão registrada: **por enquanto é só diagnóstico**. Nada foi integrado ao
> catálogo, ao backend ou ao APK.

## O que é

A iptv-org é um **índice de streams públicos**: ela não hospeda conteúdo, apenas
lista URLs que estavam acessíveis. A lista por país é regerada diariamente.
"Publicamente acessível" **não** significa "licenciado para redistribuição" — é
a diferença que importa para um produto pago.

## Números do arquivo analisado

| Métrica | Valor |
|---|---|
| Canais | 397 (sem URLs duplicadas) |
| Grupos | 44 (`General` 85, `Undefined` 53, `Entertainment` 32, `Movies` 31, `News` 24…) |
| Tamanho | 85 KB |
| Atualização | diária (`Last-Modified` 17/11/2026 00:12 UTC, cache de 10 min) |
| Protocolo | 300 HTTPS / 97 HTTP puro |
| Origens | 170 hosts; 25 são IP puro, somando 77 canais |
| Logos | 5 sem `tvg-logo` |
| Formato | só HLS (`.m3u8`); nenhum `.mpd` ou `.ts` |
| Tags de país/idioma | ausentes no arquivo (o país é implícito pela URL) |

## Composição

- **FAST oficial — ~55 canais**: Pluto TV (filmes, kids, novelas, esportes…),
  MTV Pluto, Record News Pluto.
- **Público/governo/universidade — ~28**: TV Brasil, TV Cultura, Cultura Fast,
  Futura, TV Câmara, TV Senado, TV Justiça, Canal Gov, Canal Educação, Canal
  Libras, Rede Minas, TVE RS, TVE Bahia, TV UFG, TV UFOP, assembleias estaduais.
- **TV paga redistribuída — ~55 identificáveis**: Telecine, SporTV, ESPN, A&E,
  AMC, AXN, GNT, Gloob, Discovery, History, TNT, Sony, Universal, Nickelodeon,
  Comedy Central, Lifetime, TLC, Arte 1, Combate, Band Sports, Cartoon Network.
  Vários apontam para **IP fixo**, sem CDN oficial da emissora.
- **Restante (~260)**: locais, regionais, religiosos, web TVs e canais FAST de
  terceiros — qualidade e origem variam muito.

## Disponibilidade (amostra de 50 canais)

Teste com `User-Agent` de player, timeout de 8 s e leitura dos primeiros bytes:

- **36 de 50 responderam (72%)** — `200` ou `206`;
- 3 `ConnectTimeout`, 3 `ReadTimeout`;
- 2 `403`, 3 `404`, 1 `400`;
- 2 falhas foram do **proxy da rede usada no teste**, não do canal.

Ou seja: numa integração ingênua, **cerca de 1 em cada 4 canais não funciona** em
determinado momento. Os próprios nomes trazem `[Geo-blocked]` e `[Not 24/7]`.

## Riscos para o EFTV

1. **Jurídico**: incluir Telecine/SporTV/ESPN/GNT/Gloob etc. num plano pago é
   redistribuir TV paga sem contrato. Não usar.
2. **Instabilidade**: streams em IP fixo desaparecem sem aviso; a lista muda
   todo dia.
3. **HTTP puro**: 97 canais sem TLS; em rede hostil há espaço para injeção no
   stream.
4. **Geo-bloqueio**: parte só abre de IP brasileiro e pode falhar em VPN/datacenter.
5. **Qualidade**: sem EPG, sem numeração, resoluções de 268p a 1080p.

## Compatibilidade técnica com o app

O `M3uParser` já lê `group-title`, `tvg-logo`, `tvg-id` e URLs **sem extensão**
(assume HLS). O problema seria de produto, não de parser:

- grupos viriam em inglês (`General`, `News`), criando categorias fora do padrão
  em português;
- nomes viriam com sufixos `(720p)` e `[Geo-blocked]`;
- a categoria virtual **Abertos** já reconheceria Globo/SBT/Record/Band/Cultura/
  TV Brasil etc. pelo nome, mas os canais de TV paga continuariam no catálogo.

## Recomendação (se um dia integrar)

- **Nunca** substituir a playlist licenciada do Render; ela continua sendo o
  conteúdo do plano pago.
- Se houver camada gratuita, usar **lista branca**: Pluto TV + emissoras
  públicas/governo/universidades + locais com stream do site oficial.
- Excluir toda a TV paga e hosts de IP desconhecido.
- Baixar e **testar no backend** (HEAD/primeiros bytes), com cache, e entregar
  ao app só o que está no ar — o app não precisa saber a origem.
- Estimar **80 a 110 canais** aproveitáveis com esse filtro conservador.

## Conclusão

Serve como referência e possível camada gratuita curada; **não** serve como base
do EFTV pago. Sem integração por enquanto, por decisão de 17/11/2026.
