# EFTV

Player de playlists IPTV para o navegador. Importe sua lista `.m3u` / `.m3u8` por link ou arquivo e assista aos seus canais ao vivo ou sob demanda — sem cadastro e sem depender de um serviço externo.

> **A EFTV não inclui canais nem links de terceiros.** Cada usuário adiciona a própria playlist pela interface. Use apenas conteúdo que você tem direito de assistir e redistribuir.

## Recursos

- Importação de playlist por **URL** ou **arquivo local**.
- Categorias em destaque: **Esportes**, **Notícias**, **Abertos**, **Filmes**, **Séries**, **Novelas**, **Documentários**, **Infantil**, **Animes**, **Variedades**, **Música**, **Religiosos**, **24 Horas**, **Streaming**, **Adultos** e **Outros**.
- Trilho **Ao vivo**, grade completa, busca, filtros e carregamento gradual.
- Player com suporte a **HLS**, **MPEG-TS**, **DASH** e arquivos **MP4**.
- Botão **Ao vivo / Voltar ao vivo** para saltar ao ponto mais recente da transmissão.
- Proxy local para streams, segmentos, chaves e logos, evitando bloqueios de CORS e conteúdo misto.
- Conversão automática de links Xtream `.ts` para a variante HLS `.m3u8`, com fallback para `.ts`.
- Layout responsivo em azul, para desktop e celular.
- **Instalação como app (PWA)** no Chrome, Edge, Android e iPhone/iPad.
- Playlists salvas apenas neste dispositivo — no servidor local (`data/playlists.json`) ou no IndexedDB do navegador (GitHub Pages).
- **Início do servidor local pela própria página**: um botão na interface sobe o `server.py` do computador do usuário (protocolo `eftv://`) e abre a versão completa em `http://127.0.0.1:8124/`.

## Requisitos

- Python 3.10 ou superior (para o modo local).
- Navegador moderno com suporte a MSE (Chrome, Edge, Firefox, Brave ou Safari recente).
- Acesso à internet para carregar as bibliotecas do player (hls.js, mpegts.js e dash.js via CDN) e para acessar os streams importados.

## Como rodar localmente

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

## Iniciar o servidor local pela página

A interface tem um cartão **Servidor local** que faz tudo isso:

1. Verifica se o `server.py` já está rodando em `http://127.0.0.1:8124/`.
2. Se estiver parado, o botão **Iniciar servidor local** aciona o protocolo `eftv://` e a aba com a versão completa abre sozinha.
3. Se o servidor já estiver no ar, o botão **Abrir EFTV local** aparece. Na própria página local, há ainda **Encerrar servidor**.

Para o protocolo `eftv://` funcionar, o usuário instala o **lançador** uma única vez:

| Sistema | Arquivo | O que ele faz |
|---|---|---|
| Windows | `instalar/instalar-eftv.bat` | instala o Python (se faltar), registra o protocolo `eftv://` no registro do Windows e sobe o servidor |
| macOS e Linux | `instalar/instalar-eftv.sh` | idem, criando um arquivo `.desktop` com `x-scheme-handler/eftv` |

O instalador também pode ser rodado direto, sem a página:

```bash
python3 instalar/instalar-eftv.py            # instala, registra e inicia
python3 instalar/instalar-eftv.py --instalar # só instala e registra
python3 instalar/instalar-eftv.py --iniciar  # só sobe o servidor
python3 instalar/instalar-eftv.py --parar    # encerra o servidor
python3 instalar/instalar-eftv.py --status   # mostra o estado
```

O `server.py` também aceita atalhos:

```bash
python3 server.py --abrir     # abre o navegador ao subir
python3 server.py --parar     # encerra o servidor que estiver rodando
python3 server.py --porta=9000
python3 server.py "eftv://iniciar?porta=8124"   # chamada do navegador
```

O registro do protocolo acontece **apenas no seu usuário** (`HKCU` no Windows, `~/.local/share/applications` no macOS e Linux). Nada é instalado em nível de sistema e o Python usado é o mesmo do instalador.

## Como adicionar canais

