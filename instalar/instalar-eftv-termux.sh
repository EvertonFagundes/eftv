#!/data/data/com.termux/files/usr/bin/bash
# EFTV - instalador e lancador para Termux (Android).
#
# Instala o Python, baixa a EFTV, cria o comando "eftv" e sobe o servidor
# escutando na rede Wi-Fi (para abrir na smart TV, tablet ou notebook).
#
# Uso:
#   bash instalar-eftv-termux.sh            # instala e inicia
#   bash instalar-eftv-termux.sh --instalar # so instala, nao inicia
#   bash instalar-eftv-termux.sh --atualizar # atualiza a copia do codigo

set -euo pipefail

REPO="https://github.com/EvertonFagundes/eftv.git"
DEST="${EFTV_HOME:-$HOME/eftv}"
BIN="$HOME/bin"
MARKER="# EFTV (Termux)"

apenas_instalar=0
atualizar=0
for argumento in "$@"; do
  case "$argumento" in
    --instalar) apenas_instalar=1 ;;
    --atualizar) atualizar=1 ;;
  esac
done

echo
echo "  EFTV - instalador para Termux (Android)"
echo "  ====================================="
echo

# ------------------------------------------------------------- checagens
if [ ! -d /data/data/com.termux/files ] && [ -z "${PREFIX:-}" ]; then
  echo "  [ERRO] Este script precisa rodar dentro do Termux."
  echo
  echo "  Instale o Termux (F-Droid ou Google Play) e rode de novo:"
  echo "    pkg install python git"
  echo "    git clone $REPO ~/eftv"
  echo "    bash ~/eftv/instalar/instalar-eftv-termux.sh"
  echo
  exit 1
fi

if ! command -v python >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
  echo "  Instalando o Python..."
  pkg install -y python || {
    echo "  [ERRO] Nao foi possivel instalar o Python. Rode: pkg update && pkg install python"
    exit 1
  }
fi

if ! command -v git >/dev/null 2>&1; then
  echo "  Instalando o Git..."
  pkg install -y git || {
    echo "  [ERRO] Nao foi possivel instalar o Git. Rode: pkg update && pkg install git"
    exit 1
  }
fi

PYTHON="python3"
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON="python"

# --------------------------------------------------------------- codigo
if [ -d "$DEST/.git" ]; then
  if [ "$atualizar" -eq 1 ]; then
    echo "  Atualizando a EFTV..."
    git -C "$DEST" pull --ff-only || echo "  (aviso: nao foi possivel atualizar)"
  else
    echo "  Codigo ja existe em $DEST"
  fi
else
  echo "  Baixando a EFTV..."
  mkdir -p "$(dirname "$DEST")"
  git clone --depth 1 "$REPO" "$DEST"
fi

# ------------------------------------------------------- comando "eftv"
mkdir -p "$BIN"
cat > "$BIN/eftv" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
# Sobe a EFTV escutando na rede Wi-Fi e abre o navegador do Android.
exec "$PYTHON" "$DEST/server.py" --lan --abrir "\$@"
EOF

cat > "$BIN/eftv-parar" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
# Encerra a EFTV que estiver rodando neste aparelho.
exec "$PYTHON" "$DEST/server.py" --parar "\$@"
EOF

cat > "$BIN/eftv-atualizar" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
# Atualiza a copia do codigo da EFTV.
git -C "$DEST" pull --ff-only
EOF

chmod +x "$BIN/eftv" "$BIN/eftv-parar" "$BIN/eftv-atualizar"

# ------------------------------------------------- iniciar com o aparelho
# O Termux:Boot roda este script quando o Android lanca o aparelho.
BOOT="$HOME/.termux/boot"
if mkdir -p "$BOOT" 2>/dev/null; then
  cat > "$BOOT/eftv" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
# Iniciado automaticamente pelo Termux:Boot quando o aparelho liga.
export PATH="\$HOME/bin:\$PATH"
termux-wake-lock >/dev/null 2>&1
"$PYTHON" "$DEST/server.py" --lan
EOF
  chmod +x "$BOOT/eftv"
  tem_boot=1
else
  tem_boot=0
fi

# Coloca o ~/bin no PATH das próximas sessoes.
for arquivo in "$HOME/.bashrc" "$HOME/.profile"; do
  touch "$arquivo"
  grep -q "$MARKER" "$arquivo" || {
    echo "" >> "$arquivo"
    echo "$MARKER" >> "$arquivo"
    echo "export PATH=\"\$HOME/bin:\$PATH\"" >> "$arquivo"
  }
done

echo "  Comandos prontos: eftv, eftv-parar, eftv-atualizar"
echo

if [ "$apenas_instalar" -eq 1 ]; then
  echo "  Instalacao concluida. Rode \"eftv\" para iniciar o servidor."
  if [ "$tem_boot" -eq 1 ]; then
    echo
    echo "  Para iniciar junto com o aparelho, instale o addon Termux:Boot."
  fi
  echo
  exit 0
fi

# Mantem o processo vivo quando o Android tentar matar o Termux.
if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock >/dev/null 2>&1 || true
  echo "  Wake lock ligado: o servidor continua rodando com a tela apagada."
else
  echo "  Aviso: instale o addon Termux:API para o servidor continuar com"
  echo "  a tela apagada (comando: pkg install termux-api)."
fi

echo "  Iniciando a EFTV (Ctrl+C para parar)..."
echo
echo "  A TV precisa do endereco \"Na rede Wi-Fi\" que aparecera logo abaixo."
echo
exec "$PYTHON" "$DEST/server.py" --lan --abrir
