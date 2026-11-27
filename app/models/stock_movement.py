from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "product_id"], ["products.business_id", "products.product_id"]),
        ForeignKeyConstraint(["business_id", "purchase_id"], ["purchases.business_id", "purchases.purchase_id"],
                             name="fk_stock_movement_purchase"),
        ForeignKeyConstraint(["business_id", "invoice_id"], ["sales_invoices.business_id", "sales_invoices.invoice_id"],
                             name="fk_stock_movement_sale"),
    )

    movement_id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(nullable=False)
    product_id: Mapped[int] = mapped_column(nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    purchase_id: Mapped[int | None] = mapped_column(nullable=True)
    invoice_id: Mapped[int | None] = mapped_column(nullable=True)
    quantity_change: Mapped[int] = mapped_column(Integer, nullable=False)
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
