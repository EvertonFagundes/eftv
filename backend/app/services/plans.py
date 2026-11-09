"""Plano comercial unico do EFTV.

O trial de 7 dias usa o mesmo plano que a assinatura paga: o que muda e o
status da assinatura (``trial`` ou ``active``). Assim o preco exibido na tela
de planos e o mesmo que o cliente pagara no Mercado Pago.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Plan

PLAN_NAME = "Mensal"
PLAN_DESCRIPTION = "Acesso completo ao catalogo, 1 aparelho e 1 stream"
PLAN_PRICE_CENTS = 1990
PLAN_MAX_DEVICES = 1
PLAN_MAX_STREAMS = 1
PLAN_FEATURES = {"hd": True, "full_hd": True, "4k": False}


async def get_or_create_plan(db: AsyncSession) -> Plan:
    """Devolve o plano ativo ou cria o plano mensal padrao.

    Nao sobrescreve um plano existente: o administrador pode ajustar preco e
    limites pela API sem que o proximo cadastro reverta a mudanca.
    """
    result = await db.execute(
        select(Plan)
        .where(Plan.is_active.is_(True))
        .order_by(Plan.sort_order.asc(), Plan.created_at.asc())
    )
    plan = result.scalars().first()
    if plan is not None:
        return plan

    plan = Plan(
        name=PLAN_NAME,
        description=PLAN_DESCRIPTION,
        price_cents=PLAN_PRICE_CENTS,
        currency="BRL",
        interval="month",
        max_simultaneous_streams=PLAN_MAX_STREAMS,
        max_devices=PLAN_MAX_DEVICES,
        features=PLAN_FEATURES,
        sort_order=0,
    )
    db.add(plan)
    await db.flush()
    return plan
