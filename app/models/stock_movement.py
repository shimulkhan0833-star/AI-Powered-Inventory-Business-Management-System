from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "product_id"], ["products.business_id", "products.id"]),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(nullable=False)
    product_id: Mapped[int] = mapped_column(nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    quantity_change: Mapped[int] = mapped_column(Integer, nullable=False)
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
