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
- **Acesso pela rede Wi-Fi**: com `--lan` o servidor também atende smart TVs, tablets e notebooks da mesma rede, mantendo o proxy de streams.
- **Roda no Android**: o mesmo `server.py` funciona no celular pelo Termux, com instalador próprio.
- **Categoria 18+ discreta**: os canais adultos ficam ocultos por padrão (fora da grade, da busca e dos filtros) e só aparecem ao tocar no botão **18+** no rodapé. Abrir o link direto de um canal adulto mostra uma barreira de confirmação.
- **Filtro “Só ao vivo”**: um botão ao lado do campo de filtro mostra apenas os canais que estão transmitindo no momento — filmes e séries sob demanda ficam de fora (eles não estão “sem sinal”: são arquivos prontos). A escolha fica salva, e cada chip de filtro já mostra a sua contagem.
- **Botão Voltar grande na página do canal**: feito para o controle remoto da smart TV, que nem sempre consegue voltar. Ele devolve para a tela anterior — com a categoria, o texto filtrado e a posição da rolagem que estavam antes de abrir o canal — e funciona mesmo sem JavaScript (cai na lista de canais).
- **Layout pensado para assistir**: a página começa nos canais (herói → Ao vivo → Categorias → Todos os canais), o formulário de importação `.m3u` fica recolhido num botão discreto no fim da página, e o cartão do servidor aparece como uma linha de status com as opções atrás de **Opções do servidor**.

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
python3 server.py --lan       # escuta também na rede Wi-Fi
python3 server.py "eftv://iniciar?porta=8124"   # chamada do navegador
```

O registro do protocolo acontece **apenas no seu usuário** (`HKCU` no Windows, `~/.local/share/applications` no macOS e Linux). Nada é instalado em nível de sistema e o Python usado é o mesmo do instalador.

## Acesso pela rede local (smart TV, tablet, notebook)

Com `--lan` (ou `HOST=0.0.0.0`) o servidor escuta também na interface de rede, e o terminal mostra os endereços:

```text
  EFTV no ar!
  Neste aparelho:  http://127.0.0.1:8124/
  Na rede Wi-Fi:   http://192.168.0.14:8124/
  Smart TV: digite no navegador o endereço "Na rede Wi-Fi"
  (as duas máquinas precisam estar na mesma rede Wi-Fi).
  Celular/notebook: use "http://127.0.0.1:8124/"
  — ele vale no Wi-Fi e também nos dados móveis.
```

A partir daí, qualquer aparelho da mesma rede abre `http://192.168.0.14:8124/` no navegador e usa a EFTV completa — o proxy de streams continua funcionando, porque quem busca o conteúdo é o servidor (o celular ou o notebook), não a TV.

### Ligar pelo celular

Na interface, o cartão **Servidor local** tem o interruptor **Acesso pela rede Wi-Fi**. Marque e clique em **Iniciar servidor local**: o servidor sobe escutando em `0.0.0.0` e o cartão passa a mostrar o endereço para digitar no celular. Pelo terminal, o equivalente é `python3 server.py --lan`.

Depois é só abrir no Chrome do Android (ou em qualquer navegador da rede) o endereço mostrado, por exemplo `http://192.168.0.14:8124/`. O celular precisa estar **na mesma rede Wi-Fi** do notebook.

Se o celular não conseguir conectar, em geral é o firewall do Windows bloqueando a entrada. Rode `instalar/liberar-firewall.bat` (ele pede permissão de administrador e libera a porta 8124 na rede privada):

```bash
netsh advfirewall firewall add rule name="EFTV (servidor local na rede)" dir=in action=allow protocol=TCP localport=8124 profile=private
```

### Deixar pronto para outra pessoa usar

O servidor **não precisa** ficar ligado o tempo todo: a página sobe o `server.py` na hora em que você toca em "Iniciar servidor", e ele só fica vivo enquanto aquele terminal estiver aberto. É a opção que menos pesa no notebook.

Se quiser que ele suba sozinho com o Windows — sabendo que o processo fica rodando o tempo todo, usando memória e processador — rode `instalar/iniciar-eftv-automatico.bat` uma única vez. Ele cria um atalho na inicialização do Windows que sobe o servidor em segundo plano, já com `--lan`. Para desfazer, rode `instalar/remover-inicio-automatico.bat`.

Aí o uso na smart TV fica:

1. você abre o endereço `http://IP-DO-NOTEBOOK:8124/` no navegador da TV **uma vez** e salva como favorito;
2. seu pai liga a TV, abre o favorito e assiste — sem tocar em mais nada.

O endereço aparece no cartão **Servidor local** da própria página, com um botão **Copiar**. Ele pode mudar se o notebook reconectar no Wi-Fi; para fixar, reserve um IP para o notebook no roteador.

