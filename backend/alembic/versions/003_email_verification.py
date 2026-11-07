"""Email verification: token e expiracao no usuario

Adiciona as colunas usadas pelo fluxo de verificacao de email. Contas que ja
existiam antes desse recurso sao marcadas como verificadas para nao perderem
o acesso ao conteudo.

Revision ID: 003
Revises: 002
Create Date: 2026-11-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    already_exists = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'email_verification_token'"
        )
    ).first()

    # IF NOT EXISTS deixa a migration segura caso o app ja tenha criado as
    # colunas no startup (safety net em database.init_db).
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verification_token VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "email_verification_expires_at TIMESTAMPTZ"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_users_email_verification_token "
        "ON users (email_verification_token)"
    )

    if already_exists is None:
        # Primeira vez que o recurso roda: contas existentes foram criadas
        # antes da verificacao por email, entao seguem com acesso liberado.
        op.execute("UPDATE users SET email_verified = true")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_email_verification_token")
    op.execute(
        "ALTER TABLE users DROP COLUMN IF EXISTS email_verification_expires_at"
    )
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email_verification_token")
