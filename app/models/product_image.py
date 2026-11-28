from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductImage(Base):
    __tablename__ = "product_images"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary().with_variant(MEDIUMBLOB(), "mysql"), nullable=False)