Detalhes que importam nesse cenário:

- **Celular e TV precisam estar na mesma rede Wi-Fi**, e o roteador não pode ter "isolamento de clientes" (AP isolation) ligado.
- **A TV precisa de internet** para carregar `hls.js`, `mpegts.js` e `dash.js` do CDN. O conteúdo em si vem do servidor.
- **Fora de `localhost` não há contexto seguro**: a TV não instala o EFTV como app e o service worker não é registrado (a interface continua funcionando normalmente).
- O endereço do celular pode mudar quando o Wi-Fi reconecta. Parafixar, reserve um IP no roteador ou use um nome DNS local.
- Na interface, o cartão **Servidor local** mostra os endereços de rede e avisa quando a página está sendo aberta de outro aparelho. Com o servidor no ar ele aparece compacto, só com a linha de status — as opções (e os endereços) ficam atrás do botão **Opções do servidor**.
- Na página do canal há um botão **Voltar** grande, no alto: serve para o controle remoto da TV e devolve para a mesma tela em que a pessoa estava (categoria filtrada e rolagem preservadas).

### Só funciona no Wi-Fi? É o endereço errado

O endereço `http://192.168.x.x:8124/` pertence à **interface de rede local**. Quando o aparelho sai do Wi-Fi e passa para os dados móveis, esse IP deixa de existir — e aí a página não carrega (ou, se o service worker entregar a versão guardada, nenhum canal toca). Já o `http://127.0.0.1:8124/` é o próprio aparelho e vale em **qualquer** rede: o servidor escuta em `0.0.0.0`, que inclui o loopback.

| Aparelho | Endereço |
| --- | --- |
| O que roda o servidor (celular no Termux, notebook) | `http://127.0.0.1:8124/` — sempre |
| Smart TV, tablet ou outro notebook | `http://IP-DA-REDE:8124/` — só enquanto estiver na mesma rede |

A página acompanha isso sozinha: a cada 15 s ela pergunta ao servidor se o endereço da rede ainda responde. Se o servidor estiver de pé no próprio aparelho — o celular trocou de Wi-Fi para os dados, por exemplo — ela **se recoloca em `http://127.0.0.1:8124/` sozinha**. Se ninguém responder, ela mostra a explicação em vez de uma tela de erro do navegador.

Na smart TV nada disso se aplica: o endereço dela é o da rede e precisa do servidor ligado e na mesma Wi-Fi.

## No Android (Termux)

O mesmo `server.py` roda no Android pelo **Termux** (app gratuito, sem root). No Android não existe o protocolo `eftv://`, então a página mostra um cartão específico com o passo a passo e o comando pronto para copiar.

Instalação manual no Termux:

```bash
pkg install -y python git
git clone https://github.com/EvertonFagundes/eftv.git ~/eftv
bash ~/eftv/instalar/instalar-eftv-termux.sh
```

Se o `git clone` falhar — o que costuma acontecer quando o aparelho usa um **espelho do GitHub** configurado no `git` e ele está fora do ar — o instalador tenta sozinho: o clone normal, o clone ignorando a configuração global (ou seja, sem espelho) e por fim o `.zip`. Se ainda assim falhar, ele mostra o caminho manual. O mais curto é baixar o **pacote completo** pelo navegador do celular e descompactar no Termux:

```bash
pkg install -y unzip
unzip ~/eftv-android.zip -d ~
bash ~/eftv/instalar/instalar-eftv-termux.sh
```

O pacote é gerado por `instalar/gerar-pacote.py` e publicado em `https://evertonfagundes.github.io/eftv/eftv-android.zip`.

Se o próprio `pkg install` falhar com `rename failed` ou `Could not open file .../cache/apt/archives/partial/...`, o cache do `apt` está quebrado ou falta espaço no aparelho. O conserto:

```bash
df -h /data                                        # conferir o espaço livre
apt clean
mkdir -p /data/data/com.termux/cache/apt/archives/partial
termux-change-repo                                 # trocar o espelho
pkg update -y && pkg install -y python
```

O instalador já recria a pasta `partial` e avisa quando o espaço está baixo, mas se o disco estiver cheio é preciso liberar espaço antes.

O instalador do Termux:

- instala o Python e o Git se faltarem;
- baixa (ou atualiza) a cópia do código em `~/eftv`;
- cria os comandos `eftv`, `eftv-parar` e `eftv-atualizar` em `~/bin` (e adiciona `~/bin` ao `PATH`);
- sobe o servidor com `--lan --abrir`, ou seja, **escutando na rede Wi-Fi e abrindo o navegador do Android**.

Depois de instalado, no Termux:

```bash
eftv            # sobe o servidor (Ctrl+C para parar)
eftv-parar      # encerra
eftv-atualizar  # git pull do código
```

