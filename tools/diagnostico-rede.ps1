# diagnostico-rede.ps1 - Coleta o que o app registra quando falha nos dados moveis.
#
# Uso:
#   1. Conecte o celular no USB e autorize a depuracao.
#   2. Rode:  powershell -ExecutionPolicy Bypass -File tools\diagnostico-rede.ps1
#   3. Desligue o Wi-Fi, abra o EFTV nos dados moveis e tente abrir um canal.
#   4. Volte ao terminal e pressione Enter.
#
# O arquivo gerado nao tem senha/usuario do provedor: as URLs e credenciais
# sao mascaradas antes de gravar.

$ErrorActionPreference = "Stop"

function Achar-Adb {
    $candidatos = @(
        "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe",
        "$env:ANDROID_HOME\platform-tools\adb.exe",
        "$env:ANDROID_SDK_ROOT\platform-tools\adb.exe"
    )
    foreach ($c in $candidatos) {
        if ($c -and (Test-Path $c)) { return $c }
    }
    $noPath = Get-Command adb -ErrorAction SilentlyContinue
    if ($noPath) { return $noPath.Source }
    throw "adb nao encontrado. Instale o Android Platform Tools ou informe o caminho."
}

$adb = Achar-Adb
$device = (& $adb devices) | Select-Object -Skip 1 | Where-Object { $_ -match "\sdevice$" } | Select-Object -First 1
if (-not $device) {
    throw "Nenhum celular autorizado. Conecte no USB e aceite 'Permitir depuracao USB'."
}

$modelo = (& $adb shell getprop ro.product.model).Trim()
$android = (& $adb shell getprop ro.build.version.release).Trim()
$versao = ((& $adb shell dumpsys package com.eftv.android) | Select-String -Pattern "versionName=" | Select-Object -First 1).Line.Trim()
$wifi = (& $adb shell settings get global wifi_on).Trim()
$data = Get-Date -Format "yyyyMMdd-HHmmss"
$saida = Join-Path (Get-Location) "diagnostico-rede-$data.txt"

Write-Host ""
Write-Host "Aparelho: $modelo (Android $android)"
Write-Host "App: $versao | Wi-Fi ligado: $wifi"
Write-Host ""
Write-Host "Agora DESLIGUE O WI-FI, abra o EFTV nos dados moveis e tente abrir um canal." -ForegroundColor Yellow
Read-Host "Quando o erro aparecer, pressione Enter"

$conectividade = (& $adb shell dumpsys connectivity) |
    Select-String -Pattern "Active default network|NetworkAgentInfo|Transports:|VALIDATED|NOT_VALIDATED|CELLULAR|WIFI" |
    Select-Object -First 40

$bruto = (& $adb logcat -d -v time) |
    Select-String -Pattern "com\.eftv\.android|EFTV|Timber|LocalServer|Playlist|ExoPlayer|AndroidRuntime|não foi possível|nao foi possivel|UnknownHost|SSLHandshake|gaierror|DoH"

$texto = ($bruto | ForEach-Object { $_.Line }) -join "`n"
# Nunca gravar a credencial do provedor nem a URL inteira do proxy.
$texto = $texto -replace '(?i)(password|senha|username|user|token)=([^&\s]+)', '$1=***'
$texto = $texto -replace '(?i)https?://127\.0\.0\.1:8124/api/(proxy|playlist-remote)\?url=\S+', '<proxy-local>'
$texto = $texto -replace '(?i)tvg-logo="[^"]*"', 'tvg-logo="***"'
$texto = $texto -replace '(?i)(https?://[^\s"<>]+)', '<url>'

$conteudo = @(
    "EFTV - diagnostico de rede",
    "Gerado em: $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')",
    "Aparelho: $modelo",
    "Android: $android",
    "App: $versao",
    "Wi-Fi ligado no momento da coleta: $wifi",
    "",
    "=== Conectividade ===",
    ($conectividade | ForEach-Object { $_.Line }) -join "`n",
    "",
    "=== Log do app ===",
    $texto
) -join "`n"

Set-Content -Path $saida -Value $conteudo -Encoding UTF8
Write-Host ""
Write-Host "Diagnostico salvo em: $saida" -ForegroundColor Green
Write-Host "Envie esse arquivo no chat."
