"""Rename identifier columns without changing their values.

Revision ID: 9a4f2b7d31c0
Revises: 453cf5f0e0f2
"""

from alembic import op

revision = "9a4f2b7d31c0"
down_revision = "453cf5f0e0f2"
branch_labels = None
depends_on = None

RENAMES = (
    ("businesses", "id", "business_id"),
    ("users", "id", "user_id"),
    ("login_sessions", "id", "session_id"),
    ("customers", "id", "customer_id"),
    ("products", "id", "product_id"),
    ("purchases", "id", "purchase_id"),
    ("purchase_items", "id", "purchase_item_id"),
    ("sales_invoices", "id", "invoice_id"),
    ("sales_invoice_items", "id", "invoice_item_id"),
    ("payments", "id", "payment_id"),
    ("stock_movements", "id", "movement_id"),
    ("stock_movements", "sales_invoice_id", "invoice_id"),
)


def rename(table: str, old: str, new: str) -> None:
    dialect = op.get_context().dialect.name
    if dialect == "mysql":
        # MySQL requires INPLACE when another table references the column.
        op.execute(f"ALTER TABLE `{table}` RENAME COLUMN `{old}` TO `{new}`, ALGORITHM=INPLACE")
    else:
        op.execute(f'ALTER TABLE "{table}" RENAME COLUMN "{old}" TO "{new}"')


def upgrade() -> None:
    for table, old, new in RENAMES:
        rename(table, old, new)


def downgrade() -> None:
    for table, old, new in reversed(RENAMES):
        rename(table, new, old)
