from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Business, User
from app.schemas.auth import BusinessRegistration


class EmailAlreadyRegistered(Exception):
    """A user already exists with this email address."""


def register_business(db: Session, data: BusinessRegistration) -> tuple[Business, User]:
    email = str(data.email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise EmailAlreadyRegistered

    password_hash = hash_password(data.password)
    try:
        business = Business(name=data.business_name)
        db.add(business)
        db.flush()
        owner = User(
            business_id=business.id,
            name=data.owner_name,
            email=email,
            password_hash=password_hash,
            role="owner",
        )
        db.add(owner)
        db.flush()
        db.commit()
    except IntegrityError:
        db.rollback()
        # The unique constraint also handles concurrent registrations.
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            raise EmailAlreadyRegistered from None
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(business)
    db.refresh(owner)
    return business, owner
