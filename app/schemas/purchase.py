from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.product import Money

Supplier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class PurchaseLineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(strict=True, gt=0)
    quantity: int = Field(strict=True, gt=0, le=2_147_483_647)
    unit_price: Money


class PurchaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_name: Supplier | None = None
    items: list[PurchaseLineCreate] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_items(self):
        ids = [line.product_id for line in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Each product may appear only once")
        if sum((line.unit_price * line.quantity for line in self.items), Decimal("0")) > Decimal("9999999999999999.99"):
            raise ValueError("Purchase total is too large")
        return self


class PurchaseItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: int
    quantity: int
    unit_price: Decimal


class PurchaseResponse(BaseModel):
    purchase_id: int
    supplier_name: str | None
    total: Decimal
    user_id: int
    created_at: datetime
    items: list[PurchaseItemResponse]


class MemoItem(BaseModel):
    product_name: str | None = None
    quantity: str | None = None
    unit_price: str | None = None


class MemoDraft(BaseModel):
    supplier_name: str | None = None
    items: list[MemoItem] = Field(default_factory=list, max_length=100)
    note: str = "AI draft only. Review every field and select matching products before saving."
