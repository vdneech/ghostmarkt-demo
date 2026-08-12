"""create_orders

Revision ID: 0003_orders
Revises: 0002_products

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003_orders'
down_revision: Union[str, Sequence[str], None] = '0002_products'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create orders table
    op.create_table('orders',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('payment_status', sa.Enum('PENDING', 'PAID', 'FAILED', 'CANCELED', name='payment_status', native_enum=False), nullable=False, default='PENDING'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payment_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('address', sa.String(length=256), nullable=True),
        sa.Column('telegram_message_id', sa.BigInteger(), nullable=True),
        sa.Column('payment_url', sa.String(length=256), nullable=True),
        sa.Column('promo_code', sa.String(length=64), nullable=True),
        sa.Column('discount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('delivery', sa.Enum('CDEK', 'RUSSIAN_POST', 'URBAN', name='delivery', native_enum=False), nullable=False, default='CDEK'),
        sa.Column('delivery_point', sa.String(length=255), nullable=True),
        sa.Column('tariff_code', sa.Integer(), nullable=True),
        sa.Column('delivery_id', sa.UUID(), nullable=True),
        sa.Column('delivery_code', sa.String(length=255), nullable=True),
        sa.Column('shipment_cost', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_orders_user_id'), 'orders', ['user_id'], unique=False)
    op.create_index(op.f('ix_orders_payment_status'), 'orders', ['payment_status'], unique=False)
    op.create_index(op.f('ix_orders_created_at'), 'orders', ['created_at'], unique=False)

    # 2. Create order_items table
    op.create_table('order_items',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, default=1),
        sa.Column('price_at_purchase', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_order_items_order_id'), 'order_items', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_items_product_id'), 'order_items', ['product_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_order_items_product_id'), table_name='order_items')
    op.drop_index(op.f('ix_order_items_order_id'), table_name='order_items')
    op.drop_table('order_items')
    op.drop_index(op.f('ix_orders_created_at'), table_name='orders')
    op.drop_index(op.f('ix_orders_payment_status'), table_name='orders')
    op.drop_index(op.f('ix_orders_user_id'), table_name='orders')
    op.drop_table('orders')
