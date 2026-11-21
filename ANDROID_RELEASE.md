# Release do app Android

## Antes de gerar o APK

1. Confira a versao em `android/app/build.gradle.kts`:
   - `versionCode` precisa **aumentar** a cada publicacao (2, 3, 4...).
   - `versionName` e o texto que aparece no app (ex.: `1.1.0`).
2. O build de release aponta para `https://eftv.onrender.com` (ou para
   `-PEFTV_API_URL=https://seudominio.com`). URL local em `local.properties`
   e ignorada no release.

## Assinatura

O APK de release e assinado com a chave em `android/eftv-release.jks`.
As senhas ficam em `android/keystore.properties`. **Os dois arquivos estao no
`.gitignore` e nunca vao para o GitHub.**

### Chave atual (criada em 20/11/2026, versao 1.4.9)

| Item | Valor |
| --- | --- |
| Arquivo | `android/eftv-release.jks` (PKCS12, RSA 4096, validade 10.000 dias) |
| Alias | `eftv` |
| SHA-256 do certificado | `b23096e6e33c21231d3006bcbee45f468b481dfc697606c2d75547f02be4ee8d` |
| SHA-1 do certificado | `3a70f4ad62235e9d946526f6951c90468431d64a` |
| Primeiro APK com esta chave | `versionCode 24` / `1.4.9` |

A chave anterior (certificado `CN=EFTV`, SHA-256 `844f91af...069f1e`), usada
ate a 1.4.8, foi perdida e **nao pode ser extraida do APK** (o APK so tem o
certificado publico). Por isso a 1.4.9 inaugura uma assinatura nova: quem tem
a 1.4.8 ou anterior precisa desinstalar e instalar a 1.4.9 **uma unica vez**.
Conta, assinatura e dispositivos ficam no servidor; basta entrar de novo.

### Backup da chave

Tres copias, todas fora do Git:

1. **Local** - `android/eftv-release.jks` + `android/keystore.properties`.
2. **GitHub Actions Secrets** (usados pelo workflow `android-release.yml`):
   `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`,
   `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.
3. **Backup criptografado** - `tools/backup-keystore.ps1` gera um `.enc` com
   AES-256-CBC + HMAC-SHA256 (PBKDF2, 200 mil iteracoes). A senha e pedida no
   terminal e nao fica salva. Guarde o `.enc` no gerenciador de senhas ou em
   nuvem privada, e a senha em local separado.

```bat
powershell -ExecutionPolicy Bypass -File tools\backup-keystore.ps1
powershell -ExecutionPolicy Bypass -File tools\restore-keystore.ps1
```

> GitHub Secret e somente escrita: nao da para ler o valor de volta. O `.enc`
> e a copia local sao o que permitem reconstruir a chave se o PC ou a conta
> GitHub forem perdidos.

### Conferir a assinatura

```bat
"%ANDROID_HOME%\build-tools\34.0.0\apksigner.bat" verify --print-certs ^
  android\app\build\outputs\apk\release\app-release.apk
```

O SHA-256 precisa bater com o da tabela acima. Se mudar, ninguem consegue
atualizar por cima e todos precisam reinstalar.

## Gerar o APK

Requer JDK 17 (`JAVA_HOME`) e o Android SDK.

```bat
cd android
gradlew.bat assembleRelease
```

Saida: `android/app/build/outputs/apk/release/app-release.apk`.

## Publicar no GitHub

Com a assinatura configurada, basta criar a tag: o workflow
`.github/workflows/android-release.yml` compila, assina com os secrets e anexa
o APK na release.

```bat
git tag v1.4.9
git push origin v1.4.9
```

Alternativa manual:

```bat
gh release create v1.4.9 android/app/build/outputs/apk/release/app-release.apk ^
  --title "EFTV 1.4.9" --notes "Novidades desta versao"
```

> A 1.4.9 e a **primeira** com a chave nova. Quem estiver na 1.4.8 ou antes vai
> receber o aviso de atualizacao, mas a instalacao sera recusada pelo Android
> (assinatura diferente). Inclua nas notas da release a instrucao: desinstalar
> o app antigo e instalar este APK; a conta continua valendo.

## Variaveis do Render

- `MAX_DEVICES_PER_SUBSCRIPTION=2` (plano de 2 aparelhos).
- `FRONTEND_URL` deve apontar para o site que hospeda `checkout.html`
  (hoje `https://evertonfagundes.github.io/eftv`).
- `IPTV_PLAYLIST_URL` e o link da playlist licenciada; trocar nao exige APK.
