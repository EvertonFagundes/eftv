#!/usr/bin/env bash
# Inicia a EFTV com a API de playlists em http://127.0.0.1:8124
set -euo pipefail
cd "$(dirname "$0")"
exec python3 server.py
