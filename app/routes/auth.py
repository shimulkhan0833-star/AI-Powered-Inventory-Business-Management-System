from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.auth import BusinessRegistration, RegistrationResponse
from app.services.registration import EmailAlreadyRegistered, register_business

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=RegistrationResponse, status_code=201)
def register(data: BusinessRegistration, db: Session = Depends(get_db)):
    try:
        business, owner = register_business(db, data)
    except EmailAlreadyRegistered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from None
    return RegistrationResponse(
        business_id=business.id,
        user_id=owner.id,
        business_name=business.name,
        owner_name=owner.name,
        email=owner.email,
        role=owner.role,
    )
