# EFTV

Player local de playlists IPTV para o navegador. Importe sua lista `.m3u` / `.m3u8` por link ou arquivo e assista aos seus canais ao vivo ou sob demanda — sem cadastro e sem depender de um serviço externo.

> **A EFTV não inclui canais nem links de terceiros.** Cada usuário adiciona a própria playlist pela interface. Use apenas conteúdo que você tem direito de assistir e redistribuir.

## Recursos

- Importação de playlist por **URL** ou **arquivo local**.
- Canais organizados em uma grade com busca, filtros e carregamento gradual.
- Player com suporte a **HLS**, **MPEG-TS**, **DASH** e arquivos **MP4**.
- Botão **Ao vivo / Voltar ao vivo** para saltar ao ponto mais recente da transmissão.
- Proxy local para streams, segmentos, chaves e logos, evitando bloqueios de CORS e conteúdo misto.
- Conversão automática de links Xtream `.ts` para a variante HLS `.m3u8`, com fallback para `.ts`.
- Layout responsivo em azul, para desktop e celular.
- Playlists salvas apenas neste computador, em `data/playlists.json`.

## Requisitos

- Python 3.10 ou superior.
- Navegador moderno com suporte a MSE (Chrome, Edge, Firefox, Brave ou Safari recente).
- Acesso à internet para carregar as bibliotecas do player (hls.js, mpegts.js e dash.js via CDN) e para acessar os streams importados.

## Como rodar

```bash
git clone https://github.com/EvertonFagundes/eftv.git
cd eftv
./start.sh
# ou: python3 server.py
```

Abra **http://127.0.0.1:8124/**.

Para usar outra porta:

```bash
PORT=9000 python3 server.py
```

O servidor escuta somente em `127.0.0.1` por padrão. Para expor na rede local de forma consciente:

```bash
HOST=0.0.0.0 PORT=8124 python3 server.py
```

> Abrir o `index.html` diretamente via `file://` mostra o layout, mas a importação e o proxy do player precisam do `server.py`.

## Como adicionar canais

1. Abra a página inicial.
2. No bloco **Adicionar playlist**, cole o link da sua lista `.m3u` / `.m3u8` e clique em **Adicionar link**.
3. Ou clique em **Escolher arquivo** e envie uma lista do seu computador.
4. Os canais aparecem na seção **Canais**. Use a busca ou os filtros **Ao vivo**, **Sob demanda** e **Importados**.

A lista de playlists mostra o link usado na importação e permite **copiar**, **atualizar** e **remover** cada playlist.

### Formato aceito

A EFTV lê listas M3U/M3U8 com entradas `#EXTINF`, incluindo atributos comuns como:

```m3u
#EXTM3U
#EXTINF:-1 tvg-id="canal" tvg-logo="https://exemplo.com/logo.png" group-title="Esportes",Meu Canal
https://exemplo.com/ao-vivo/canal.m3u8
```

Também é aceita uma lista simples com uma URL por linha.

## Estrutura

```text
index.html              página inicial, importação e grade de canais
canal.html?c=<slug>     página do canal, player e programação
embed/player.html       player interno (HLS, TS, DASH e MP4)
assets/css/style.css    tema azul e layout responsivo
assets/js/data.js       dados base e helpers de busca
assets/js/app.js        busca, filtros, grade e contadores
assets/js/playlists.js  formulário, upload e lista de playlists
assets/js/canal.js      cabeçalho do canal, troca de fonte e tela ampla
assets/img/             marca e favicon da EFTV
server.py               servidor local, API e proxy de streams
data/playlists.json     playlists importadas (criado localmente, fora do Git)
```

## API local

| Método | Rota | Função |
|---|---|---|
| `GET` | `/api/playlists` | lista as playlists salvas |
| `POST` | `/api/playlists` | adiciona por `{ "url": "..." }` |
| `POST` | `/api/playlists/upload?name=...` | adiciona a partir do corpo do arquivo |
| `POST` | `/api/playlists/refresh` | relê a URL de `{ "id": "..." }` |
| `DELETE` | `/api/playlists?id=...` | remove uma playlist |
| `POST` | `/api/playlists/clear` | remove todas as playlists |
| `GET` | `/api/catalogo.json` | catálogo completo em JSON |
| `GET` | `/api/catalogo.js` | catálogo em JavaScript para a interface |
| `GET` | `/api/proxy?url=...` | proxy de stream, segmento, chave ou imagem |

## Limites e configuração

As variáveis abaixo podem ser definidas antes de iniciar o servidor:

| Variável | Padrão | Descrição |
|---|---|---|
| `HOST` | `127.0.0.1` | endereço de escuta |
| `PORT` | `8124` | porta HTTP |
| `MAX_PLAYLIST_MB` | `128` | tamanho máximo de uma playlist |
| `MAX_CHANNELS` | `50000` | canais importados por playlist |

A grade mostra 240 canais por vez, com o botão **Mostrar mais canais**. A busca e os filtros continuam valendo para a lista inteira.

## Privacidade e segurança

- `data/playlists.json` guarda as URLs e os canais importados, incluindo possíveis usuários, senhas e tokens da sua playlist.
- O arquivo é criado com permissão `0600` e a pasta `/data/` não é servida publicamente.
- O link completo da playlist aparece na interface local para você não perder a referência. **Não compartilhe capturas de tela ou o arquivo `data/playlists.json`.**
- O repositório ignora `data/*.json`; nenhuma playlist de usuário é enviada ao Git.
- O servidor usa apenas a biblioteca padrão do Python e não envia telemetria.

## Formatos e limitações

| Tipo | Como é reproduzido |
|---|---|
| `hls` (`.m3u8`) | hls.js, com fallback nativo do navegador |
| `ts` (`.ts`) | mpegts.js via MSE |
| `dash` (`.mpd`) | dash.js |
| `mp4` | elemento `<video>` nativo |
| `iframe` | incorporação de uma página de player externa |

- Streams protegidos por **DRM** (Widevine/PlayReady/CENC) não são suportados.
- Canais `.mp4`, `.mkv`, `.avi` e similares são tratados como **Sob demanda**.
- A latência de transmissões ao vivo depende do provedor e do tamanho dos segmentos HLS; o botão **Ao vivo** reduz o atraso local.
- A programação exibida é básica: a EFTV usa o nome do grupo e informações genéricas da playlist, sem EPG externo.

## Aviso legal

A EFTV é uma interface de reprodução. Você é responsável pelas playlists que importa e pelo uso do conteúdo. Não use a ferramenta para acessar ou redistribuir conteúdo sem autorização dos detentores dos direitos.
