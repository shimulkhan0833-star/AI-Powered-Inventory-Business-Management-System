"""Create and verify opaque, revocable login sessions."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models import LoginSession, User

SESSION_SECONDS = 8 * 60 * 60


def utc_now() -> datetime:
    # MySQL DATETIME stores a timezone-naive value; all values here are UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return None
    return user


def create_session(db: Session, user: User, previous_token: str | None = None) -> str:
    token = secrets.token_urlsafe(32)
    if previous_token:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == token_digest(previous_token)))
    db.add(LoginSession(
        user_id=user.id,
        token_hash=token_digest(token),
        expires_at=utc_now() + timedelta(seconds=SESSION_SECONDS),
    ))
    db.commit()
    return token


def user_for_token(db: Session, token: str) -> User | None:
    return db.scalar(
        select(User)
        .join(LoginSession, LoginSession.user_id == User.id)
        .where(
            LoginSession.token_hash == token_digest(token),
            LoginSession.expires_at > utc_now(),
            User.is_active.is_(True),
        )
    )


def revoke_session(db: Session, token: str) -> None:
    db.execute(delete(LoginSession).where(LoginSession.token_hash == token_digest(token)))
    db.commit()
