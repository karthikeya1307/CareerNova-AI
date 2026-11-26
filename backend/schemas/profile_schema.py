
import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

BIO_MAX = 600   # characters: a short professional introduction


def clean_bio_text(value):
    """Plain text: control characters removed, at most two consecutive line breaks, trimmed; empty -> None."""
    if value is None:
        return None
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value.replace("\r\n", "\n"))
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    return value or None


# ============================================================
# CREATE PROFILE
# ============================================================

class ProfileCreate(BaseModel):

    college: str | None = Field(default=None, max_length=200)
    degree: str | None = Field(default=None, max_length=150)
    graduation_year: int | None = Field(
        default=None,
        ge=1900,
        le=2100
    )
    location: str | None = Field(default=None, max_length=150)
    bio: str | None = Field(default=None, max_length=BIO_MAX)

    @field_validator("bio")
    @classmethod
    def clean_bio(cls, value):
        return clean_bio_text(value)

    @field_validator("college", "degree", "location")
    @classmethod
    def clean_text(cls, value):
        if value is None:
            return None

        value = value.strip()
        return value if value else None


# ============================================================
# UPDATE PROFILE
# ============================================================

class ProfileUpdate(BaseModel):

    college: str | None = Field(default=None, max_length=200)
    degree: str | None = Field(default=None, max_length=150)
    graduation_year: int | None = Field(
        default=None,
        ge=1900,
        le=2100
    )
    location: str | None = Field(default=None, max_length=150)
    bio: str | None = Field(default=None, max_length=BIO_MAX)

    @field_validator("bio")
    @classmethod
    def clean_bio(cls, value):
        return clean_bio_text(value)

    @field_validator("college", "degree", "location")
    @classmethod
    def clean_text(cls, value):
        if value is None:
            return None

        value = value.strip()
        return value if value else None


# ============================================================
# PROFILE RESPONSE
# ============================================================

class ProfileResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    profile_id: int
    user_id: int
    college: str | None
    degree: str | None
    graduation_year: int | None
    location: str | None
    bio: str | None = None
    has_avatar: bool = False                  # GET /profiles/me/avatar returns the picture (owner only)
    avatar_updated_at: datetime | None = None
