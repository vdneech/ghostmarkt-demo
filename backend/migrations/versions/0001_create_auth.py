"""create_auth

Revision ID: 0001_auth
Revises: None

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001_auth'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create Enum type for Locale
    locale_enum = sa.Enum('RU', 'EN', name='locale')
    
    op.create_table('users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('telegram_chat_id', sa.BigInteger(), autoincrement=False, nullable=True),
        sa.Column('username', sa.String(length=32), nullable=True),
        sa.Column('email', sa.String(length=64), nullable=True),
        sa.Column('first_name', sa.String(length=64), nullable=True),
        sa.Column('middle_name', sa.String(length=64), nullable=True),
        sa.Column('last_name', sa.String(length=64), nullable=True),
        sa.Column('source', sa.String(length=64), nullable=True),
        sa.Column('specialty', sa.String(length=128), nullable=True),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, default=False),
        sa.Column('locale', locale_enum, nullable=False, default='RU'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_telegram_chat_id'), 'users', ['telegram_chat_id'], unique=True)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_phone'), 'users', ['phone'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_phone'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_telegram_chat_id'), table_name='users')
    op.drop_table('users')
    
    # Drop Enum type
    sa.Enum(name='locale').drop(op.get_bind(), checkfirst=True)
