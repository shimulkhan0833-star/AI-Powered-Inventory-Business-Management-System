from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Purchase(Base):
    __tablename__ = "purchases"
    __table_args__ = (
        UniqueConstraint("business_id", "idempotency_key", name="uq_purchases_business_key"),
        UniqueConstraint("business_id", "id", name="uq_purchases_business_id_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    supplier_name: Mapped[str | None] = mapped_column(String(150))
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


class PurchaseItem(Base):
    __tablename__ = "purchase_items"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "purchase_id"], ["purchases.business_id", "purchases.id"]),
        ForeignKeyConstraint(["business_id", "product_id"], ["products.business_id", "products.id"]),
        UniqueConstraint("purchase_id", "product_id", name="uq_purchase_item_product"),
        Index("ix_purchase_items_business_purchase", "business_id", "purchase_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(nullable=False)
    purchase_id: Mapped[int] = mapped_column(nullable=False)
    product_id: Mapped[int] = mapped_column(nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
