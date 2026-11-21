<#
.SYNOPSIS
    Gera um backup criptografado do keystore de release do EFTV.

.DESCRIPTION
    Empacota android/eftv-release.jks e android/keystore.properties em um ZIP,
    criptografa com AES-256-CBC + HMAC-SHA256 (chave derivada por PBKDF2 com
    200.000 iteracoes) e grava android/eftv-release-backup.enc.

    A senha do backup e pedida no terminal e nao fica salva em lugar nenhum.
    Guarde o arquivo .enc no gerenciador de senhas ou em nuvem privada e a
    senha em local separado.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\backup-keystore.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\backup-keystore.ps1 -OutFile D:\backups\eftv-keystore.enc
#>
[CmdletBinding()]
param(
    [string]$AndroidDir = (Join-Path $PSScriptRoot '..\android'),
    [string]$OutFile
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

$androidDir = (Resolve-Path $AndroidDir).Path
if (-not $OutFile) { $OutFile = Join-Path $androidDir 'eftv-release-backup.enc' }

$required = @('eftv-release.jks', 'keystore.properties')
foreach ($name in $required) {
    if (-not (Test-Path (Join-Path $androidDir $name))) {
        throw "Arquivo nao encontrado: $name em $androidDir"
    }
}

if (Test-Path $OutFile) {
    $answer = Read-Host "O backup '$OutFile' ja existe. Sobrescrever? (s/N)"
    if ($answer -notmatch '^[sSyY]') { Write-Host 'Cancelado.'; return }
}

$secure1 = Read-Host 'Senha do backup' -AsSecureString
$secure2 = Read-Host 'Repita a senha do backup' -AsSecureString
$pass1 = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure1))
$pass2 = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure2))
if ($pass1 -ne $pass2) { throw 'As senhas nao conferem.' }
if ($pass1.Length -lt 12) { throw 'Use uma senha com pelo menos 12 caracteres.' }

# 1. ZIP com os dois arquivos, montado em memoria (via arquivo temporario).
$tmpZip = [IO.Path]::GetTempFileName()
# ZipFile.Open(..., 'Create') exige que o caminho ainda nao exista.
Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue
try {
    $zip = [IO.Compression.ZipFile]::Open($tmpZip, 'Create')
    try {
        foreach ($name in $required) {
            [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $zip,
                (Join-Path $androidDir $name),
                $name,
                [IO.Compression.CompressionLevel]::Optimal
            )
        }
    } finally {
        $zip.Dispose()
    }
    $plain = [IO.File]::ReadAllBytes($tmpZip)
} finally {
    Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue
}

# 2. Deriva chave de criptografia e de MAC a partir da senha.
$salt = New-Object byte[] 16
$iv = New-Object byte[] 16
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($salt)
$rng.GetBytes($iv)
$rng.Dispose()

$derive = [Security.Cryptography.Rfc2898DeriveBytes]::new(
    $pass1, $salt, 200000, [Security.Cryptography.HashAlgorithmName]::SHA256
)
$material = $derive.GetBytes(64)
[byte[]]$encKey = $material[0..31]
[byte[]]$macKey = $material[32..63]

# 3. AES-256-CBC.
$aes = [Security.Cryptography.Aes]::Create()
$aes.Mode = 'CBC'
$aes.Padding = 'PKCS7'
$aes.Key = $encKey
$aes.IV = $iv
$encryptor = $aes.CreateEncryptor()
$cipher = $encryptor.TransformFinalBlock($plain, 0, $plain.Length)
$encryptor.Dispose()
$aes.Dispose()

# 4. Cabecalho: magic + salt + iv. MAC cobre cabecalho + ciphertext.
$magic = [Text.Encoding]::ASCII.GetBytes('EFTVKS1')
$header = New-Object byte[] ($magic.Length + $salt.Length + $iv.Length)
[Array]::Copy($magic, 0, $header, 0, $magic.Length)
[Array]::Copy($salt, 0, $header, $magic.Length, $salt.Length)
[Array]::Copy($iv, 0, $header, $magic.Length + $salt.Length, $iv.Length)

$authenticated = New-Object byte[] ($header.Length + $cipher.Length)
[Array]::Copy($header, 0, $authenticated, 0, $header.Length)
[Array]::Copy($cipher, 0, $authenticated, $header.Length, $cipher.Length)

$hmac = [Security.Cryptography.HMACSHA256]::new($macKey)
$mac = $hmac.ComputeHash($authenticated)
$hmac.Dispose()

$output = New-Object byte[] ($authenticated.Length + $mac.Length)
[Array]::Copy($authenticated, 0, $output, 0, $authenticated.Length)
[Array]::Copy($mac, 0, $output, $authenticated.Length, $mac.Length)
[IO.File]::WriteAllBytes($OutFile, $output)

$hash = (Get-FileHash -Path $OutFile -Algorithm SHA256).Hash
$size = (Get-Item $OutFile).Length

Write-Host ''
Write-Host 'Backup criado com sucesso.' -ForegroundColor Green
Write-Host "  Arquivo : $OutFile"
Write-Host "  Tamanho : $size bytes"
Write-Host "  SHA-256 : $hash"
Write-Host ''
Write-Host 'Guarde este arquivo e a senha em locais diferentes (ex.: anexo no' -ForegroundColor Yellow
Write-Host 'gerenciador de senhas + senha como campo separado). Para restaurar:' -ForegroundColor Yellow
Write-Host '  powershell -ExecutionPolicy Bypass -File tools\restore-keystore.ps1' -ForegroundColor Yellow
