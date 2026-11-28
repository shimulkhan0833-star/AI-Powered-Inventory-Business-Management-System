"""Store optional product images.

Revision ID: b7e38c24af01
Revises: 9a4f2b7d31c0
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMBLOB

revision = "b7e38c24af01"
down_revision = "9a4f2b7d31c0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_images",
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.product_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("content_type", sa.String(20), nullable=False),
        sa.Column("content", sa.LargeBinary().with_variant(MEDIUMBLOB(), "mysql"), nullable=False),
    )


def downgrade():
    op.drop_table("product_images")
