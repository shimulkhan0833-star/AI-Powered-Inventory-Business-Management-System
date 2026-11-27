"""Save purchase, lines, and stock movements as one transaction."""

import hashlib
import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Product, Purchase, PurchaseItem, StockMovement, User
from app.schemas.purchase import PurchaseCreate, PurchaseItemResponse, PurchaseResponse
from app.services.products import MAX_STOCK


class PurchaseProductNotFound(Exception):
    pass


class PurchaseStockOverflow(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


def request_digest(data: PurchaseCreate) -> str:
    payload = {
        "supplier_name": data.supplier_name,
        "items": [{"product_id": item.product_id, "quantity": item.quantity,
                   "unit_price": str(item.unit_price.quantize(Decimal("0.01")))}
                  for item in sorted(data.items, key=lambda item: item.product_id)],
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def purchase_response(db: Session, purchase: Purchase) -> PurchaseResponse:
    lines = db.scalars(select(PurchaseItem).where(
        PurchaseItem.business_id == purchase.business_id, PurchaseItem.purchase_id == purchase.id
    ).order_by(PurchaseItem.id)).all()
    return PurchaseResponse(id=purchase.id, supplier_name=purchase.supplier_name,
                            total=purchase.total, user_id=purchase.user_id,
                            created_at=purchase.created_at,
                            items=[PurchaseItemResponse.model_validate(line) for line in lines])


def create_purchase(db: Session, owner: User, data: PurchaseCreate, key: str) -> tuple[PurchaseResponse, bool]:
    business_id = owner.business_id
    user_id = owner.id
    digest = request_digest(data)
    purchase = Purchase(business_id=business_id, user_id=user_id, supplier_name=data.supplier_name,
                        total=sum((line.unit_price * line.quantity for line in data.items), Decimal("0")),
                        idempotency_key=key, request_hash=digest)
    try:
        db.add(purchase)
        # Reserve the key before touching stock, including for concurrent requests.
        db.flush()
        for line in sorted(data.items, key=lambda item: item.product_id):
            product = db.scalar(select(Product).where(
                Product.id == line.product_id, Product.business_id == business_id
            ).with_for_update().execution_options(populate_existing=True))
            if product is None:
                raise PurchaseProductNotFound
            if product.stock_quantity + line.quantity > MAX_STOCK:
                raise PurchaseStockOverflow
            product.stock_quantity += line.quantity
            db.add(PurchaseItem(business_id=business_id, purchase_id=purchase.id,
                                product_id=product.id, quantity=line.quantity, unit_price=line.unit_price))
            db.add(StockMovement(business_id=business_id, product_id=product.id, user_id=user_id,
                                 purchase_id=purchase.id, quantity_change=line.quantity,
                                 movement_type="purchase", reason=f"Purchase #{purchase.id}"))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Purchase).where(Purchase.business_id == business_id, Purchase.idempotency_key == key))
        if existing is None:
            raise
        if existing.request_hash != digest:
            raise IdempotencyConflict from None
        return purchase_response(db, existing), False
    except Exception:
        db.rollback()
        raise
    db.refresh(purchase)
    return purchase_response(db, purchase), True
