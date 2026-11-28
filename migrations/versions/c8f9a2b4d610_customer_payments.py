"""Add customer payments and link their invoice allocations.

Revision ID: c8f9a2b4d610
Revises: b7e38c24af01
"""
from alembic import op
import sqlalchemy as sa

revision = "c8f9a2b4d610"
down_revision = "b7e38c24af01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_payments",
        sa.Column("customer_payment_id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("idempotency_key", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["business_id", "customer_id"], ["customers.business_id", "customers.customer_id"]),
        sa.UniqueConstraint("business_id", "customer_payment_id", name="uq_customer_payments_business_id"),
        sa.UniqueConstraint("business_id", "idempotency_key", name="uq_customer_payments_business_key"),
    )
    op.add_column("payments", sa.Column("customer_payment_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_payments_customer_payment", "payments", "customer_payments", ["business_id", "customer_payment_id"], ["business_id", "customer_payment_id"])


def downgrade():
    op.drop_constraint("fk_payments_customer_payment", "payments", type_="foreignkey")
    op.drop_column("payments", "customer_payment_id")
    op.drop_table("customer_payments")
