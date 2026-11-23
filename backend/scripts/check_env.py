"""Diagnostico de configuracao para go-live.

Uso:
    python scripts/check_env.py

Nao precisa de banco. Le as variaveis de ambiente (ou backend/.env) e diz o
que falta para vender para usuarios reais. Nao imprime segredos, so se estao
presentes e validos.
"""

from __future__ import annotations

import os
import sys

# Permite rodar de qualquer diretorio.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings  # noqa: E402


def _ok(name: str, ok: bool, hint: str = "") -> None:
    status = "OK" if ok else "FALTA"
    line = f"[{status}] {name}"
    if hint:
        line += f"  -> {hint}"
    print(line)


def main() -> int:
    try:
        settings = Settings()
    except Exception as exc:  # noqa: BLE001
        print("Configuracao invalida:", exc)
        return 1

    errors = 0

    checks = [
        ("SECRET_KEY (>=32, nao placeholder)", len(settings.SECRET_KEY) >= 32, "Render: clique em Generate Value"),
        ("DATABASE_URL", bool(settings.DATABASE_URL), "Supabase/Postgres"),
        ("FRONTEND_URL", settings.FRONTEND_URL.startswith("http"), "URL publica do frontend"),
        ("CORS_ORIGINS", bool(settings.cors_origins), "inclua o dominio do frontend"),
        ("EMAIL_PROVIDER", settings.EMAIL_PROVIDER in {"auto", "brevo", "resend", "dev"}, "brevo em producao"),
    ]
    for name, ok, hint in checks:
        if not ok:
            errors += 1
        _ok(name, ok, "" if ok else hint)

    # Mercado Pago (necessario para vender)
    mp_token = settings.MERCADOPAGO_ACCESS_TOKEN
    mp_ok = bool(mp_token) and mp_token.startswith(("APP_USR-", "TEST-"))
    if not mp_ok:
        errors += 1
    _ok("MERCADOPAGO_ACCESS_TOKEN (conta real: APP_USR-)", mp_ok, "use token de producao, nao de teste")
    _ok(
        "MERCADOPAGO_SANDBOX=false em producao",
        not settings.MERCADOPAGO_SANDBOX or settings.ENVIRONMENT != "production",
        "defina MERCADOPAGO_SANDBOX=false",
    )

    # Streaming (opcional, mas necessario para entregar canais)
    _ok("IPTV_PLAYLIST_URL", bool(settings.IPTV_PLAYLIST_URL), "link da playlist licenciada")
    _ok("APP_APK_URL (atualizacao do app)", bool(settings.APP_APK_URL), "opcional")

    print()
    if errors:
        print(f"{errors} bloqueio(s) para vender. Corrija as variaveis acima no Render.")
        return 1
    print("Configuracao minima OK para vender.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())