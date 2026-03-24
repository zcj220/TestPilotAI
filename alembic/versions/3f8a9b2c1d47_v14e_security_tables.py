"""v14e_security_tables

Revision ID: 3f8a9b2c1d47
Revises: f03fbc681fc5
Create Date: 2026-03-24 20:00:00.000000

新增三张安全增强表：
- login_attempts: 登录失败持久化（替代内存字典）
- refresh_tokens: JWT Refresh Token（7天有效）
- email_verifications: 邮箱验证码
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3f8a9b2c1d47'
down_revision: Union[str, Sequence[str], None] = 'f03fbc681fc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('login_attempts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('identifier', sa.String(length=255), nullable=False),
        sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_success', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('login_attempts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_login_attempts_identifier'), ['identifier'], unique=False)
        batch_op.create_index('ix_login_attempts_id_time', ['identifier', 'attempted_at'], unique=False)

    op.create_table('refresh_tokens',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=128), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_revoked', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_refresh_tokens_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_token_hash'), ['token_hash'], unique=True)

    op.create_table('email_verifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('code', sa.String(length=10), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_used', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('email_verifications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_verifications_email'), ['email'], unique=False)


def downgrade() -> None:
    op.drop_table('email_verifications')
    op.drop_table('refresh_tokens')
    with op.batch_alter_table('login_attempts', schema=None) as batch_op:
        batch_op.drop_index('ix_login_attempts_id_time')
        batch_op.drop_index(batch_op.f('ix_login_attempts_identifier'))
    op.drop_table('login_attempts')
