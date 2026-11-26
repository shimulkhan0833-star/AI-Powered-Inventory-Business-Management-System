from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class BusinessRegistration(BaseModel):
    business_name: Name
    owner_name: Name
    email: EmailStr
    password: str = Field(min_length=8, max_length=128, repr=False)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.lower()
        if len(normalized) > 255:
            raise ValueError("Email must be at most 255 characters")
        return normalized


class RegistrationResponse(BaseModel):
    business_id: int
    user_id: int
    business_name: str
    owner_name: str
    email: str
    role: str
