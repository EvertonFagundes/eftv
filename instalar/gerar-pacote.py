#!/usr/bin/env python3
"""Gera o pacote eftv-android.zip.

O zip e uma copia do projeto pronta para instalar no Android (Termux) sem
git: e o caminho mais seguro quando o aparelho usa um espelho do GitHub que
esta fora do ar, ou quando a rede bloqueia o github.com.

Uso:
    python3 instalar/gerar-pacote.py            # gera na raiz do projeto
    python3 instalar/gerar-pacote.py saida.zip
"""

from __future__ import annotations

import os
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOME_PADRAO = "eftv-android.zip"

# O que nao entra no pacote.
IGNORAR_PASTAS = {".git", ".github", "data", "__pycache__", ".idea", ".vscode"}
IGNORAR_ARQUIVOS = {".DS_Store", "playlists.json", NOME_PADRAO}


def collected() -> list[tuple[str, str]]:
    """Lista (caminho no zip, caminho no disco) dos arquivos do pacote."""
    arquivos = []
    for base, pastas, nomes in os.walk(RAIZ):
        pastas[:] = [p for p in pastas if p not in IGNORAR_PASTAS]
        for nome in nomes:
            if nome in IGNORAR_ARQUIVOS or nome.endswith((".pyc", ".log", ".tmp")):
                continue
            caminho = os.path.join(base, nome)
            relativo = os.path.relpath(caminho, RAIZ).replace("\\", "/")
            arquivos.append((relativo, caminho))
    return arquivos


def main() -> int:
    destino = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, NOME_PADRAO)
    arquivos = collected()
    if not arquivos:
        print("Nenhum arquivo encontrado para empacotar.")
        return 1

    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as pacote:
        for relativo, caminho in arquivos:
            pacote.write(caminho, "eftv/" + relativo)

    tamanho = os.path.getsize(destino)
    print(f"{destino} ({tamanho / 1024:.0f} KB, {len(arquivos)} arquivos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
