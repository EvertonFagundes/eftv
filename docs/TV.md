# EFTV na TV — situação e plano

## Decisão de produto

Não existe "uma versão para smart TV": são plataformas diferentes.

| Alvo | Base | Estratégia | Esforço |
|---|---|---|---|
| TV box Android (Mi Box, Chromecast, genéricos) | Android | **mesmo APK** | baixo |
| Fire TV (Stick/Cube) | Fire OS (Android) | mesmo APK | baixo |
| Android TV / Google TV (TCL, Philips, Sony, AOC) | Android | mesmo APK + Play Store | baixo |
| Samsung (Tizen) | web app | app web separado | alto |
| LG (webOS) | web app | app web separado | alto |
| Roku | BrightScript | app separado | alto |

Fase 1 = Android TV/Fire TV no APK atual. Fase 2 = Samsung/LG (web).

---

## O que já está pronto (Android TV)

No `AndroidManifest.xml`:

```xml
<uses-feature android:name="android.hardware.type.television" android:required="false" />
<uses-feature android:name="android.software.leanback" android:required="false" />
<uses-feature android:name="android.hardware.touchscreen" android:required="false" />
<application android:banner="@drawable/tv_banner" ...>
<intent-filter>
    <action android:name="android.intent.action.MAIN" />
    <category android:name="android.intent.category.LEANBACK_LAUNCHER" />
</intent-filter>
```

Ou seja: o APK instala e aparece no launcher da TV. O player já aceita o **OK**
do controle para mostrar os controles.

Backend do login por código já implementado e testado:
`POST /auth/device-code`, `POST /auth/device-code/poll`,
`POST /auth/device-code/approve`.

Para instalar no box, a partir da 1.4.7 o app no celular mostra o link curto
(`/tv`) e o servidor entrega o APK direto — veja **3.2**.

---

## Fase 1 — o que já está implementado (1.2.0)

### 1. Login sem teclado ✅
- `LoginActivity` detecta TV e mostra **"Entrar pelo celular"**
  (`tvCodeButton`): pede `/auth/device-code`, exibe o código em fonte grande e
  faz *poll* a cada 3 s até aprovar, expirar ou o cliente cancelar.
- No celular: menu ⋮ → **"Autorizar TV"** → digita o código →
  `POST /auth/device-code/approve`.
- O e-mail da conta volta junto com os tokens e a TV já abre logada.
- E-mail/senha continuam disponíveis como opção secundária.

### 2. Assinatura sem navegador ✅
- Na TV, `SubscriptionActivity` cria o checkout, desenha o `init_point` em
  **QR code** (`ui/QrCode.kt`, ZXing core, sem câmera) e consulta
  `/subscriptions/current` a cada 5 s por até 10 min.
- O cliente paga no celular; quando a assinatura fica `active`, o diálogo fecha
  e a tela mostra o novo estado.
- No celular continua abrindo o navegador como antes.

### 3. Transmitir a tela do celular ⏸️ (parado na 1.4.7)
- **Decisão de produto (17/11/2026)**: se a TV já tem o EFTV, espelhar do celular
  é pior em tudo (720p, atraso, bateria, DRM preto) — basta abrir o app na TV. E
  se a TV **não** tem o EFTV, o app-to-app não funciona, porque depende do
  receptor Android. O recurso só serve para mostrar conteúdo de **outros apps**
  (fotos, galeria, navegador) numa TV que já tem o EFTV.
- Por isso as entradas **Transmitir tela / Receber tela saíram do menu** na
  1.4.7. As telas e o protocolo continuam no APK, testados, sem entrada — para
  reativar basta devolver os itens em `res/menu/menu_main.xml` e os dois
  `when` em `MainActivity.setupToolbar()`.
- Limites conhecidos, se um dia voltar: mesma rede Wi-Fi (não passa pela
  internet); **som** exige Android 10+ e a permissão de gravação (negada,
  transmite só imagem); apps com DRM (Netflix, Globoplay) podem aparecer pretos
  ou mudos; um celular por vez; girar a tela no meio da transmissão distorce a
  imagem.

