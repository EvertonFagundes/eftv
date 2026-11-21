"""Trial por aparelho, refresh revogavel, linhas proprias e rate limit

Fecha os furos de receita que sobraram da primeira rodada:

* ``trial_devices``: um aparelho so ganha teste gratis uma vez (antes bastava
  criar outra conta no mesmo celular);
* ``refresh_tokens``: permite revogar sessao de verdade no logout e na
  rotacao;
* ``subscriptions.provider_playlist_url``: linha propria no provedor de IPTV,
  revogavel por assinante (antes todos usavam a mesma URL);
* ``rate_limit_counters``: contador no banco, por identidade, em vez de um
  balde em memoria por IP;
* ``subscriptions.trial_expired_notified_at``: aviso de fim de teste.

Revision ID: 007
Revises: 006
Create Date: 2026-11-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trial_devices",
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("device_id"),
    )
    op.create_index("ix_trial_devices_user_id", "trial_devices", ["user_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("jti", sa.String(64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("jti"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index(
        "idx_refresh_tokens_user_active", "refresh_tokens", ["user_id", "revoked_at"]
    )
    op.create_index("idx_refresh_tokens_expires", "refresh_tokens", ["expires_at"])

    op.create_table(
        "rate_limit_counters",
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column(
            "window_start",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("key"),
    )

    op.add_column(
        "subscriptions",
        sa.Column("provider_playlist_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("provider_revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("trial_expired_notified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "trial_expired_notified_at")
    op.drop_column("subscriptions", "provider_revoked_at")
    op.drop_column("subscriptions", "provider_playlist_url")
    op.drop_table("rate_limit_counters")
    op.drop_index("idx_refresh_tokens_expires", table_name="refresh_tokens")
    op.drop_index("idx_refresh_tokens_user_active", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_trial_devices_user_id", table_name="trial_devices")
    op.drop_table("trial_devices")
