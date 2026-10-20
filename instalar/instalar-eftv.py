#!/usr/bin/env python3
"""EFTV - instalador e lancador do servidor local.

Este script faz tres coisas:

1. Garante que exista uma copia do codigo da EFTV no computador
   (usa a copia do repositorio quando o script esta dentro dele, senao
   clona ou baixa o codigo do GitHub).
2. Registra o protocolo "eftv://" no sistema, que e o que permite que a
   pagina (inclusive a do GitHub Pages) inicie o servidor local.
3. Sobe o server.py e abre o navegador.

Uso:
    python3 instalar-eftv.py              # instala, registra e inicia
    python3 instalar-eftv.py --instalar   # so instala e registra
    python3 instalar-eftv.py --iniciar    # so inicia o servidor
    python3 instalar-eftv.py --parar      # encerra o servidor
    python3 instalar-eftv.py --status     # mostra o estado
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

PROTOCOLO = "eftv"
PORTA_PADRAO = 8124
REPO_URL = "https://github.com/EvertonFagundes/eftv.git"
ZIP_URL = "https://github.com/EvertonFagundes/eftv/archive/refs/heads/main.zip"
USER_AGENT = "EFTV-instalador"


# --------------------------------------------------------------------------- #
# Caminhos
# --------------------------------------------------------------------------- #
def pasta_dados() -> str:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "EFTV")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "EFTV")
    return os.path.join(os.path.expanduser("~"), ".local", "share", "eftv")


def dir_raiz() -> str:
    """Pasta onde o server.py vive, quando o script roda de dentro do repo."""
    aqui = os.path.dirname(os.path.abspath(__file__))
    raiz = os.path.dirname(aqui)
    if os.path.isfile(os.path.join(raiz, "server.py")):
        return raiz
    return ""


def log(mensagem: str) -> None:
    print(mensagem, flush=True)


# --------------------------------------------------------------------------- #
# Obter o codigo
# --------------------------------------------------------------------------- #
def tem_git() -> bool:
    return shutil.which("git") is not None


def baixar_zip(destino: str) -> bool:
    """Baixa o repositorio em zip (sem depender do git)."""
    try:
        requisicao = urllib.request.Request(ZIP_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(requisicao, timeout=60) as resposta:
            dados = resposta.read()
        os.makedirs(destino, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(dados)) as pacote:
            pacote.extractall(destino)
    except Exception as erro:  # noqa: BLE001
        log(f"Falha ao baixar o repositorio: {erro}")
        return False

    # O zip tem uma pasta "eftv-main" na raiz: o conteudo dela e o repo.
    entradas = [nome for nome in os.listdir(destino) if os.path.isdir(os.path.join(destino, nome))]
    if len(entradas) == 1 and os.path.isfile(os.path.join(destino, entradas[0], "server.py")):
        origem = os.path.join(destino, entradas[0])
        for nome in os.listdir(origem):
            shutil.move(os.path.join(origem, nome), os.path.join(destino, nome))
        os.rmdir(origem)
    return os.path.isfile(os.path.join(destino, "server.py"))


def clonar(destino: str) -> bool:
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", REPO_URL, destino],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as erro:  # noqa: BLE001
        log(f"Falha ao clonar o repositorio: {erro}")
        return False
    return os.path.isfile(os.path.join(destino, "server.py"))


def garantir_codigo() -> str:
    """Devolve a pasta com o server.py, baixando se for preciso."""
    raiz = dir_raiz()
    if raiz:
        return raiz

    destino = pasta_dados()
    if os.path.isfile(os.path.join(destino, "server.py")):
        return destino

    log("Baixando a EFTV...")
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    if not tem_git() and not baixar_zip(destino):
        if not clonar(destino):
            raise SystemExit("Nao foi possivel obter o codigo da EFTV.")
    elif not clonar(destino):
        if not baixar_zip(destino):
            raise SystemExit("Nao foi possivel obter o codigo da EFTV.")
    return destino


# --------------------------------------------------------------------------- #
# Protocolo eftv://
# --------------------------------------------------------------------------- #
def registrar_windows(raiz: str) -> bool:
    try:
        import winreg
    except ImportError:
        return False

    python = os.path.abspath(sys.executable)
    server = os.path.join(raiz, "server.py")
    comando = f'"{python}" "{server}" "%1"'
    icone = os.path.join(raiz, "assets", "img", "eftv-mark.svg")

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{PROTOCOLO}") as chave:
            winreg.SetValueEx(chave, "", 0, winreg.REG_SZ, f"URL:{PROTOCOLO.upper()} Protocol")
            winreg.SetValueEx(chave, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{PROTOCOLO}\\DefaultIcon") as chave:
            winreg.SetValueEx(chave, "", 0, winreg.REG_SZ, f'"{icone}"')
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{PROTOCOLO}\\shell\\open\\command"
        ) as chave:
            winreg.SetValueEx(chave, "", 0, winreg.REG_SZ, comando)
    except OSError as erro:
        log(f"Falha ao registrar o protocolo no Windows: {erro}")
        return False
    return True


def registrar_unix(raiz: str) -> bool:
    python = os.path.abspath(sys.executable)
    server = os.path.join(raiz, "server.py")
    icone = os.path.join(raiz, "assets", "img", "eftv-mark.svg")

    base = os.path.join(os.path.expanduser("~"), ".local", "share", "applications")
    os.makedirs(base, exist_ok=True)
    destino = os.path.join(base, f"{PROTOCOLO}.desktop")

    conteudo = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=EFTV\n"
        "Comment=Player local de playlists IPTV\n"
        f'Exec="{python}" "{server}" %u\n'
        "Terminal=false\n"
        f"Icon={icone}\n"
        f"MimeType=x-scheme-handler/{PROTOCOLO};\n"
        "Categories=Network;Video;Player;\n"
    )
    try:
        with open(destino, "w", encoding="utf-8") as arquivo:
            arquivo.write(conteudo)
        os.chmod(destino, 0o755)
    except OSError as erro:
        log(f"Falha ao registrar o protocolo: {erro}")
        return False

    for comando in (
        ["update-desktop-database", base],
        ["xdg-mime", "default", f"{PROTOCOLO}.desktop", f"x-scheme-handler/{PROTOCOLO}"],
    ):
        if shutil.which(comando[0]):
            try:
                subprocess.run(comando, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass
    return True


def registrar_protocolo(raiz: str) -> bool:
    if os.name == "nt":
        ok = registrar_windows(raiz)
    else:
        ok = registrar_unix(raiz)
    if ok:
        log(f"Protocolo {PROTOCOLO}:// registrado.")
    return ok


# --------------------------------------------------------------------------- #
# Servidor
# --------------------------------------------------------------------------- #
def porta_em_uso(porta: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.6)
        return sock.connect_ex(("127.0.0.1", porta)) == 0


def iniciar(raiz: str, porta: int = PORTA_PADRAO) -> bool:
    server = os.path.join(raiz, "server.py")
    if not os.path.isfile(server):
        log("server.py nao encontrado.")
        return False

    if porta_em_uso(porta):
        log(f"A EFTV ja esta rodando em http://127.0.0.1:{porta}/")
        abrir_navegador(f"http://127.0.0.1:{porta}/")
        return True

    comando = [sys.executable, server, "--abrir", f"--porta={porta}"]
    try:
        if os.name == "nt":
            subprocess.Popen(
                comando,
                cwd=raiz,
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
        else:
            subprocess.Popen(
                comando,
                cwd=raiz,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except OSError as erro:
        log(f"Falha ao iniciar o servidor: {erro}")
        return False

    for _ in range(40):
        time.sleep(0.25)
        if porta_em_uso(porta):
            log(f"EFTV no ar em http://127.0.0.1:{porta}/")
            return True

    log("O servidor demorou para responder. Confira a janela do terminal.")
    return False


def abrir_navegador(url: str) -> None:
    try:
        import webbrowser

        webbrowser.open(url, new=2)
    except Exception:  # noqa: BLE001
        pass


def parar(porta: int = PORTA_PADRAO) -> bool:
    import urllib.error
    import urllib.request

    requisicao = urllib.request.Request(
        f"http://127.0.0.1:{porta}/api/servidor?acao=parar", method="POST"
    )
    requisicao.add_header("X-EFTV-Local", "1")
    try:
        with urllib.request.urlopen(requisicao, timeout=5) as resposta:
            log(resposta.read().decode("utf-8", "replace").strip())
        return True
    except urllib.error.HTTPError as erro:
        log(f"Erro ao encerrar o servidor (HTTP {erro.code}).")
    except OSError:
        log(f"Nenhum servidor EFTV rodando na porta {porta}.")
    return False


def status(porta: int = PORTA_PADRAO) -> bool:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/status", timeout=4) as resposta:
            dados = json.loads(resposta.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        log(f"Servidor parado (porta {porta}).")
        return False

    log(f"Servidor ativo em http://127.0.0.1:{porta}/")
    log(
        f"  playlists: {dados.get('playlists', 0)} | canais: {dados.get('canais', 0)} | "
        f"python {dados.get('python', '?')}"
    )
    return True


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    argumentos = sys.argv[1:]
    porta = PORTA_PADRAO
    for argumento in argumentos:
        if argumento.startswith("--porta=") or argumento.startswith("--port="):
            try:
                porta = int(argumento.split("=", 1)[1])
            except ValueError:
                pass

    if "--parar" in argumentos:
        return 0 if parar(porta) else 1

    if "--status" in argumentos:
        return 0 if status(porta) else 1

    if "--iniciar" in argumentos:
        raiz = dir_raiz() or garantir_codigo()
        return 0 if iniciar(raiz, porta) else 1

    if "--instalar" in argumentos:
        raiz = dir_raiz() or garantir_codigo()
        log(f"Codigo da EFTV em {raiz}")
        if not registrar_protocolo(raiz):
            log("Nao foi possivel registrar o protocolo eftv://.")
            return 1
        log("Instalacao concluida. Use --iniciar para subir o servidor.")
        return 0

    # Fluxo completo: instala o codigo, registra o protocolo e sobe o servidor.
    log("EFTV - instalador do servidor local")
    log("-" * 34)
    raiz = garantir_codigo()
    log(f"Codigo da EFTV em {raiz}")

    if not registrar_protocolo(raiz):
        log("Nao foi possivel registrar o protocolo eftv://.")
        log("Voce ainda pode iniciar o servidor manualmente com: python3 server.py")
        return 1

    if not iniciar(raiz, porta):
        return 1

    print()
    log("Pronto! A EFTV esta rodando em http://127.0.0.1:%d/" % porta)
    log("Agora a pagina da EFTV consegue iniciar o servidor com um clique.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
