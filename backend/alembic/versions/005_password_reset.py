"""Recuperacao de senha por codigo enviado por email

Revision ID: 005
Revises: 004
Create Date: 2026-11-13

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_expires_at TIMESTAMPTZ"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_users_password_reset_token "
        "ON users (password_reset_token)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_password_reset_token")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_reset_expires_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_reset_token")
