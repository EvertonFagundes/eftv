"""Plano mensal passa a liberar 2 aparelhos

Antes o plano permitia 1 aparelho. Quem trocava de celular ou instalava o app
na TV ficava bloqueado com "Assinatura em uso". O plano comercial passa a ter
2 vagas, mantendo 1 stream simultaneo.

Revision ID: 006
Revises: 005
Create Date: 2026-11-15

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE plans
        SET description = 'Acesso completo ao catalogo, 2 aparelhos e 1 stream',
            max_devices = 2,
            updated_at = now()
        WHERE max_devices < 2
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE plans
        SET description = 'Acesso completo ao catalogo, 1 aparelho e 1 stream',
            max_devices = 1,
            updated_at = now()
        WHERE max_devices = 2
        """
    )
