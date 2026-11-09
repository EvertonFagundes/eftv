"""Plano mensal unico: R$ 19,90, 1 aparelho e 1 stream

Atualiza o plano legado "Dono do App" (criado como default antes do modelo
comercial) para o plano que o cliente realmente assina. O trial de 7 dias usa
o mesmo plano; o que muda e o status da assinatura.

Revision ID: 004
Revises: 003
Create Date: 2026-11-09

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE plans
        SET name = 'Mensal',
            description = 'Acesso completo ao catalogo, 1 aparelho e 1 stream',
            price_cents = 1990,
            max_devices = 1,
            max_simultaneous_streams = 1,
            features = '{"hd": true, "full_hd": true, "4k": false}'::jsonb,
            updated_at = now()
        WHERE name = 'Dono do App'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE plans
        SET name = 'Dono do App',
            description = 'Plano default para o proprietario da instancia EFTV',
            price_cents = 0,
            max_devices = 10,
            max_simultaneous_streams = 5,
            updated_at = now()
        WHERE name = 'Mensal'
        """
    )
