@echo off
title EFTV - remover inicializacao automatica
chcp 65001 >nul 2>&1

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "ALVO=%STARTUP%\EFTV-servidor-local.bat"

echo.
echo   EFTV - inicializacao automatica
echo   ==============================
echo.

if not exist "%ALVO%" goto :nao_existe

del /q "%ALVO%"
if exist "%ALVO%" goto :falhou

echo   Pronto. Removido:
echo     %ALVO%
echo.
echo   O servidor nao vai mais subir sozinho com o Windows.
echo   Para usar quando quiser, abra a pagina e toque em "Iniciar servidor".
echo.
pause
exit /b 0

:nao_existe
echo   O servidor nao estava configurado para iniciar com o Windows.
echo   Nada para remover.
echo.
pause
exit /b 0

:falhou
echo   [ERRO] Nao foi possivel apagar:
echo     %ALVO%
echo.
echo   Apague na mao: abra %STARTUP% e delete o arquivo
echo   EFTV-servidor-local.bat
echo.
pause
exit /b 1
