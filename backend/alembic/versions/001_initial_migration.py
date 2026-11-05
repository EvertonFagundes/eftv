"""Initial migration: users, plans, subscriptions, payments, categories, channels, playback_sessions

Revision ID: 001
Revises: 
Create Date: 2026-11-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=True),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )
    op.create_index('ix_users_email_active', 'users', ['email', 'is_active'])

    # plans
    op.create_table(
        'plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('price_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='BRL'),
        sa.Column('interval', sa.String(20), nullable=False, server_default='month'),
        sa.Column('max_simultaneous_streams', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('max_devices', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('features', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('mercadopago_plan_id', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('mercadopago_plan_id'),
    )
    op.create_index('ix_plans_active_sort', 'plans', ['is_active', 'sort_order'])

    # subscriptions
    op.create_table(
        'subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('plan_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('mercadopago_subscription_id', sa.String(100), nullable=True),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('trial_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('auto_renew', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('mercadopago_subscription_id'),
    )
    op.create_index('idx_subscriptions_user_status', 'subscriptions', ['user_id', 'status'])
    op.create_index('idx_subscriptions_mp_id', 'subscriptions', ['mercadopago_subscription_id'])

    # payments
    op.create_table(
        'payments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('subscription_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('plan_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('mercadopago_payment_id', sa.String(100), nullable=True),
        sa.Column('mercadopago_preference_id', sa.String(100), nullable=True),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='BRL'),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('payment_method', sa.String(50), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('mercadopago_payment_id'),
    )
    op.create_index('idx_payments_user', 'payments', ['user_id'])
    op.create_index('idx_payments_mp_id', 'payments', ['mercadopago_payment_id'])
    op.create_index('idx_payments_status_created', 'payments', ['status', 'created_at'])

    # categories
    op.create_table(
        'categories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('slug', sa.String(50), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('icon', sa.String(10), nullable=True),
        sa.Column('color', sa.String(7), nullable=True),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_adult', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_index('idx_categories_active_sort', 'categories', ['is_active', 'sort_order'])

    # channels
    op.create_table(
        'channels',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('group_title', sa.String(255), nullable=True),
        sa.Column('logo_url', sa.Text(), nullable=True),
        sa.Column('is_live', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_adult', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('stream_url', sa.Text(), nullable=True),
        sa.Column('stream_type', sa.String(20), nullable=True),
        sa.Column('backup_stream_url', sa.Text(), nullable=True),
        sa.Column('backup_stream_type', sa.String(20), nullable=True),
        sa.Column('drm_protected', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('drm_license_url', sa.Text(), nullable=True),
        sa.Column('current_program_title', sa.String(255), nullable=True),
        sa.Column('current_program_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_program_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_program_description', sa.Text(), nullable=True),
        sa.Column('next_program_title', sa.String(255), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_index('idx_channels_category_active', 'channels', ['category_id', 'is_active'])
    op.create_index('idx_channels_slug', 'channels', ['slug'])
    op.create_index('idx_channels_active_live', 'channels', ['is_active', 'is_live'])

    # playback_sessions
    op.create_table(
        'playback_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subscription_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('device_fingerprint', sa.String(255), nullable=True),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('token_jti', sa.String(255), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_heartbeat', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_jti'),
    )
    op.create_index('idx_playback_sessions_user_active', 'playback_sessions', ['user_id', 'ended_at'], postgresql_where=sa.text('ended_at IS NULL'))
    op.create_index('idx_playback_sessions_token', 'playback_sessions', ['token_jti'])
    op.create_index('idx_playback_sessions_channel_active', 'playback_sessions', ['channel_id', 'ended_at'], postgresql_where=sa.text('ended_at IS NULL'))


def downgrade() -> None:
    op.drop_table('playback_sessions')
    op.drop_table('channels')
    op.drop_table('categories')
    op.drop_table('payments')
    op.drop_table('subscriptions')
    op.drop_table('plans')
    op.drop_table('users')