1. Abra a página inicial.
2. No bloco **Adicionar playlist**, cole o link da sua lista `.m3u` / `.m3u8` e clique em **Adicionar link**.
3. Ou clique em **Escolher arquivo** e envie uma lista do seu computador.
4. Os canais aparecem nas seções **Categorias**, **Ao vivo** e **Todos os canais**. Use a busca ou os filtros por categoria e por **Ao vivo** / **Sob demanda**.

A lista de playlists mostra o link usado na importação e permite **copiar**, **atualizar** e **remover** cada playlist.

### Formato aceito

A EFTV lê listas M3U/M3U8 com entradas `#EXTINF`, incluindo atributos comuns como:

```m3u
#EXTM3U
#EXTINF:-1 tvg-id="canal" tvg-logo="https://exemplo.com/logo.png" group-title="Esportes",Meu Canal
https://exemplo.com/ao-vivo/canal.m3u8
```

Também é aceita uma lista simples com uma URL por linha. O `group-title` é usado para distribuir o canal nas categorias da interface.

## Instalar como aplicativo

Com a página aberta em **HTTPS** (GitHub Pages) ou em **localhost**, o navegador pode instalar a EFTV como um app:

- **Chrome, Edge ou Android:** clique no botão **Instalar app** no cabeçalho e confirme. O ícone também pode aparecer na barra de endereço.
- **iPhone/iPad (Safari):** toque em **Compartilhar** e depois em **Adicionar à Tela de Início**.
- O app abre em tela cheia e usa o mesmo armazenamento local do navegador.
- O service worker mantém o app shell disponível offline; os streams continuam precisando de internet.

O botão **Instalar app** só aparece quando a instalação é possível (ou abre as instruções manuais quando o navegador não oferece o prompt).

## GitHub Pages (modo estático)

Página publicada: **https://evertonfagundes.github.io/eftv/**

O GitHub Pages não executa Python, então essa versão funciona de forma diferente do servidor local:

- **Importação por arquivo:** funciona normalmente; a playlist fica no IndexedDB do navegador.
- **Importação por link:** só funciona se o servidor da playlist permitir CORS. Não existe proxy no Pages.
- **Reprodução:** os streams são abertos diretamente pelo navegador. Provedores que bloqueiam CORS ou usam HTTP em uma página HTTPS podem não tocar.
- **Servidor local:** o cartão **Servidor local** detecta um `server.py` rodando em `http://127.0.0.1:8124/` e, com o lançador instalado, também consegue iniciá-lo a partir da própria página.
- **Dados:** cada navegador/dispositivo tem sua própria biblioteca; não há sincronização nem armazenamento no GitHub.
- **Proxy completo, importação por link sem CORS e mais recursos:** rode o `server.py` localmente.

### Se a importação falhar no Pages

- Use o botão **Copiar link** na lista de playlists. O endereço mostrado na tela é mascarado com `***` e não funciona se for copiado manualmente.
- O link precisa ser o da **lista M3U** do provedor (normalmente `get.php...type=m3u_plus` ou um arquivo `.m3u` / `.m3u8` com vários `#EXTINF`). Páginas de login, respostas JSON da API e manifests de um único canal não são playlists.
- Um `.m3u8` baixado de um canal contém apenas os segmentos daquele canal. Para importar vários canais, use a lista completa do provedor.
- A EFTV agora reconhece arquivos UTF-16, quebras de linha antigas e URLs entre aspas, e mostra uma mensagem específica para HTML, JSON, links RTMP/RTSP/UDP, arquivos compactados e manifests HLS.

Para publicar a sua própria cópia, envie os arquivos para um repositório e ative **Settings → Pages → Deploy from a branch → main / (root)**. O arquivo `.nojekyll` já está incluído.

## Estrutura

