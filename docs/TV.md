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

### 3. Transmitir a tela do celular ✅ (1.3.0)
- Na TV: menu ⋮ → **Receber tela** (`CastReceiveActivity`). Ela mostra um PIN de
  4 dígitos, o endereço `IP:porta` e anuncia o serviço `_eftvcast._tcp` na rede
  (mDNS/NSD).
- No celular: menu ⋮ → **Transmitir tela** (`CastSendActivity`). O cliente digita
  o PIN, escolhe a TV encontrada (ou informa o endereço) e autoriza a captura no
  diálogo do Android.
- Pipeline: `MediaProjection` → `MediaCodec` H.264 (720p, 4 Mbps, 30 fps) →
  TCP → `MediaCodec` decodificando direto na `Surface` da TV.
- **Não usa Miracast nem Chromecast**: funciona em qualquer Android 5.0+,
  inclusive nos aparelhos sem a opção "Transmitir tela" nas configurações.
- A captura roda em `CastService` (primeiro plano,
  `foregroundServiceType="mediaProjection"`), então continua com o EFTV em
  segundo plano: pode abrir YouTube, galeria, qualquer app.
- Limites: mesma rede Wi-Fi (não passa pela internet); **sem áudio** nesta
  versão; apps com DRM (Netflix, Globoplay) podem aparecer pretos; um celular
  por vez; girar a tela no meio da transmissão distorce a imagem.

### 4. Interface 10 pés — pendente
- [ ] "Atualizar" no menu já existe; validar no controle.
- [ ] Configurações hoje entram por **toque longo** no título: expor no menu.
- [ ] Revisar foco/ordem em telas 1280×720 (sem elementos cortados).
- [ ] Banner 320×180 (`tv_banner`) conferido no launcher da TV.

### 5. Publicação — pendente
- Google Play (mesmo app, com `LEANBACK_LAUNCHER`).
- Amazon Appstore (Fire TV).
- Enquanto não houver loja: `adb install -r` no box.

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
