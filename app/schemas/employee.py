from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.auth import Name


class EmployeeCreate(BaseModel):
    name: Name
    email: EmailStr
    password: str = Field(min_length=8, max_length=128, repr=False)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.lower()
        if len(value) > 255:
            raise ValueError("Email must be at most 255 characters")
        return value


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
    is_active: bool