```text
index.html                    página inicial, categorias, ao vivo e grade
canal.html?c=<slug>           página do canal, player e programação
embed/player.html             player interno (HLS, TS, DASH e MP4)
assets/css/style.css          tema azul e layout responsivo
assets/js/data.js             categorias base, helpers e busca
assets/js/catalogo-base.js    mescla os canais importados com a base
assets/js/catalogo-loader.js  carrega o catálogo local em segundo plano
assets/js/static-store.js     IndexedDB e importação no modo GitHub Pages
assets/js/local-server.js     detecta, inicia e acompanha o servidor local
assets/js/app.js              busca, filtros, categorias, trilho e grade
assets/js/playlists.js        formulário, upload e lista de playlists
assets/js/canal.js            cabeçalho do canal, troca de fonte e tela ampla
assets/js/pwa.js              instalação como app
api/modo.js                   identifica o modo local ou estático
instalar/instalar-eftv.py     instalador e lançador (multiplataforma)
instalar/instalar-eftv.bat    instalador para Windows
instalar/instalar-eftv.sh     instalador para macOS e Linux
manifest.webmanifest          manifesto do PWA
sw.js                         service worker do app shell
assets/img/                   marca, favicon e ícones do app
server.py                     servidor local, API e proxy de streams
data/playlists.json           playlists importadas (criado localmente, fora do Git)
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
| `GET` | `/api/status` | estado do servidor (versão, porta, playlists, canais) |
| `GET` | `/api/modo.js` | informa o modo da interface (`local`) |
| `GET` | `/api/proxy?url=...` | proxy de stream, segmento, chave ou imagem |
| `POST` | `/api/servidor?acao=parar` | encerra o servidor (somente a página local) |

`/api/status` e `/api/modo.js` respondem com `Access-Control-Allow-Origin: *` para que a página do GitHub Pages consiga consultá-las. Nenhuma das duas expõe dados das playlists. O encerramento do servidor exige a mesma origem e o cabeçalho `X-EFTV-Local`, então nenhum site de fora consegue desligá-lo.

## Limites e configuração

As variáveis abaixo podem ser definidas antes de iniciar o servidor:

| Variável | Padrão | Descrição |
|---|---|---|
| `HOST` | `127.0.0.1` | endereço de escuta |
| `PORT` | `8124` | porta HTTP |
| `MAX_PLAYLIST_MB` | `128` | tamanho máximo de uma playlist |
| `MAX_CHANNELS` | `50000` | canais importados por playlist |

A grade mostra 240 canais por vez, com o botão **Mostrar mais canais**. A busca e os filtros continuam valendo para a lista inteira. O catálogo grande é carregado em segundo plano; a página exibe **Carregando seus canais...** enquanto isso.

## Privacidade e segurança

- `data/playlists.json` guarda as URLs e os canais importados, incluindo possíveis usuários, senhas e tokens da sua playlist.
- O arquivo é criado com permissão `0600` e a pasta `/data/` não é servida publicamente.
- O link da playlist aparece com usuário, senha e tokens mascarados na tela; o botão **Copiar link** copia o endereço completo. **Não compartilhe capturas de tela ou o arquivo `data/playlists.json`.**
- O repositório ignora `data/*.json`; nenhuma playlist de usuário é enviada ao Git.
- O service worker guarda apenas o app shell e o `api/modo.js` público. O catálogo local (`/api/catalogo.json`) **não** é armazenado no cache do PWA.
- No GitHub Pages, as playlists ficam no IndexedDB do seu navegador e não são enviadas ao GitHub.
- O servidor usa apenas a biblioteca padrão do Python e não envia telemetria.
- O instalador do lançador registra o protocolo `eftv://` **apenas no seu usuário**: chave `HKCU` no Windows e `~/.local/share/applications/eftv.desktop` no macOS e Linux. Nada é instalado em nível de sistema.
- A rota `/api/status` é pública, mas devolve apenas versão, porta e contadores. Nenhum dado das playlists sai do computador.

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
- No modo GitHub Pages não há proxy: provedores com CORS restrito podem exigir o servidor local.

## Aviso legal

A EFTV é uma interface de reprodução. Você é responsável pelas playlists que importa e pelo uso do conteúdo. Não use a ferramenta para acessar ou redistribuir conteúdo sem autorização dos detentores dos direitos.
