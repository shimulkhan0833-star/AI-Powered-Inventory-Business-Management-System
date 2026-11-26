"""Import models here so Alembic can discover their tables."""

from app.models.business import Business
from app.models.user import User

__all__ = ["Business", "User"]
