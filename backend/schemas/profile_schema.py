
from pydantic import BaseModel, ConfigDict, Field, field_validator


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
