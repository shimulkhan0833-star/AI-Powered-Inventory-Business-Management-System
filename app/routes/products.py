from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_owner
from app.database import get_db
from app.models import Product, StockMovement, User
from app.schemas.product import AdjustmentCreate, MovementResponse, OwnerProduct, ProductCreate, ProductUpdate, PublicMovement, PublicProduct
from app.services.products import DuplicateSKU, InvalidStock, ProductNotFound, adjust_stock, create_product, get_product, update_product

router = APIRouter(prefix="/products", tags=["Products and stock"])


def visible_product(product: Product, user: User) -> OwnerProduct | PublicProduct:
    values = dict(id=product.id, name=product.name, sku=product.sku,
                  selling_price=product.selling_price, stock_quantity=product.stock_quantity)
    if user.role == "owner":
        return OwnerProduct(**values, purchase_cost=product.purchase_cost)
    return PublicProduct(**values)


@router.post("", response_model=OwnerProduct, status_code=201)
def add_product(data: ProductCreate, owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    try:
        return visible_product(create_product(db, owner, data), owner)
    except DuplicateSKU:
        raise HTTPException(status_code=409, detail="SKU already exists for this business") from None


@router.get("", response_model=list[OwnerProduct | PublicProduct])
def list_products(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    products = db.scalars(select(Product).where(Product.business_id == user.business_id).order_by(Product.id)).all()
    return [visible_product(product, user) for product in products]


@router.get("/{product_id}", response_model=OwnerProduct | PublicProduct)
def read_product(product_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return visible_product(get_product(db, user.business_id, product_id), user)
    except ProductNotFound:
        raise HTTPException(status_code=404, detail="Product not found") from None


@router.patch("/{product_id}", response_model=OwnerProduct)
def edit_product(product_id: int, data: ProductUpdate, owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    try:
        return visible_product(update_product(db, owner, product_id, data), owner)
    except ProductNotFound:
        raise HTTPException(status_code=404, detail="Product not found") from None
    except DuplicateSKU:
        raise HTTPException(status_code=409, detail="SKU already exists for this business") from None


@router.post("/{product_id}/adjustments", response_model=OwnerProduct)
def add_adjustment(product_id: int, data: AdjustmentCreate, owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    try:
        return visible_product(adjust_stock(db, owner, product_id, data), owner)
    except ProductNotFound:
        raise HTTPException(status_code=404, detail="Product not found") from None
    except InvalidStock:
        raise HTTPException(status_code=409, detail="Adjustment would produce an invalid stock quantity") from None


@router.get("/{product_id}/history", response_model=list[MovementResponse | PublicMovement])
def stock_history(product_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        get_product(db, user.business_id, product_id)
    except ProductNotFound:
        raise HTTPException(status_code=404, detail="Product not found") from None
    movements = db.scalars(select(StockMovement).where(
        StockMovement.business_id == user.business_id, StockMovement.product_id == product_id
    ).order_by(StockMovement.id)).all()
    model = MovementResponse if user.role == "owner" else PublicMovement
    return [model.model_validate(movement) for movement in movements]


@router.get("/{product_id}/stock")
def read_stock(product_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        product = get_product(db, user.business_id, product_id)
    except ProductNotFound:
        raise HTTPException(status_code=404, detail="Product not found") from None
    return {"product_id": product.id, "stock_quantity": product.stock_quantity}
