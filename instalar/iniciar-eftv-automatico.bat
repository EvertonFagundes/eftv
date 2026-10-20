@echo off
setlocal enabledelayedexpansion
title EFTV - iniciar automaticamente com o Windows
chcp 65001 >nul 2>&1

echo.
echo   EFTV - inicializacao automatica
echo   ==============================
echo.
echo   Este script coloca o servidor local na inicializacao do Windows.
echo   Assim o notebook ja sobe com a EFTV pronta, sem ninguem precisar
echo   abrir um terminal.
echo.

call :achar_python
if not defined PYEXE (
  echo   [ERRO] Python 3.10 ou superior nao encontrado.
  echo   Instale com: winget install Python.Python.3.12
  pause
  exit /b 1
)

set "RAIZ=%~dp0.."
if not exist "%~dp0..\server.py" (
  echo.
  echo   [ERRO] Este script precisa ficar dentro da pasta do projeto EFTV,
  echo          no mesmo lugar do server.py.
  pause
  exit /b 1
)

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if not exist "%STARTUP%" mkdir "%STARTUP%"
set "ALVO=%STARTUP%\EFTV-servidor-local.bat"

call :escrever_inicializador

echo   Servidor configurado para iniciar com o Windows.
echo.
echo   Arquivo criado:
echo     %ALVO%
echo.
echo   Ele sobe o servidor em segundo plano, escutando tambem na rede
echo   Wi-Fi, para o celular e a smart TV acessarem.
echo.
echo   Para desativar, apague o arquivo acima ou rode:
echo     del "%ALVO%"
echo.
pause
exit /b 0

REM ----------------------------------------------------------------------
:achar_python
set "PYEXE="
py -3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if not errorlevel 1 set "PYEXE=py -3"
if not defined PYEXE python -c "import sys;raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if not defined PYEXE if not errorlevel 1 set "PYEXE=python"
if not defined PYEXE call :achar_python_instalado
goto :eof

:achar_python_instalado
for %%V in (313 312 311 310) do (
  if not defined PYEXE (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
      set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
    )
  )
)
goto :eof

REM ----------------------------------------------------------------------
:escrever_inicializador
> "%ALVO%" echo @echo off
>> "%ALVO%" echo start "" "!PYEXE!" "!RAIZ!\server.py" --lan
>> "%ALVO%" echo exit
goto :eof
