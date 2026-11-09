"""Cria (ou atualiza) um assinante com plano mensal ativo.

Uso dentro do container:

    docker compose --env-file deploy/.env -f docker-compose.prod.yml \
        exec api python scripts/seed_subscriber.py

Ou com valores explicitos:

    SEED_EMAIL=cliente@exemplo.com SEED_PASSWORD='senha-forte' \
        python scripts/seed_subscriber.py --days 30

Se SEED_PASSWORD nao for informada, uma senha aleatoria e gerada e exibida.
"""

import argparse
import asyncio
import os
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Permite executar como "python scripts/seed_subscriber.py" de dentro de backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.database import AsyncSessionLocal, engine  # noqa: E402
from app.models import Plan, Subscription, User  # noqa: E402
from app.services.auth_service import hash_password  # noqa: E402


async def seed(email: str, password: str, days: int, is_admin: bool) -> None:
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                full_name="Assinante EFTV",
                is_admin=is_admin,
                email_verified=True,
            )
            db.add(user)
            await db.flush()
        else:
            user.password_hash = hash_password(password)
            user.email_verified = True
            if is_admin:
                user.is_admin = True

        plan = (await db.execute(select(Plan).where(Plan.name == "Mensal"))).scalar_one_or_none()
        if plan is None:
            plan = Plan(
                name="Mensal",
                description="Acesso completo ao catalogo",
                price_cents=1990,
                interval="month",
                max_simultaneous_streams=1,
                max_devices=1,
                features={"hd": True, "full_hd": True},
                is_active=True,
            )
            db.add(plan)
            await db.flush()

        now = datetime.now(UTC)
        end = now + timedelta(days=days)

        subscription = (
            await db.execute(select(Subscription).where(Subscription.user_id == user.id))
        ).scalar_one_or_none()
        if subscription is None:
            subscription = Subscription(
                user_id=user.id,
                plan_id=plan.id,
                status="active",
                current_period_start=now,
                current_period_end=end,
            )
            db.add(subscription)
        else:
            subscription.plan_id = plan.id
            subscription.status = "active"
            subscription.current_period_start = now
            subscription.current_period_end = end

        await db.commit()

    await engine.dispose()
    print(f"assinante: {email}")  # noqa: T201
    print(f"senha:     {password}")  # noqa: T201
    print(f"ativo ate: {end.date()} ({days} dias)")  # noqa: T201


def main() -> None:
    parser = argparse.ArgumentParser(description="Cria assinante ativo no EFTV")
    parser.add_argument("--email", default=os.getenv("SEED_EMAIL", "demo@eftv.com.br"))
    parser.add_argument(
        "--password", default=os.getenv("SEED_PASSWORD") or secrets.token_urlsafe(12)
    )
    parser.add_argument("--days", type=int, default=int(os.getenv("SEED_DAYS", "30")))
    parser.add_argument("--admin", action="store_true", help="Concede acesso administrativo")
    args = parser.parse_args()

    asyncio.run(seed(args.email, args.password, args.days, args.admin))


if __name__ == "__main__":
    main()
