import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.dependencies import SESSION_COOKIE, get_current_user
from app.models import User
from app.schemas.auth import (
    BusinessRegistration, CurrentUserResponse, LoginRequest, RegistrationResponse,
)
from app.services.registration import EmailAlreadyRegistered, register_business
from app.services.sessions import SESSION_SECONDS, authenticate, create_session, revoke_session

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
        business_id=business.business_id,
        user_id=owner.user_id,
        business_name=business.name,
        owner_name=owner.name,
        email=owner.email,
        role=owner.role,
    )


def user_response(user: User) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=user.user_id, business_id=user.business_id, name=user.name,
        email=user.email, role=user.role, must_change_password=user.must_change_password,
    )


@router.post("/login", response_model=CurrentUserResponse)
def login(data: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = authenticate(db, str(data.email), data.password, data.role, data.business_name)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid login details")
    token = create_session(db, user, request.cookies.get(SESSION_COOKIE))
    response.set_cookie(
        key=SESSION_COOKIE, value=token, max_age=SESSION_SECONDS,
        httponly=True, secure=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
        samesite="strict", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return user_response(user)


@router.get("/me", response_model=CurrentUserResponse)
def current_user(response: Response, user: User = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return user_response(user)


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        revoke_session(db, token)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")
    return response
