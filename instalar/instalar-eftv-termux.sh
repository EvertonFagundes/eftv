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
    echo "  Aviso: Git nao instalado. Vou baixar a EFTV em .zip."
    TEM_GIT=0
  }
fi

PYTHON="python3"
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON="python"

# --------------------------------------------------------------- codigo
TMPZIP="$HOME/eftv-download.zip"
TMPDIR="$HOME/eftv-download"
TMP_LOG="$HOME/eftv-git.log"
LIMITE_SEGUNDOS=90

# Roda o git com limite de tempo: se a rede travar, o script segue para
# a proxima alternativa em vez de ficar parado.
git_com_limite() {
  if command -v timeout >/dev/null 2>&1; then
    timeout "$LIMITE_SEGUNDOS" git "$@"
  else
    git "$@"
  fi
}

baixar_zip() {
  # Sem o git, ou com o git indisponivel: tenta o .zip do repositorio.
  for url in \
    "https://evertonfagundes.github.io/eftv/eftv-android.zip" \
    "https://raw.githubusercontent.com/EvertonFagundes/eftv/main/eftv-android.zip" \
    "https://codeload.github.com/EvertonFagundes/eftv/zip/refs/heads/main" \
    "https://github.com/EvertonFagundes/eftv/archive/refs/heads/main.zip"; do
    echo "    $url"
    rm -f "$TMPZIP"
    if command -v curl >/dev/null 2>&1; then
      curl -fL --connect-timeout 25 --max-time 180 --retry 2 -o "$TMPZIP" "$url" 2>/dev/null || continue
    elif command -v wget >/dev/null 2>&1; then
      wget -q --timeout=30 --tries=2 -O "$TMPZIP" "$url" || continue
    else
      continue
    fi
    rm -rf "$TMPDIR"
    mkdir -p "$TMPDIR"
    if ! "$PYTHON" -c "
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    z.extractall(sys.argv[2])
" "$TMPZIP" "$TMPDIR" 2>/dev/null; then
      continue
    fi
    # O zip tem uma pasta "eftv-main" na raiz: o conteudo dela e o repo.
    for pasta in "$TMPDIR"/*; do
      [ -d "$pasta" ] || continue
      rm -rf "$DEST"
      mv "$pasta" "$DEST"
      break
    done
    rm -rf "$TMPDIR" "$TMPZIP"
    [ -f "$DEST/server.py" ] && return 0
  done
  return 1
}

obter_codigo() {
  if [ -d "$DEST/.git" ]; then
    if [ "$atualizar" -eq 1 ]; then
      echo "  Atualizando a EFTV..."
      git -C "$DEST" pull --ff-only || echo "  (aviso: nao foi possivel atualizar)"
    else
      echo "  Codigo ja existe em $DEST"
    fi
    return 0
  fi

  mkdir -p "$(dirname "$DEST")"

  # 1) Git clone normal: usa a configuracao do aparelho (pode ter espelho).
  # O limite de tempo evita ficar preso quando a rede nao responde.
  if command -v git >/dev/null 2>&1; then
    echo "  Baixando a EFTV com git..."
    if git_com_limite clone --depth 1 "$REPO" "$DEST" > "$TMP_LOG" 2>&1; then
      sed 's/^/    /' "$TMP_LOG"
      [ -f "$DEST/server.py" ] && return 0
    else
      sed 's/^/    /' "$TMP_LOG"
    fi
    rm -rf "$DEST"

    # 2) Git clone ignorando a configuracao global: contorna espelho quebrado.
    echo "  Tentando de novo, direto do GitHub (sem espelho)..."
    CASA_VAZIA="$(mktemp -d)"
    if HOME="$CASA_VAZIA" git_com_limite clone --depth 1 "$REPO" "$DEST" > "$TMP_LOG" 2>&1; then
      sed 's/^/    /' "$TMP_LOG"
      [ -f "$DEST/server.py" ] && { rm -rf "$CASA_VAZIA"; return 0; }
    else
      sed 's/^/    /' "$TMP_LOG"
    fi
    rm -rf "$DEST" "$CASA_VAZIA"
  fi

  # 3) Ultimo recurso: o .zip do repositorio.
  echo "  Baixando a EFTV em .zip..."
  if baixar_zip; then
    return 0
  fi

  return 1
}

if ! obter_codigo; then
  echo
  echo "  [ERRO] Nao foi possivel baixar a EFTV."
  echo
  echo "  O aparelho pode estar usando um espelho do GitHub que esta fora"
  echo "  do ar. Tente uma destas opcoes:"
  echo
  echo "  a) Baixe o pacote no navegador do celular:"
  echo "     https://evertonfagundes.github.io/eftv/eftv-android.zip"
  echo "     e depois, no Termux, cole estas tres linhas:"
  echo "       pkg install -y unzip"
  echo "       unzip ~/eftv-android.zip -d ~"
  echo "       bash ~/eftv/instalar/instalar-eftv-termux.sh"
  echo
  echo "  b) Ou baixe direto do GitHub:"
  echo "     https://github.com/EvertonFagundes/eftv/archive/refs/heads/main.zip"
  echo "     e no Termux:"
  echo "       pkg install -y unzip"
  echo "       unzip ~/eftv-main.zip -d ~"
  echo "       bash ~/eftv/instalar/instalar-eftv-termux.sh"
  echo
  echo "  c) Verifique o espelho configurado no git:"
  echo "       git config --global --get-regexp insteadOf"
  echo "     e remova a regra com:"
  echo "       git config --global --unset-all url.<endereco>.insteadOf"
  echo
  exit 1
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

cat > "$BIN/eftv-servidor" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
# Sobe a EFTV na rede Wi-Fi sem abrir o navegador (para TV Box e
# servidores que nao tem tela). O comando "eftv" abre o navegador.
exec "$PYTHON" "$DEST/server.py" --lan --sem-navegador "\$@"
EOF

cat > "$BIN/eftv-atualizar" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
# Atualiza a copia do codigo da EFTV.
git -C "$DEST" pull --ff-only
EOF

chmod +x "$BIN/eftv" "$BIN/eftv-parar" "$BIN/eftv-servidor" "$BIN/eftv-atualizar"

# ------------------------------------------------- iniciar com o aparelho
# O Termux:Boot roda este script quando o Android lanca o aparelho.
BOOT="$HOME/.termux/boot"
if mkdir -p "$BOOT" 2>/dev/null; then
  cat > "$BOOT/eftv" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
# Iniciado automaticamente pelo Termux:Boot quando o aparelho liga.
export PATH="\$HOME/bin:\$PATH"
termux-wake-lock >/dev/null 2>&1
"$PYTHON" "$DEST/server.py" --lan --sem-navegador
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

echo "  Comandos prontos: eftv, eftv-servidor, eftv-parar, eftv-atualizar"
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
