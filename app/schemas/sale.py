from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_serializer, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Amount = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2, allow_inf_nan=False)]


class CustomerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    phone: Phone | None = None


class CustomerResponse(BaseModel):
    customer_id: int
    name: str
    phone: str | None
    due: Decimal


class SaleLineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(strict=True, gt=0)
    quantity: int = Field(strict=True, gt=0, le=2_147_483_647)


class SaleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: int = Field(strict=True, gt=0)
    items: list[SaleLineCreate] = Field(min_length=1, max_length=100)
    initial_payment: Amount = Decimal("0")

    @model_validator(mode="after")
    def unique_products(self):
        ids = [line.product_id for line in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Each product may appear only once")
        return self


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Amount = Field(gt=0)


class UtcResponse(BaseModel):
    @field_serializer("created_at", check_fields=False)
    def serialize_utc(self, value: datetime) -> str:
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class SaleItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: int
    product_name: str
    sku: str
    quantity: int
    unit_price: Decimal


class PaymentResponse(UtcResponse):
    model_config = ConfigDict(from_attributes=True)
    payment_id: int
    invoice_id: int
    customer_payment_id: int | None = None
    user_id: int
    amount: Decimal
    created_at: datetime


class CustomerPaymentResponse(UtcResponse):
    customer_payment_id: int
    customer_id: int
    amount: Decimal
    created_at: datetime
    allocations: list[PaymentResponse]


class SaleResponse(UtcResponse):
    invoice_id: int
    business_id: int
    business_name: str
    customer_id: int
    customer_name: str
    user_id: int
    salesperson_name: str
    created_at: datetime
    total: Decimal
    paid: Decimal
    due: Decimal
    items: list[SaleItemResponse]
    payments: list[PaymentResponse]


class CustomerHistoryResponse(BaseModel):
    customer: CustomerResponse
    sales: list[SaleResponse]
