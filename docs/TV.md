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

## Fase 1 — pendências no app (Android TV / Fire TV)

### 1. Login sem teclado
- `LoginActivity` detecta TV (`PackageManager.FEATURE_LEANBACK`/`FEATURE_TELEVISION`)
  e mostra em destaque **"Entrar pelo celular"**: pede `/auth/device-code`,
  exibe o código em fonte grande (`ABCD-EFGH`) e faz `poll` a cada 3 s.
- No celular (conta já logada): opção **"Autorizar TV"** em ⋮ → digita o código →
  `POST /auth/device-code/approve`.
- Alternativa sem app no celular: aceitar o código na área do assinante na web.
- Manter e-mail/senha como opção secundária (teclado virtual existe, mas é ruim).

### 2. Assinatura sem navegador
- TV cria o checkout (`POST /subscriptions/checkout`), desenha o `init_point` em
  **QR code** na tela e faz *polling* em `/subscriptions/current`.
- Cliente escaneia com a câmera do celular e paga no navegador do próprio celular.
- Ao detectar `has_access: true`, a TV libera sozinha.
- Requer: gerar QR (biblioteca `com.google.zxing:core`, sem câmera) e um diálogo
  de acompanhamento.

### 3. Interface 10 pés
- Foco visível em todos os itens (cartões com borda + escala).
- Categorias já usam cartões focáveis (`CategoriesActivity`).
- `SwipeRefresh` (gesto) não existe na TV: expor "Atualizar" no menu.
- Configurações: hoje entram por **toque longo** no título; na TV precisa de item
  no menu (⋮).
- Fundo do app: manter 16:9, sem elementos cortados em telas 1280×720.

### 4. Publicação
- **Google Play**: mesmo app do celular com `LEANBACK_LAUNCHER` e banner 320×180
  (já existe `tv_banner`); exige Play Console e revisão de TV.
- **Amazon Appstore** (Fire TV): APK próprio, mesmo código.
- Enquanto não houver loja: instalar por `adb install -r` no box.

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
