@echo off
title EFTV - liberar o firewall para a rede local
chcp 65001 >nul 2>&1

REM Pede permissao de administrador (UAC) e libera a porta 8124 na rede
REM privada, para o celular e a smart TV conseguirem acessar o servidor.

net session >nul 2>&1
if errorlevel 1 (
  echo Solicitando permissao de administrador...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo.
echo   EFTV - liberando o firewall para o acesso pela rede
echo   ==================================================
echo.

netsh advfirewall firewall delete rule name="EFTV (servidor local na rede)" >nul 2>&1
netsh advfirewall firewall add rule name="EFTV (servidor local na rede)" dir=in action=allow protocol=TCP localport=8124 profile=private

echo.
echo   Pronto. Agora o celular (e a smart TV) na mesma rede Wi-Fi podem
echo   abrir http://IP-DO-NOTEBOOK:8124/ no navegador.
echo.
echo   Para remover a regra depois:
echo     netsh advfirewall firewall delete rule name="EFTV (servidor local na rede)"
echo.
pause
