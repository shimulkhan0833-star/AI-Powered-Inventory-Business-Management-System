"""Product operations and atomic, auditable stock changes."""

import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Product, StockMovement, User
from app.schemas.product import AdjustmentCreate, ProductCreate, ProductUpdate

MAX_STOCK = 2_147_483_647


class ProductNotFound(Exception):
    pass


class DuplicateSKU(Exception):
    pass


class InvalidStock(Exception):
    pass


def get_product(db: Session, business_id: int, product_id: int, *, lock: bool = False) -> Product:
    query = select(Product).where(Product.business_id == business_id, Product.id == product_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    product = db.scalar(query)
    if product is None:
        raise ProductNotFound
    return product


def commit_or_duplicate(db: Session, business_id: int, sku: str, product_id: int | None = None) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_id = db.scalar(select(Product.id).where(Product.business_id == business_id, Product.sku == sku))
        if existing_id is not None and existing_id != product_id:
            raise DuplicateSKU from None
        raise


def create_product(db: Session, owner: User, data: ProductCreate) -> Product:
    sku = data.sku or f"PRD-{secrets.token_hex(6).upper()}"
    product = Product(business_id=owner.business_id, name=data.name, sku=sku,
                      selling_price=data.selling_price, purchase_cost=data.purchase_cost,
                      stock_quantity=data.opening_stock)
    db.add(product)
    try:
        db.flush()
        if data.opening_stock:
            db.add(StockMovement(business_id=owner.business_id, product_id=product.id,
                                 user_id=owner.id, quantity_change=data.opening_stock,
                                 movement_type="opening", reason="Opening stock"))
        commit_or_duplicate(db, owner.business_id, sku)
    except IntegrityError:
        # An SKU conflict can also be raised by flush before commit.
        db.rollback()
        if db.scalar(select(Product.id).where(Product.business_id == owner.business_id, Product.sku == sku)) is not None:
            raise DuplicateSKU from None
        raise
    db.refresh(product)
    return product


def update_product(db: Session, owner: User, product_id: int, data: ProductUpdate) -> Product:
    product = get_product(db, owner.business_id, product_id, lock=True)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    commit_or_duplicate(db, owner.business_id, product.sku, product.id)
    db.refresh(product)
    return product


def adjust_stock(db: Session, owner: User, product_id: int, data: AdjustmentCreate) -> Product:
    # All stock-changing flows must lock this product before reading its balance.
    product = get_product(db, owner.business_id, product_id, lock=True)
    new_quantity = product.stock_quantity + data.quantity_change
    if not 0 <= new_quantity <= MAX_STOCK:
        db.rollback()
        raise InvalidStock
    product.stock_quantity = new_quantity
    db.add(StockMovement(business_id=owner.business_id, product_id=product.id,
                         user_id=owner.id, quantity_change=data.quantity_change,
                         movement_type="adjustment", reason=data.reason))
    db.commit()
    db.refresh(product)
    return product
