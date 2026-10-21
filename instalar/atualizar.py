#!/usr/bin/env python3
"""Atualiza a copia do codigo da EFTV a partir do pacote publicado.

Usado pelo comando "eftv-atualizar" quando a instalacao foi feita pelo .zip
(sem repositorio git). Preserva a pasta data/ — as playlists do usuario nunca
sao tocadas.

Uso:
    python3 instalar/atualizar.py [pasta_da_instalacao]
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

URL = "https://evertonfagundes.github.io/eftv/eftv-android.zip"
URL_ALT = "https://raw.githubusercontent.com/EvertonFagundes/eftv/main/eftv-android.zip"


def _comando(url: str, destino: str) -> bool:
    """Tenta curl e wget; cada um pode estar quebrado (upgrade incompleto)."""
    tentativas = []
    if shutil.which("curl"):
        tentativas.append([
            "curl", "-fL", "--connect-timeout", "25", "--max-time", "240",
            "-o", destino, url,
        ])
    if shutil.which("wget"):
        tentativas.append(["wget", "-q", "--timeout=30", "-O", destino, url])

    for comando in tentativas:
        try:
            subprocess.check_call(
                comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if os.path.getsize(destino) > 1024:
                return True
        except Exception:  # noqa: BLE001 - tenta o proximo programa
            continue
    return False


def baixar(destino: str) -> bool:
    for url in (URL, URL_ALT):
        print(f"  Baixando {url}")
        try:
            if _comando(url, destino):
                return True

            import urllib.request

            with urllib.request.urlopen(url, timeout=60) as resposta, open(destino, "wb") as saida:
                shutil.copyfileobj(resposta, saida)
            if os.path.getsize(destino) > 1024:
                return True
        except Exception as erro:  # noqa: BLE001 - tenta a proxima origem
            print(f"  Falhou: {erro}")
    return False


def instalar(pacote: str, destino: str) -> int:
    with tempfile.TemporaryDirectory() as temporario:
        with zipfile.ZipFile(pacote) as z:
            z.extractall(temporario)

        pastas = [p for p in os.listdir(temporario) if os.path.isdir(os.path.join(temporario, p))]
        if not pastas:
            print("  Pacote inesperado: nenhuma pasta na raiz.")
            return 1
        raiz = os.path.join(temporario, pastas[0])

        copiados = 0
        for base, _dirs, arquivos in os.walk(raiz):
            relativo = os.path.relpath(base, raiz)
            if relativo.split(os.sep)[0] == "data":
                continue  # nunca sobrescreve a pasta de playlists
            alvo = destino if relativo == "." else os.path.join(destino, relativo)
            os.makedirs(alvo, exist_ok=True)
            for arquivo in arquivos:
                shutil.copy2(os.path.join(base, arquivo), os.path.join(alvo, arquivo))
                copiados += 1

    print(f"  {copiados} arquivos atualizados em {destino}")
    print("  Suas playlists em data/ ficaram intactas.")
    return 0


def main() -> int:
    destino = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/eftv"))
    if not os.path.isdir(destino):
        print(f"  [ERRO] Pasta nao encontrada: {destino}")
        return 1

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as arquivo:
        pacote = arquivo.name
    try:
        if not baixar(pacote):
            print("  [ERRO] Nao foi possivel baixar a atualizacao.")
            return 1
        return instalar(pacote, destino)
    finally:
        try:
            os.unlink(pacote)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
