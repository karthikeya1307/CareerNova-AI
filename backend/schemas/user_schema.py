
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
    is_verified: bool
    created_at: datetime
    # Added in the account-security upgrade (additive; defaults keep old clients working).
    is_active: bool = True
    last_login_at: datetime | None = None


# ============================================================
# ADMIN: CREATE USER (pending account, activated by invitation in Phase 2)
# ============================================================

class AdminUserCreate(BaseModel):

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone_number: str | None = Field(default=None, min_length=7, max_length=20)
    role: str = Field(default="student", min_length=1, max_length=30)
    # Email an activation link straight away (the person sets their own password).
    send_invitation: bool = True

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
        if value is None:
            return value
        value = re.sub(r"[\s().-]", "", value.strip())
        if not re.fullmatch(r"\+?\d{7,15}", value):
            raise ValueError("Enter a valid phone number with 7 to 15 digits.")
        return value

    @field_validator("role")
    @classmethod
    def validate_role(cls, value):
        from backend.utils.roles import ASSIGNABLE_ROLES

        value = value.strip().lower()
        if value not in ASSIGNABLE_ROLES:
            raise ValueError(f"Role must be one of: {', '.join(sorted(ASSIGNABLE_ROLES))}")
        return value


# ============================================================
# ADMIN: AUDIT EVENTS
# ============================================================

class AuditEventResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    event_id: int
    actor_user_id: int | None
    actor_role: str | None
    action: str
    target_user_id: int | None
    target_label: str | None
    details: dict | None
    ip_address: str | None
    created_at: datetime


class AuditEventPage(BaseModel):

    total: int
    skip: int
    limit: int
    items: list[AuditEventResponse]


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
# RESEND VERIFICATION EMAIL
# ============================================================

class ResendVerificationRequest(BaseModel):
    email: EmailStr


# ============================================================
# ADMIN: UPDATE USER ROLE
# ============================================================

class RoleUpdateRequest(BaseModel):

    role: str = Field(min_length=1, max_length=30)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value):
        from backend.utils.roles import VALID_ROLES

        value = value.strip().lower()

        if value not in VALID_ROLES:
            raise ValueError(
                f"Role must be one of: {', '.join(sorted(VALID_ROLES))}"
            )

        return value


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


# ============================================================
# INVITATIONS (Phase 2)
# ============================================================

class InvitationSummary(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    invitation_id: int
    status: str                     # pending | accepted | expired | revoked
    delivery_status: str            # pending | sent | outboxed | skipped | failed
    delivery_error: str | None = None
    created_at: datetime
    expires_at: datetime


class AdminUserResponse(UserResponse):
    """UserResponse plus the latest invitation (additive; None when never invited)."""

    invitation: InvitationSummary | None = None


class InvitationListItem(InvitationSummary):

    user_id: int
    email: EmailStr
    first_name: str
    last_name: str
    invited_by_user_id: int | None = None


class InvitationTokenRequest(BaseModel):

    token: str = Field(min_length=20, max_length=256)


class InvitationCheckResponse(BaseModel):

    email: EmailStr
    first_name: str
    last_name: str
    expires_at: datetime


class AcceptInvitationRequest(BaseModel):

    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value):
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password must contain at least one letter and one number.")
        return value


class EmailDeliveryItem(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    delivery_id: int
    kind: str
    recipient: EmailStr | str
    status: str
    error_code: str | None
    user_id: int | None
    invitation_id: int | None
    created_at: datetime
    sent_at: datetime | None
