"""Subscription devices: vinculo de aparelhos por assinatura

Revision ID: 002
Revises: 001
Create Date: 2026-11-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("device_name", sa.String(120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id", "device_id", name="uq_subscription_device"),
    )
    op.create_index(
        "ix_subscription_devices_subscription_id",
        "subscription_devices",
        ["subscription_id"],
    )
    op.create_index(
        "idx_subscription_devices_active",
        "subscription_devices",
        ["subscription_id", "revoked_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_subscription_devices_active", table_name="subscription_devices")
    op.drop_index("ix_subscription_devices_subscription_id", table_name="subscription_devices")
    op.drop_table("subscription_devices")
