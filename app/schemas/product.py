from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
SKU = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]
Quantity = Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]
Change = Annotated[int, Field(strict=True, ge=-2_147_483_647, le=2_147_483_647)]


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    sku: SKU | None = None
    selling_price: Money
    purchase_cost: Money | None = None
    opening_stock: Quantity = 0


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    sku: SKU | None = None
    selling_price: Money | None = None
    purchase_cost: Money | None = None

    @field_validator("name", "sku", "selling_price", mode="before")
    @classmethod
    def required_fields_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class AdjustmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity_change: Change
    reason: Reason

    @field_validator("quantity_change")
    @classmethod
    def nonzero_change(cls, value: int) -> int:
        if value == 0:
            raise ValueError("Quantity change cannot be zero")
        return value


class PublicProduct(BaseModel):
    product_id: int
    name: str
    sku: str
    selling_price: Decimal
    stock_quantity: int


class OwnerProduct(PublicProduct):
    purchase_cost: Decimal | None


class PublicMovement(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    movement_id: int
    product_id: int
    user_id: int
    quantity_change: int
    movement_type: str
    created_at: datetime


class MovementResponse(PublicMovement):
    reason: str
