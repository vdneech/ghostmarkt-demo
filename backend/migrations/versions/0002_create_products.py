"""create_products

Revision ID: 0002_products
Revises: 0001_auth

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002_products'
down_revision: Union[str, Sequence[str], None] = '0001_auth'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create products table
    op.create_table('products',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('name_en', sa.String(length=128), nullable=True),
        sa.Column('description', sa.String(length=512), nullable=True),
        sa.Column('description_en', sa.String(length=512), nullable=True),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False, default=0),
        sa.Column('weight', sa.Integer(), nullable=False, default=1),
        sa.Column('length', sa.Integer(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('quantity >= 0', name='ck_products_quantity_nonnegative'),
        sa.CheckConstraint('weight >= 0', name='ck_products_weight_nonnegative')
    )
    op.create_index(op.f('ix_products_is_active'), 'products', ['is_active'], unique=False)

    # 2. Create product_images table
    op.create_table('product_images',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('path', sa.String(length=128), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_product_images_product_id'), 'product_images', ['product_id'], unique=False)

    # 3. Create product_videos table
    op.create_table('product_videos',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('path', sa.String(length=128), nullable=False),
        sa.Column('description', sa.String(length=256), nullable=True),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_product_videos_product_id'), 'product_videos', ['product_id'], unique=False)

    # 4. Create promocodes table
    op.create_table('promocodes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('max_usages', sa.Integer(), nullable=True),
        sa.Column('usages_count', sa.Integer(), nullable=False, default=0),
        sa.Column('discount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('discount_percent', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            '(discount IS NOT NULL AND discount_percent IS NULL) OR (discount IS NULL AND discount_percent IS NOT NULL)',
            name='ck_promocode_discount_xor'
        )
    )
    op.create_index(op.f('ix_promocodes_code'), 'promocodes', ['code'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_promocodes_code'), table_name='promocodes')
    op.drop_table('promocodes')
    op.drop_index(op.f('ix_product_videos_product_id'), table_name='product_videos')
    op.drop_table('product_videos')
    op.drop_index(op.f('ix_product_images_product_id'), table_name='product_images')
    op.drop_table('product_images')
    op.drop_index(op.f('ix_products_is_active'), table_name='products')
    op.drop_table('products')
