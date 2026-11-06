#!/usr/bin/env python3
"""
Seed script to create test user and initial data.
Run: python seed.py
"""

import asyncio
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.auth import hash_password
from app.database import AsyncSessionLocal, init_db
from app.models import User
from sqlalchemy import select


async def seed():
    await init_db()

    async with AsyncSessionLocal() as db:
        # Verifica se já existe usuário de teste
        result = await db.execute(select(User).where(User.email == "teste@eftv.local"))
        existing = result.scalar_one_or_none()

        if existing:
            print("Usuário de teste já existe:", existing.email)
            return

        # Cria usuário de teste
        test_user = User(
            email="teste@eftv.local",
            hashed_password=hash_password("123456"),
            full_name="Usuário Teste EFTV",
            is_active=1,
            is_superuser=0,
        )
        db.add(test_user)
        await db.commit()
        await db.refresh(test_user)

        print(f"Usuario de teste criado:")
        print(f"   Email: teste@eftv.local")
        print(f"   Senha: 123456")
        print(f"   ID: {test_user.id}")


if __name__ == "__main__":
    asyncio.run(seed())