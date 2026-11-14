
import re

from uuid import UUID
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator
)


# ============================================================
# USER REGISTRATION
# ============================================================

class UserCreate(BaseModel):

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone_number: str = Field(min_length=7, max_length=20)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, value):
        value = value.strip()

        if not value:
            raise ValueError("Name cannot be empty")

        return value

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value):
        value = re.sub(r"[\s().-]", "", value.strip())

        if not re.fullmatch(r"\+?\d{7,15}", value):
            raise ValueError(
                "Enter a valid phone number with 7 to 15 digits."
            )

        return value


# ============================================================
# USER RESPONSE
# ============================================================

class UserResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    user_uuid: UUID
    first_name: str
    last_name: str
    phone_number: str | None
    email: EmailStr
    role: str
    created_at: datetime


# ============================================================
# LOGIN
# ============================================================

class UserLogin(BaseModel):

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


# ============================================================
# TOKEN RESPONSE
# ============================================================

class TokenResponse(BaseModel):

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int


class RefreshTokenRequest(BaseModel):

    refresh_token: str = Field(
        min_length=20,
        max_length=512
    )


# ============================================================
# DELETE ACCOUNT
# ============================================================

class UserDeleteRequest(BaseModel):

    current_password: str = Field(
        min_length=1,
        max_length=128
    )


# ============================================================
# FORGOT PASSWORD
# ============================================================

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


# ============================================================
# RESET PASSWORD
# ============================================================

class ResetPasswordRequest(BaseModel):

    token: str = Field(
        min_length=20,
        max_length=256
    )

    new_password: str = Field(
        min_length=8,
        max_length=128
    )


# ============================================================
# CHANGE PASSWORD
# ============================================================

class ChangePasswordRequest(BaseModel):

    current_password: str = Field(
        min_length=1,
        max_length=128
    )

    new_password: str = Field(
        min_length=8,
        max_length=128
    )
