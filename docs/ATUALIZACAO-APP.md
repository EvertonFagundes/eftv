# Atualização do app pelo próprio app

O EFTV é distribuído por APK, fora da Play Store. Para o cliente não precisar
procurar e baixar um APK novo a cada correção, o app consulta a versão
publicada, baixa o arquivo e abre o instalador do Android — tudo dentro do
EFTV.

## Estado atual

| Item | Valor |
| --- | --- |
| Versão | `1.5.25` (`versionCode 50`) |
| Release | <https://github.com/EvertonFagundes/eftv/releases/tag/v1.5.25> |
| APK | <https://github.com/EvertonFagundes/eftv/releases/download/v1.5.25/eftv-v1.5.25.apk> |
| SHA-256 | `513e2a8b2a288ef8e343da0a36607d55de366ad365e3a6a00b6d943cf2f9188b` |
| Tamanho | 40.022.407 bytes |
| Assinatura | SHA-256 `b23096e6e33c21231d3006bcbee45f468b481dfc697606c2d75547f02be4ee8d` |

O APK publicado foi baixado de volta do GitHub, verificado com `apksigner` e
conferido contra o SHA-256 acima. O DEX contém `UpdateActivity` e
`UpdateInstaller`; `minSdk 24`, `targetSdk 34`.

## Como o cliente usa

- Menu ⋮ → **Atualizar app**.
- Configurações → Sobre → **Atualizar app**.
- Aviso automático: na abertura do app, no máximo uma vez por dia, quando o
  servidor anuncia uma versão mais nova. O aviso tem **Atualizar** e **Depois**;
  quando `APP_UPDATE_MANDATORY=true`, só tem **Atualizar**.

A tela de atualização mostra:

- versão instalada;
- versão nova e as novidades (`APP_UPDATE_NOTES`);
- progresso do download;
- botão **Autorizar instalação** quando o Android ainda não permite instalar
  apps desconhecidos;
- **Abrir instalador** se o cliente voltar sem concluir a instalação.

Ao voltar do painel "Instalar apps desconhecidos", se a permissão foi
concedida, o download continua sozinho.

## Como funciona por dentro

1. `GET /app/version` (sem login) devolve `version_code`, `version_name`,
   `apk_url`, `notes`, `mandatory` e `update_available_from`:

   ```json
   {
     "version_code": 50,
     "version_name": "1.5.25",
     "apk_url": "https://github.com/.../eftv-v1.5.25.apk",
     "notes": "novidades desta versao",
     "mandatory": false,
     "update_available_from": true
   }
   ```

   `update_available_from=false` (APK ainda não publicado) faz o app tratar
   como "sem atualização", sem mostrar erro ao cliente.
2. `UpdateActivity` compara `version_code` com `BuildConfig.VERSION_CODE`.
   Versão igual ou menor não gera aviso.
3. A URL só é aceita se for HTTPS em host público
   (`LogUtils.isSafeUpdateUrl`).
4. `UpdateInstaller.download()` segue no máximo cinco redirecionamentos,
   todos HTTPS, e confere o `Content-Length` para não instalar APK truncado.
5. `UpdateInstaller.isExpectedApk()` confere se o arquivo é do pacote
   `com.eftv.android` e se o `versionCode` é exatamente o anunciado.
6. O APK é entregue ao instalador por `FileProvider`; o Android valida a
   assinatura. Uma assinatura diferente só instala desinstalando a versão
   antiga.
7. O manifesto declara `REQUEST_INSTALL_PACKAGES`. No Android 8+ o sistema
   pede a autorização em "Instalar apps desconhecidos".

Arquivos principais:

| Arquivo | Papel |
| --- | --- |
| `UpdateActivity.kt` | Tela, estados, download e retomada após permissão |
| `UpdateInstaller.kt` | Download com validação, verificação do APK e instalação |
| `MainActivity.kt` | Aviso automático diário e item do menu |
| `SettingsActivity.kt` / `res/xml/preferences.xml` | Entrada em Configurações |
| `backend/app/routes/app_client.py` | `GET /app/version` e `/app/apk` |
| `backend/app/core/config.py` | Variáveis `APP_LATEST_*` / `APP_UPDATE_*` |

## Publicar uma nova versão

1. Subir `versionCode` e `versionName` em `android/app/build.gradle.kts`.
2. Gerar o APK de release:

   ```powershell
   cd android
   $env:JAVA_HOME = "C:\Program Files\Microsoft\jdk-17.0.13.11-hotspot"
   .\gradlew.bat :app:testDebugUnitTest :app:assembleRelease
   ```

3. Conferir versão e assinatura:

   ```powershell
   & "$env:LOCALAPPDATA\Android\Sdk\build-tools\36.0.0\apksigner.bat" verify --print-certs `
     app\build\outputs\apk\release\app-release.apk
   ```

4. Publicar a release `vX.Y.Z` com o asset `eftv-vX.Y.Z.apk` e o SHA-256.
5. Atualizar as variáveis no Render (ou sincronizar o `render.yaml`):

   ```text
   APP_LATEST_VERSION_CODE=<versionCode>
   APP_LATEST_VERSION_NAME=<versionName>
   APP_APK_URL=https://github.com/EvertonFagundes/eftv/releases/download/vX.Y.Z/eftv-vX.Y.Z.apk
   APP_UPDATE_NOTES=<novidades, opcional>
   APP_UPDATE_MANDATORY=false
   ```

6. Conferir `GET https://eftv.onrender.com/app/version` e testar no aparelho:
   menu → Atualizar app → baixar → autorizar (se pedir) → instalar.

## Cuidados

- Sempre aumentar o `versionCode`; o Android não instala downgrade.
- Nunca trocar a keystore: atualização por cima exige a mesma assinatura.
- O download usa o GitHub Releases. Se o GitHub estiver bloqueado ou lento na
  rede do cliente, basta apontar `APP_APK_URL` para outro endereço HTTPS.
- `APP_UPDATE_MANDATORY=true` deve ser usado só em correção crítica, porque o
  cliente não consegue adiar o aviso.
- Não colocar usuário/senha do provedor na URL do APK nem nas notas: a tela é
  visível para o cliente e as notas vêm do servidor.