<details>
<summary>Como o cast app-to-app funcionava (implementação preservada)</summary>

- Na TV: `CastReceiveActivity` mostra um PIN de
  4 dígitos, o endereço `IP:porta` e anuncia o serviço `_eftvcast._tcp` na rede
  (mDNS/NSD).
- No celular: `CastSendActivity`. O cliente digita
  o PIN, escolhe a TV encontrada (ou informa o endereço) e autoriza a captura no
  diálogo do Android.
- Pipeline: `MediaProjection` → `MediaCodec` H.264 (720p, 4 Mbps, 30 fps) →
  TCP → `MediaCodec` decodificando direto na `Surface` da TV. O som vai no
  mesmo socket em AAC-LC (44,1 kHz estéreo, 128 kbps) e toca num `AudioTrack`.
- **Sincronia de som e imagem (1.4.1)**: as duas trilhas são carimbadas no mesmo
  relógio (`System.nanoTime()`) e a TV usa um `PresentationClock` — a primeira
  amostra define a âncora (com 150 ms de folga para o buffer) e cada quadro é
  agendado em `releaseOutputBuffer(index, instanteNs)`. Assim o som não
  escorrega ao longo do tempo, e quadro/som com mais de 400/250 ms de atraso é
  descartado em vez de acumular fila. O som só começa a ser capturado depois do
  primeiro quadro de vídeo: aí a base de tempo da imagem já é conhecida.
- **Não usa Miracast nem Chromecast**: funciona em qualquer Android 5.0+,
  inclusive nos aparelhos sem a opção "Transmitir tela" nas configurações.
- A captura roda em `CastService` (primeiro plano,
  `foregroundServiceType="mediaProjection"`), então continua com o EFTV em
  segundo plano: pode abrir YouTube, galeria, qualquer app.

</details>

### 3.2 Instalar o APK na TV (1.4.7)
- Menu ⋮ → **Instalar na TV** mostra o link curto e um botão **Copiar link**.
- O backend responde `302` direto no APK em `/tv` (alias curto, digitável no
  controle) e `/app/tv`. Não é página HTML de propósito: o Downloader do Fire TV
  e o navegador do box precisam receber o arquivo, não uma página.
- Sem `APP_APK_URL` configurada no servidor a rota devolve `503` e o app avisa
  "O APK ainda não foi publicado no servidor".
- Passo a passo do cliente: abrir o **Downloader** (Fire TV) ou o navegador do
  box → digitar `https://eftv.onrender.com/tv` → autorizar "apps de fontes
  desconhecidas" → instalar → entrar com o código de TV.



### 3.1 Diagnóstico do cast (17/11/2026)

- **Android 14+**: o diálogo do sistema abre em "Share one app". É preciso
  trocar para **Tela inteira**, senão a TV espelha só o EFTV. O texto da tela
  já avisa desde a 1.4.4.
- **`CastService` encerrava ~100 ms depois de subir** (corrigido na 1.4.5): a
  falha de conexão fazia o `CastSender` soltar a projeção; o callback da
  projeção interpretava isso como captura interrompida pelo sistema,
  sobrescrevia a mensagem real e chamava `stopSelf()`. Agora o `CastService`
  distingue a limpeza feita por ele mesmo (`CastSender.isStopping`), mantém a
  mensagem de rede/PIN na tela e só encerra depois dos 6 s de aviso.
  - O callback também ficou preso à sessão que o registrou: conectar de novo
    fecha a projeção antiga sem derrubar a transmissão nova.
  - Queda do socket durante a transmissão agora vira **"A conexão com a TV
    caiu"** em vez de deixar "Transmitindo" na tela para sempre.
- O socket do `CastServer` (porta 8765) e o anúncio mDNS da tela "Receber
  tela" **podem não ter sumido**: a checagem anterior lia só
  `/proc/net/tcp`, mas o `ServerSocket` do Java também pode abrir em IPv6
  (`/proc/net/tcp6`). Na 1.4.5 a TV loga abertura/fechamento do socket,
  tentativas de conexão, PIN errado e quedas com a tag `Receber tela:`, então
  o próximo teste no aparelho confirma (ou descarta) o problema.
