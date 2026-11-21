# Bibliotecas do player (vendor)

Arquivos servidos junto com o site para o player não depender de CDNs de
terceiros. Carregados sob demanda por `embed/player.html`.

| Arquivo | Versão | Origem | Licença |
| --- | --- | --- | --- |
| `hls.min.js` | 1.5.17 | `https://cdn.jsdelivr.net/npm/hls.js@1.5.17/dist/hls.min.js` | Apache-2.0 (`hls.js.LICENSE.txt`) |
| `mpegts.js` | 1.7.3 | `https://cdn.jsdelivr.net/npm/mpegts.js@1.7.3/dist/mpegts.min.js` | Apache-2.0 (`mpegts.js.LICENSE.txt`) |
| `dash.all.min.js` | 5.3.0 | `https://cdn.jsdelivr.net/npm/dashjs@5.3.0/dist/modern/umd/dash.all.min.js` | BSD-3-Clause (`dash.all.min.js.LICENSE.txt`) |

## Atualizar

1. Baixe a versão nova de uma URL **fixa** (nunca `latest`).
2. Substitua o arquivo e a licença correspondente.
3. Atualize a tabela acima e teste HLS, MPEG-TS e DASH em `embed/player.html`.
4. Rode `node --check` nos arquivos JavaScript baixados.

Os nomes `hls.min.js`, `mpegts.js` e `dash.all.min.js` são os referenciados em
`player.html`; mantenha-os para não quebrar o carregamento sob demanda.
