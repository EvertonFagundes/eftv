# ============================================================
#  EFTV — Gera os ícones PNG do PWA (Windows / PowerShell)
#  Uso:  powershell -ExecutionPolicy Bypass -File web/tools/gerar-icones.ps1
#  Saída: web/app/assets/img/icon-*.png
# ============================================================

Add-Type -AssemblyName System.Drawing

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$destino = Join-Path $raiz "app\assets\img"
New-Item -ItemType Directory -Force -Path $destino | Out-Null

# Grava bytes com retentativas: antivírus/indexador pode travar o PNG recém-criado.
function Save-BytesSeguro {
    param([string]$Caminho, [byte[]]$Bytes)
    $tmp = "$Caminho.tmp"
    [System.IO.File]::WriteAllBytes($tmp, $Bytes)
    for ($i = 0; $i -lt 40; $i++) {
        try {
            if (Test-Path $Caminho) { [System.IO.File]::Delete($Caminho) }
            [System.IO.File]::Move($tmp, $Caminho)
            return
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    throw "Não foi possível gravar $Caminho (arquivo em uso)."
}

function New-EftvIcon {
    param(
        [int]$Size,
        [string]$Arquivo,
        [switch]$Maskable,
        [switch]$Redondo
    )

    $bmp = New-Object System.Drawing.Bitmap($Size, $Size)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality

    # Fundo (gradiente diagonal azul -> azul-escuro)
    $rect = New-Object System.Drawing.Rectangle(0, 0, $Size, $Size)
    $c1 = [System.Drawing.Color]::FromArgb(255, 47, 155, 255)
    $c2 = [System.Drawing.Color]::FromArgb(255, 7, 20, 38)
    $brush = New-Object System.Drawing.Drawing2D.LinearGradientBrush($rect, $c1, $c2, 45.0)
    if ($Redondo -and -not $Maskable) {
        $raio = [int]($Size * 0.23)
        $path = New-Object System.Drawing.Drawing2D.GraphicsPath
        $d = $raio * 2
        $path.AddArc(0, 0, $d, $d, 180, 90)
        $path.AddArc($Size - $d, 0, $d, $d, 270, 90)
        $path.AddArc($Size - $d, $Size - $d, $d, $d, 0, 90)
        $path.AddArc(0, $Size - $d, $d, $d, 90, 90)
        $path.CloseFigure()
        $g.FillPath($brush, $path)
        $path.Dispose()
    } else {
        $g.FillRectangle($brush, $rect)
    }
    $brush.Dispose()

    # Brilho suave no topo
    $glowRect = New-Object System.Drawing.Rectangle(0, 0, $Size, [int]($Size * 0.62))
    $glow = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
        $glowRect,
        [System.Drawing.Color]::FromArgb(90, 255, 255, 255),
        [System.Drawing.Color]::FromArgb(0, 255, 255, 255),
        90.0
    )
    $g.FillRectangle($glow, $glowRect)
    $glow.Dispose()

    # Área segura: maskable usa 70% central
    $fator = if ($Maskable) { 0.58 } else { 0.70 }
    $lado = [int]($Size * $fator)
    $cx = [int](($Size - $lado) / 2)
    $cy = [int](($Size - $lado) / 2)

    # Círculo translúcido atrás do play
    $circulo = New-Object System.Drawing.Rectangle($cx, $cy, $lado, $lado)
    $pincelCirculo = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(46, 255, 255, 255))
    $g.FillEllipse($pincelCirculo, $circulo)
    $pincelCirculo.Dispose()

    # Triângulo de play
    $m = [int]($lado * 0.16)
    $pontos = @(
        (New-Object System.Drawing.PointF([float]($cx + $m + ($lado - 2 * $m) * 0.10), [float]($cy + $m))),
        (New-Object System.Drawing.PointF([float]($cx + $m + ($lado - 2 * $m) * 0.10), [float]($cy + $lado - $m))),
        (New-Object System.Drawing.PointF([float]($cx + $lado - $m), [float]($cy + $lado / 2)))
    )
    $pincelPlay = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
    $g.FillPolygon($pincelPlay, $pontos)
    $pincelPlay.Dispose()

    # Marca "EFTV" na base (só em tamanhos maiores)
    if ($Size -ge 192) {
        $fonteTam = [float]($Size * 0.105)
        $fonte = New-Object System.Drawing.Font("Segoe UI", $fonteTam, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        $texto = "EFTV"
        $fmt = New-Object System.Drawing.StringFormat
        $fmt.Alignment = [System.Drawing.StringAlignment]::Center
        $fmt.LineAlignment = [System.Drawing.StringAlignment]::Center
        $areaTexto = New-Object System.Drawing.RectangleF(0, [float]($Size * 0.72), $Size, [float]($Size * 0.16))
        $sombra = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(120, 0, 0, 0))
        $areaSombra = New-Object System.Drawing.RectangleF(0, [float]($Size * 0.725), $Size, [float]($Size * 0.16))
        $g.DrawString($texto, $fonte, $sombra, $areaSombra, $fmt)
        $branco = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
        $g.DrawString($texto, $fonte, $branco, $areaTexto, $fmt)
        $branco.Dispose()
        $sombra.Dispose()
        $fmt.Dispose()
        $fonte.Dispose()
    }

    $caminho = Join-Path $destino $Arquivo
    # Salva em memória e grava os bytes (evita erro de GDI+ com caminhos acentuados).
    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    Save-BytesSeguro -Caminho $caminho -Bytes $ms.ToArray()
    $ms.Dispose()
    $g.Dispose()
    $bmp.Dispose()
    Write-Host ("  OK  {0} ({1}x{1})" -f $Arquivo, $Size)
}

