#!/usr/bin/env bash
# EFTV - instalador do servidor local (macOS e Linux)
#
# Garante o Python, obtem o codigo da EFTV, registra o protocolo eftv://
# e sobe o servidor local.

set -euo pipefail

echo
echo "  EFTV - instalador do servidor local"
echo "  ================================"
echo

# ------------------------------------------------------------------ Python
PY=""
if command -v python3 >/dev/null 2>&1; then
  if python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    PY="python3"
  fi
fi
if [ -z "$PY" ] && command -v python >/dev/null 2>&1; then
  if python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    PY="python"
  fi
fi

if [ -z "$PY" ]; then
  echo "  [ERRO] Python 3.10 ou superior nao encontrado."
  echo
  echo "  Instale com um dos comandos abaixo:"
  echo "    sudo apt install python3     (Debian, Ubuntu, Fedora)"
  echo "    brew install python          (macOS)"
  echo
  exit 1
fi

echo "  Python encontrado."

# ------------------------------------------------------------ codigo EFTV
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
if [ ! -f "$RAIZ/server.py" ]; then
  DEST="$HOME/.local/share/eftv"
  if [ ! -f "$DEST/server.py" ]; then
    echo "  Baixando a EFTV..."
    mkdir -p "$(dirname "$DEST")"
    if command -v git >/dev/null 2>&1; then
      git clone --depth 1 https://github.com/EvertonFagundes/eftv.git "$DEST"
    else
      TMP="$(mktemp -d)"
      curl -fsSL -o "$TMP/eftv.zip" \
        https://github.com/EvertonFagundes/eftv/archive/refs/heads/main.zip
      unzip -q "$TMP/eftv.zip" -d "$TMP/extraido"
      mkdir -p "$DEST"
      cp -R "$TMP/extraido/eftv-main/." "$DEST/"
      rm -rf "$TMP"
    fi
  fi
  RAIZ="$DEST"
fi

echo "  Codigo da EFTV em $RAIZ"
echo

# ------------------------------------------- registra eftv:// e inicia
"$PY" "$RAIZ/instalar/instalar-eftv.py"

echo
echo "  Pronto! A EFTV esta rodando em http://127.0.0.1:8124/"
echo "  Na pagina da EFTV, o botao \"Iniciar servidor local\" ja funciona."
echo
