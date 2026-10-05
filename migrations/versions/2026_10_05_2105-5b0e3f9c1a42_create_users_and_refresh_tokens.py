"""create users and refresh_tokens

Revision ID: 5b0e3f9c1a42
Revises: d7cd327419d1
Create Date: 2026-10-05 21:05:00.000000

AUTH-001: accounts and server-side refresh token records.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b0e3f9c1a42'
down_revision: Union[str, Sequence[str], None] = 'd7cd327419d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('reader_id', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("(role = 'reader') = (reader_id IS NOT NULL)", name='users_reader_link_check'),
    sa.CheckConstraint("role IN ('reader', 'librarian', 'admin')", name='users_role_check'),
    sa.ForeignKeyConstraint(['reader_id'], ['readers.id'], name='users_reader_id_fkey'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('reader_id', name='users_reader_id_key')
    )
    op.create_index('users_username_lower_key', 'users', [sa.literal_column('lower(username)')], unique=True)
    op.create_table('refresh_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='refresh_tokens_user_id_fkey', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash', name='refresh_tokens_token_hash_key')
    )
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index('users_username_lower_key', table_name='users')
    op.drop_table('users')
