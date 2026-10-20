@echo off
setlocal enabledelayedexpansion
title EFTV - instalador do servidor local
chcp 65001 >nul 2>&1

echo.
echo   EFTV - instalador do servidor local
echo   ================================
echo.

REM ---------------------------------------------------------------- Python
set "PYEXE="

py -3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if not errorlevel 1 set "PYEXE=py -3"

if not defined PYEXE (
  python -c "import sys;raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
  if not errorlevel 1 set "PYEXE=python"
)

if not defined PYEXE call :achar_python

if not defined PYEXE (
  echo   [ERRO] Python 3.10 ou superior nao encontrado.
  echo.
  echo   Instalando o Python com o winget...
  winget install --id Python.Python.3.12 -e --source winget --accept-source-agreements --accept-package-agreements --silent
  echo.
  echo   Se o Python acabou de ser instalado, feche esta janela
  echo   e execute o instalador de novo.
  echo.
  pause
  exit /b 1
)

echo   Python encontrado.

REM ----------------------------------------------------------- codigo EFTV
set "RAIZ="
if exist "%~dp0..\server.py" set "RAIZ=%~dp0.."

if not defined RAIZ (
  set "DEST=%LOCALAPPDATA%\EFTV"
  if not exist "!DEST!\server.py" (
    echo   Baixando a EFTV...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $dest=Join-Path $env:LOCALAPPDATA 'EFTV'; $zip=Join-Path $env:TEMP 'eftv-main.zip'; Invoke-WebRequest -Uri 'https://github.com/EvertonFagundes/eftv/archive/refs/heads/main.zip' -OutFile $zip; $tmp=Join-Path $env:TEMP 'eftv-extract'; if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }; Expand-Archive -Path $zip -DestinationPath $tmp -Force; $src=Get-ChildItem $tmp -Directory | Select-Object -First 1; if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }; New-Item -ItemType Directory -Force -Path $dest | Out-Null; Copy-Item -Path (Join-Path $src.FullName '*') -Destination $dest -Recurse -Force; Remove-Item $tmp -Recurse -Force; Remove-Item $zip -Force"
    if not exist "!DEST!\server.py" (
      echo.
      echo   [ERRO] Nao foi possivel baixar a EFTV.
      pause
      exit /b 1
    )
  )
  set "RAIZ=!DEST!"
)

echo   Codigo da EFTV em !RAIZ!
echo.

REM --------------------------------------------- registra eftv:// e inicia
%PYEXE% "!RAIZ!\instalar\instalar-eftv.py"

echo.
if errorlevel 1 (
  echo   [ERRO] A instalacao nao terminou bem. Veja a mensagem acima.
) else (
  echo   Pronto. A EFTV esta rodando em http://127.0.0.1:8124/
  echo   Na pagina da EFTV, o botao "Iniciar servidor local" ja funciona.
)
echo.
pause
exit /b 0

:achar_python
for %%V in (313 312 311 310) do (
  if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
    set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
    goto :eof
  )
)
goto :eof
