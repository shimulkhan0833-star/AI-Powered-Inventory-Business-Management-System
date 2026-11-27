from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import require_owner
from app.database import get_db
from app.models import Purchase, User
from app.schemas.purchase import MemoDraft, PurchaseCreate, PurchaseResponse
from app.services.memo import MemoUnavailable, extract_memo
from app.services.purchases import (IdempotencyConflict, PurchaseProductNotFound,
                                    PurchaseStockOverflow, create_purchase, purchase_response)

router = APIRouter(prefix="/purchases", tags=["Purchases"])
MAX_IMAGE_BYTES = 5 * 1024 * 1024


@router.post("/memo-draft", response_model=MemoDraft)
async def memo_draft(file: UploadFile = File(...), owner: User = Depends(require_owner)):
    try:
        image = await file.read(MAX_IMAGE_BYTES + 1)
    finally:
        await file.close()
    if len(image) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 5 MB or smaller")
    if file.content_type == "image/png" and image.startswith(b"\x89PNG\r\n\x1a\n"):
        content_type = "image/png"
    elif file.content_type == "image/jpeg" and image.startswith(b"\xff\xd8\xff"):
        content_type = "image/jpeg"
    else:
        raise HTTPException(status_code=400, detail="Upload a PNG or JPEG image")
    try:
        return await run_in_threadpool(extract_memo, image, content_type)
    except MemoUnavailable:
        raise HTTPException(status_code=503, detail="AI extraction unavailable. Enter the purchase manually.") from None


@router.post("", response_model=PurchaseResponse, status_code=201)
def add_purchase(data: PurchaseCreate, response: Response, idempotency_key: UUID = Header(...),
                 owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    try:
        purchase, created = create_purchase(db, owner, data, str(idempotency_key))
    except PurchaseProductNotFound:
        raise HTTPException(status_code=404, detail="Product not found") from None
    except PurchaseStockOverflow:
        raise HTTPException(status_code=409, detail="Purchase would exceed maximum stock") from None
    except IdempotencyConflict:
        raise HTTPException(status_code=409, detail="Idempotency key already used for a different purchase") from None
    if not created:
        response.status_code = 200
    return purchase


@router.get("", response_model=list[PurchaseResponse])
def list_purchases(owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    purchases = db.scalars(select(Purchase).where(Purchase.business_id == owner.business_id).order_by(Purchase.purchase_id.desc())).all()
    return [purchase_response(db, purchase) for purchase in purchases]


@router.get("/{purchase_id}", response_model=PurchaseResponse)
def get_purchase(purchase_id: int, owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    purchase = db.scalar(select(Purchase).where(Purchase.purchase_id == purchase_id, Purchase.business_id == owner.business_id))
    if purchase is None:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return purchase_response(db, purchase)
