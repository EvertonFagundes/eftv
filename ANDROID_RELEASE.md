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

> Guarde uma copia de `eftv-release.jks` e de `keystore.properties` fora do
> computador (pendrive ou cofre de senhas). Sem essa chave nao e possivel
> publicar atualizacoes do app: seria preciso um aplicativo novo, com outro
> pacote, e todos os clientes teriam que reinstalar e fazer login de novo.

## Gerar o APK

```bat
cd android
gradlew.bat assembleRelease
```

Saida: `android/app/build/outputs/apk/release/app-release.apk`.

## Publicar no GitHub

```bat
gh release create v1.1.0 android/app/build/outputs/apk/release/app-release.apk ^
  --title "EFTV 1.1.0" --notes "Novidades desta versao"
```

Sempre publique com a **mesma assinatura**. Se o aparelho tiver uma versao
antiga de debug, e necessario desinstalar uma unica vez
(`adb uninstall com.eftv.android`) antes de instalar o APK assinado.

## Variaveis do Render

- `MAX_DEVICES_PER_SUBSCRIPTION=2` (plano de 2 aparelhos).
- `FRONTEND_URL` deve apontar para o site que hospeda `checkout.html`
  (hoje `https://evertonfagundes.github.io/eftv`).
- `IPTV_PLAYLIST_URL` e o link da playlist licenciada; trocar nao exige APK.