Write-Host "Gerando ícones EFTV em $destino"

foreach ($t in 72, 96, 128, 144, 152, 192, 384, 512) {
    New-EftvIcon -Size $t -Arquivo "icon-$t.png" -Redondo
}

New-EftvIcon -Size 512 -Arquivo "icon-maskable-512.png" -Maskable
New-EftvIcon -Size 180 -Arquivo "apple-touch-icon.png" -Redondo
New-EftvIcon -Size 32  -Arquivo "favicon-32.png" -Redondo

# OG image para redes sociais / landing (1200x630)
$largura = 1200
$altura = 630
$og = New-Object System.Drawing.Bitmap($largura, $altura)
$g = [System.Drawing.Graphics]::FromImage($og)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$rect = New-Object System.Drawing.Rectangle(0, 0, $largura, $altura)
$fundo = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
    $rect,
    [System.Drawing.Color]::FromArgb(255, 5, 11, 22),
    [System.Drawing.Color]::FromArgb(255, 10, 40, 80),
    30.0
)
$g.FillRectangle($fundo, $rect)
$fundo.Dispose()

# Círculos decorativos
$deco = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(38, 47, 155, 255))
$g.FillEllipse($deco, 760, -180, 620, 620)
$g.FillEllipse($deco, 900, 380, 420, 420)
$deco.Dispose()

$fonteLogo = New-Object System.Drawing.Font("Segoe UI", 96, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$fonteSub = New-Object System.Drawing.Font("Segoe UI", 36, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
$fonteTag = New-Object System.Drawing.Font("Segoe UI", 26, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$branco = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
$azul = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 47, 155, 255))
$cinza = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 175, 195, 220))

$g.DrawString("EF", $fonteLogo, $branco, 80, 120)
$g.DrawString("TV", $fonteLogo, $azul, 230, 120)
$g.DrawString("Canais ao vivo, filmes e séries", $fonteSub, $branco, 84, 300)
$g.DrawString("Assine por R$ 19,90/mês · 7 dias grátis", $fonteSub, $cinza, 84, 360)
$g.DrawString("ABRA NO NAVEGADOR  ·  INSTALE COMO APP", $fonteTag, $azul, 84, 470)

# Play grande à direita
$pc = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(235, 255, 255, 255))
$pts = @(
    (New-Object System.Drawing.PointF(900, 190)),
    (New-Object System.Drawing.PointF(900, 450)),
    (New-Object System.Drawing.PointF(1090, 320))
)
$g.FillPolygon($pc, $pts)
$pc.Dispose()

$msOg = New-Object System.IO.MemoryStream
$og.Save($msOg, [System.Drawing.Imaging.ImageFormat]::Png)
Save-BytesSeguro -Caminho (Join-Path $destino "og-landing.png") -Bytes $msOg.ToArray()
$msOg.Dispose()
$g.Dispose()
$og.Dispose()
Write-Host "  OK  og-landing.png (1200x630)"

$fonteLogo.Dispose(); $fonteSub.Dispose(); $fonteTag.Dispose()
$branco.Dispose(); $azul.Dispose(); $cinza.Dispose()

Write-Host "Concluído."