- Fechar a tela da TV agora derruba também a conexão em andamento (antes a
  thread ficava presa no `read`), liberando a porta e o celular na hora.

### 4. Interface 10 pés
- [x] Configurações no menu (além do toque longo no título).
- [x] Cartões, linhas, abas e menus focáveis, com borda visível no foco
  (`bg_channel_item`, `selectableItemBackground`); na abertura da lista o foco
  já cai no primeiro canal (`focusListIfTelevision`).
- [x] Player no controle (1.4.7): **OK** mostra os controles e o foco cai no
  play/pause; **esquerda/direita** pulam 10 s sem abrir o menu (segurar a seta
  não dispara vários saltos); **play/pause** do controle funciona direto;
  **VOLTAR** fecha o menu antes de sair do canal.
- [ ] "Atualizar" no menu: validar no controle.
- [ ] Revisar foco/ordem em telas 1280×720 (sem elementos cortados).
- [ ] Banner 320×180 (`tv_banner`) conferido no launcher da TV. Hoje ele é um
  `layer-list` (gradiente + ícone de 96 dp), sem tamanho intrínseco: os
  launchers costumam esticar até a área do banner, mas só o teste no aparelho
  confirma. Para as lojas, o ideal é um PNG/WebP 320×180 com o nome do app.
- [x] Margem de segurança (overscan) ajustável em Configurações → TV e tela
  (1.4.6): Nenhuma / Pequena (24 dp) / Média (48 dp) / Grande (64 dp). O padrão
  em TV é 24 dp; no celular não muda nada.

### 5. Publicação — pendente
- Google Play (mesmo app, com `LEANBACK_LAUNCHER`).
- Amazon Appstore (Fire TV).
- Enquanto não houver loja: `adb install -r` no box ou o link `/tv` (1.4.7).
  O link só funciona depois de definir `APP_APK_URL` e `APP_LATEST_VERSION_*`
  no Render — até lá a rota responde `503`.

---

## Fase 2 — Samsung (Tizen) e LG (webOS)

Ambos são **aplicativos web** empacotados (HTML/JS/CSS), não Android.

O backend já entrega tudo que a TV precisa:
- login (`/auth/login`, `/auth/refresh`);
- catálogo autorizado (`/player/playlist`);
- sessão de tela (`/player/play`, `/player/heartbeat`, `/player/stop`);
- versão do app (`/app/version`).

O que muda é só a camada de apresentação:

1. Cliente web leve (HTML/CSS/JS) reaproveitando `frontend/public/assets/js/api.js`.
2. Player: `<video>` com HLS nativo (Samsung/LG recentes suportam) e fallback
   `hls.js` quando possível.
3. Login por código (o mesmo `/auth/device-code`) — teclado de TV é sofrimento.
4. Empacotamento:
   - Samsung: Tizen Studio → `.wgt`, envio pelo **Seller Office**;
   - LG: webOS CLI → `.ipk`, envio pelo **Seller Lounge**.
5. Restrições: modelos antigos têm navegador limitado (CORS, codecs); testar em
   pelo menos uma TV de cada marca.

Não recomendo começar a fase 2 antes de a fase 1 estar validada em TV box real:
o login por código e o QR de pagamento são os mesmos conceitos e serão
reaproveitados.

---

## Checklist de validação na TV (fase 1)

- [ ] APK instala e aparece na linha de apps da TV.
- [ ] Abre o app com o controle (sem mouse/toque).
- [ ] "Entrar pelo celular" gera código e a TV entra após aprovar.
- [ ] Navegação por D-pad: abas → categorias → lista → player → voltar.
- [ ] Reprodução ao vivo por 30 min sem travar.
- [ ] Segunda tela recebe o aviso de limite de telas.
- [ ] Assinatura por QR: pagar no celular e a TV liberar.
- [ ] "Atualizar" no menu recarrega o catálogo.
