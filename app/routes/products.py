from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_owner
from app.database import get_db
from app.models import Product, ProductImage, StockMovement, User
from app.schemas.product import AdjustmentCreate, MovementResponse, OwnerProduct, ProductCreate, ProductUpdate, PublicMovement, PublicProduct
from app.services.products import DuplicateSKU, InvalidStock, ProductNotFound, adjust_stock, create_product, get_product, update_product

router = APIRouter(prefix="/products", tags=["Products and stock"])


def visible_product(product: Product, user: User, has_image: bool = False) -> OwnerProduct | PublicProduct:
    values = dict(product_id=product.product_id, name=product.name, sku=product.sku,
                  selling_price=product.selling_price, stock_quantity=product.stock_quantity, has_image=has_image)
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
    products = db.scalars(select(Product).where(Product.business_id == user.business_id).order_by(Product.product_id)).all()
    image_ids = set(db.scalars(select(ProductImage.product_id).join(Product).where(Product.business_id == user.business_id)).all())
    return [visible_product(product, user, product.product_id in image_ids) for product in products]


@router.get("/{product_id}", response_model=OwnerProduct | PublicProduct)
def read_product(product_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        product = get_product(db, user.business_id, product_id)
        has_image = db.scalar(select(ProductImage.product_id).where(ProductImage.product_id == product_id)) is not None
        return visible_product(product, user, has_image)
    except ProductNotFound:
        raise HTTPException(status_code=404, detail="Product not found") from None


@router.patch("/{product_id}", response_model=OwnerProduct)
def edit_product(product_id: int, data: ProductUpdate, owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    try:
        product = update_product(db, owner, product_id, data)
        has_image = db.scalar(select(ProductImage.product_id).where(ProductImage.product_id == product_id)) is not None
        return visible_product(product, owner, has_image)
    except ProductNotFound:
        raise HTTPException(status_code=404, detail="Product not found") from None
    except DuplicateSKU:
        raise HTTPException(status_code=409, detail="SKU already exists for this business") from None


@router.put("/{product_id}/image", status_code=204)
async def upload_product_image(product_id: int, file: UploadFile = File(...), owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    try:
        get_product(db, owner.business_id, product_id, lock=True)
    except ProductNotFound:
        raise HTTPException(status_code=404, detail="Product not found") from None
    content = await file.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be 2 MB or smaller")
    try:
        with Image.open(BytesIO(content)) as image:
            content_type = {"JPEG": "image/jpeg", "PNG": "image/png"}.get(image.format)
            if not content_type or image.width * image.height > 25_000_000:
                raise ValueError("Unsupported image")
            image.verify()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise HTTPException(status_code=400, detail="Upload a valid JPEG or PNG image") from None
    image_record = db.get(ProductImage, product_id)
    if image_record is None:
        image_record = ProductImage(product_id=product_id, content_type=content_type, content=content)
        db.add(image_record)
    else:
        image_record.content_type = content_type
        image_record.content = content
    db.commit()
    return Response(status_code=204)


@router.get("/{product_id}/image")
def read_product_image(product_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        get_product(db, user.business_id, product_id)
    except ProductNotFound:
        raise HTTPException(status_code=404, detail="Product not found") from None
    image = db.get(ProductImage, product_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Product image not found")
    return Response(content=image.content, media_type=image.content_type,
                    headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/{product_id}/adjustments", response_model=OwnerProduct)
def add_adjustment(product_id: int, data: AdjustmentCreate, owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    try:
        product = adjust_stock(db, owner, product_id, data)
        has_image = db.scalar(select(ProductImage.product_id).where(ProductImage.product_id == product_id)) is not None
        return visible_product(product, owner, has_image)
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
    ).order_by(StockMovement.movement_id)).all()
    model = MovementResponse if user.role == "owner" else PublicMovement
    return [model.model_validate(movement) for movement in movements]


@router.get("/{product_id}/stock")
def read_stock(product_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        product = get_product(db, user.business_id, product_id)
    except ProductNotFound:
        raise HTTPException(status_code=404, detail="Product not found") from None
    return {"product_id": product.product_id, "stock_quantity": product.stock_quantity}
