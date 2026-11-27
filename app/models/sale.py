from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SalesInvoice(Base):
    __tablename__ = "sales_invoices"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "customer_id"], ["customers.business_id", "customers.customer_id"]),
        UniqueConstraint("business_id", "invoice_id", name="uq_sales_invoices_business_id_id"),
        UniqueConstraint("business_id", "idempotency_key", name="uq_sales_invoices_business_key"),
        Index("ix_sales_invoices_business_customer", "business_id", "customer_id"),
    )

    invoice_id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.business_id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    business_name: Mapped[str] = mapped_column(String(150), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(150), nullable=False)
    salesperson_name: Mapped[str] = mapped_column(String(150), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(36), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class SalesInvoiceItem(Base):
    __tablename__ = "sales_invoice_items"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "invoice_id"], ["sales_invoices.business_id", "sales_invoices.invoice_id"]),
        ForeignKeyConstraint(["business_id", "product_id"], ["products.business_id", "products.product_id"]),
        UniqueConstraint("invoice_id", "product_id", name="uq_sales_item_product"),
        Index("ix_sales_items_business_invoice", "business_id", "invoice_id"),
        Index("ix_sales_items_business_product", "business_id", "product_id"),
    )

    invoice_item_id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(nullable=False)
    invoice_id: Mapped[int] = mapped_column(nullable=False)
    product_id: Mapped[int] = mapped_column(nullable=False)
    product_name: Mapped[str] = mapped_column(String(150), nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "invoice_id"], ["sales_invoices.business_id", "sales_invoices.invoice_id"]),
        UniqueConstraint("business_id", "idempotency_key", name="uq_payments_business_key"),
        Index("ix_payments_business_invoice", "business_id", "invoice_id"),
    )

    payment_id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(nullable=False)
    invoice_id: Mapped[int] = mapped_column(nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
