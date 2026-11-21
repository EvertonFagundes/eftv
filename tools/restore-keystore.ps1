<#
.SYNOPSIS
    Restaura o keystore de release do EFTV a partir do backup .enc.

.DESCRIPTION
    Le o arquivo gerado por tools/backup-keystore.ps1, confere o HMAC,
    descriptografa (AES-256-CBC) e extrai eftv-release.jks e
    keystore.properties em android/.

    Use isto apenas numa maquina confiavel. Os arquivos restaurados continuam
    ignorados pelo Git.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\restore-keystore.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\restore-keystore.ps1 -InFile D:\backups\eftv-keystore.enc
#>
[CmdletBinding()]
param(
    [string]$InFile,
    [string]$AndroidDir = (Join-Path $PSScriptRoot '..\android'),
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

$androidDir = (Resolve-Path $AndroidDir).Path
if (-not $InFile) { $InFile = Join-Path $androidDir 'eftv-release-backup.enc' }
if (-not (Test-Path $InFile)) { throw "Backup nao encontrado: $InFile" }

$existing = @('eftv-release.jks', 'keystore.properties') |
    Where-Object { Test-Path (Join-Path $androidDir $_) }
if ($existing -and -not $Force) {
    throw "Ja existem arquivos em ${androidDir}: $($existing -join ', '). Use -Force para sobrescrever."
}

$bytes = [IO.File]::ReadAllBytes($InFile)
$magic = [Text.Encoding]::ASCII.GetBytes('EFTVKS1')
if ($bytes.Length -lt ($magic.Length + 16 + 16 + 32)) { throw 'Arquivo de backup invalido (muito curto).' }
for ($i = 0; $i -lt $magic.Length; $i++) {
    if ($bytes[$i] -ne $magic[$i]) { throw 'Arquivo de backup invalido (assinatura desconhecida).' }
}

$saltOffset = $magic.Length
$ivOffset = $saltOffset + 16
$cipherOffset = $ivOffset + 16
$macOffset = $bytes.Length - 32

[byte[]]$salt = $bytes[$saltOffset..($ivOffset - 1)]
[byte[]]$iv = $bytes[$ivOffset..($cipherOffset - 1)]
[byte[]]$cipher = $bytes[$cipherOffset..($macOffset - 1)]
[byte[]]$mac = $bytes[$macOffset..($bytes.Length - 1)]
[byte[]]$authenticated = $bytes[0..($macOffset - 1)]

$secure = Read-Host 'Senha do backup' -AsSecureString
$pass = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))

$derive = [Security.Cryptography.Rfc2898DeriveBytes]::new(
    $pass, $salt, 200000, [Security.Cryptography.HashAlgorithmName]::SHA256
)
$material = $derive.GetBytes(64)
[byte[]]$encKey = $material[0..31]
[byte[]]$macKey = $material[32..63]

$hmac = [Security.Cryptography.HMACSHA256]::new($macKey)
$expected = $hmac.ComputeHash($authenticated)
$hmac.Dispose()

# Comparacao em tempo constante.
$diff = 0
for ($i = 0; $i -lt 32; $i++) { $diff = $diff -bor ($expected[$i] -bxor $mac[$i]) }
if ($diff -ne 0) { throw 'Senha incorreta ou backup corrompido (HMAC nao confere).' }

$aes = [Security.Cryptography.Aes]::Create()
$aes.Mode = 'CBC'
$aes.Padding = 'PKCS7'
$aes.Key = $encKey
$aes.IV = $iv
$decryptor = $aes.CreateDecryptor()
try {
    $plain = $decryptor.TransformFinalBlock($cipher, 0, $cipher.Length)
} finally {
    $decryptor.Dispose()
    $aes.Dispose()
}

$tmpZip = [IO.Path]::GetTempFileName() + '.zip'
try {
    [IO.File]::WriteAllBytes($tmpZip, $plain)
    $zip = [IO.Compression.ZipFile]::OpenRead($tmpZip)
    try {
        foreach ($entry in $zip.Entries) {
            if ($entry.Name -notin @('eftv-release.jks', 'keystore.properties')) {
                throw "Entrada inesperada no backup: $($entry.FullName)"
            }
            [void][IO.Compression.ZipFileExtensions]::ExtractToFile(
                $entry, (Join-Path $androidDir $entry.Name), $true
            )
            Write-Host "Restaurado: $($entry.Name)" -ForegroundColor Green
        }
    } finally {
        $zip.Dispose()
    }
} finally {
    Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host 'Keystore restaurado. Confira a assinatura com:' -ForegroundColor Green
Write-Host '  android\gradlew.bat assembleRelease' -ForegroundColor Yellow