Para o servidor continuar rodando com a tela apagada, instale o addon **Termux:API** e rode `termux-wake-lock`, ou use o **Termux:Boot** para iniciar junto com o aparelho.

No Android, o `server.py` também:

- abre o navegador do próprio celular (`termux-open-url` ou `am start`), já que `webbrowser` do Python não acha navegador no Android;
- mostra o endereço IP do Wi-Fi no terminal, que é o que você digita na smart TV;
- descobre o Wi-Fi (`wlan0`) e ignora interfaces virtuais (VPN, tethering, bridges).

### O celular como servidor, para a smart TV

Se o servidor rodar no **celular** (e não no notebook), a smart TV acessa o endereço do celular. O caminho é o mesmo do Termux acima, com três cuidados a mais:

1. **Deixe o Termux rodando.** Ele precisa ficar aberto (pode estar com a tela apagada). Instale o addon **Termux:API** para o `termux-wake-lock` manter o aparelho acordado; o instalador já tenta ligar o wake lock sozinho.
2. **Deixe o celular carregando** numa tomada. Servir vídeo consome bateria.
3. **Fixe o IP do celular** nas configurações de Wi-Fi do Android (rede → **Configurações de IP → Estático**). Sem isso, cada vez que o celular reconecta no Wi-Fi ele ganha um IP novo e o favorito da TV deixa de funcionar. Se o seu roteador resolve nomes locais, dá para usar `http://nome-do-celular:8124/` em vez do número.

Depois é só abrir o endereço **Na rede Wi-Fi** no navegador da TV e salvar como favorito. Nada mais precisa ser feito no celular: ele fica na tomada, com o Termux rodando, e a TV acessa os canais que o celular busca e repassa.

### TV Box como servidor

Uma TV Box (Android TV) serve muito bem como servidor: fica na tomada, ligada o tempo todo e o IP dela quase nunca muda. O roteiro é o mesmo do Termux, com duas diferenças:

- **Android 7.0 ou superior** (Configurações → Sobre → Versão do Android). Boxes antigas com Android 5 ou 6 não rodam o Termux atual — nesses casos, use o celular ou o notebook.
- O comando `eftv` **abre o navegador** do aparelho. Na box isso toma a tela da TV; use `eftv-servidor`, que sobe o servidor sem abrir nada. É o que o Termux:Boot usa na inicialização.

Checklist rápido na box:

```bash
pkg install -y python git
git clone https://github.com/EvertonFagundes/eftv.git ~/eftv
bash ~/eftv/instalar/instalar-eftv-termux.sh
eftv-servidor
```

Depois, na smart TV: abra `http://IP-DA-BOX:8124/` e salve como favorito. Vale fixar o IP da box no roteador (ou em *Configurações de rede → Configurações de IP → Estático*) para o favorito nunca quebrar.

Atenção ao Wi-Fi: a box precisa buscar o stream e repassá-lo à TV, então o canal de 4K (15–25 Mbps) passa a depender do Wi-Fi da box. Boxes com Wi-Fi fraco ou só 2,4 GHz podem engasgar; nesse caso, o celular (que costuma ter antena melhor) ou um notebook são melhores.

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
instalar/instalar-eftv-termux.sh  instalador e lançador para Termux (Android)
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
| `GET` | `/api/catalogo.json` | catálogo completo em JSON (comprimido com gzip) |
| `GET` | `/api/canal?slug=...` | detalhes de um canal, com as fontes de transmissão |
| `GET` | `/api/status` | estado do servidor (versão, porta, endereços de rede, playlists, canais) |
| `GET` | `/api/modo.js` | informa o modo da interface (`local`) |
| `GET` | `/api/proxy?url=...` | proxy de stream, segmento, chave ou imagem |
| `POST` | `/api/servidor?acao=parar` | encerra o servidor (somente a página local) |

`/api/status` e `/api/modo.js` respondem com `Access-Control-Allow-Origin: *` para que a página do GitHub Pages consiga consultá-las. Nenhuma das duas expõe dados das playlists. O encerramento do servidor exige a mesma origem e o cabeçalho `X-EFTV-Local`, então nenhum site de fora consegue desligá-lo.

## Limites e configuração

As variáveis abaixo podem ser definidas antes de iniciar o servidor:

| Variável | Padrão | Descrição |
|---|---|---|
| `HOST` | `127.0.0.1` | endereço de escuta (use `0.0.0.0` ou `--lan` para a rede local) |
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
- Por padrão o servidor escuta **somente em `127.0.0.1`**. Com `--lan` ele passa a atender a rede local: qualquer aparelho da mesma rede acessa a interface e as playlists importadas. Use `--lan` só em redes confiáveis.
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
