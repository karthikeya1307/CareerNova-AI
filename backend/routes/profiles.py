
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import StudentProfile, User
from backend.schemas.profile_schema import (
    ProfileCreate,
    ProfileUpdate,
    ProfileResponse
)
from backend.utils.dependencies import get_current_user


# Create profile router
router = APIRouter(
    prefix="/profiles",
    tags=["User Profiles"]
)


# ============================================================
# API 1: CREATE USER PROFILE
# POST /profiles/
# ============================================================

@router.post(
    "/",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED
)
def create_profile(
    profile_data: ProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Check whether profile already exists
    existing_profile = db.scalar(
        select(StudentProfile).where(
            StudentProfile.user_id == current_user.user_id
        )
    )

    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User profile already exists"
        )

    # Create profile using authenticated user's ID
    new_profile = StudentProfile(
        user_id=current_user.user_id,
        **profile_data.model_dump()
    )

    try:
        db.add(new_profile)
        db.commit()
        db.refresh(new_profile)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create profile"
        )

    return new_profile


# ============================================================
# API 2: GET CURRENT USER PROFILE
# GET /profiles/me
# ============================================================

@router.get(
    "/me",
    response_model=ProfileResponse
)
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    profile = db.scalar(
        select(StudentProfile).where(
            StudentProfile.user_id == current_user.user_id
        )
    )

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found"
        )

    return profile


# ============================================================
# API 3: UPDATE CURRENT USER PROFILE
# PATCH /profiles/me
# ============================================================

@router.patch(
    "/me",
    response_model=ProfileResponse
)
def update_profile(
    profile_data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    profile = db.scalar(
        select(StudentProfile).where(
            StudentProfile.user_id == current_user.user_id
        )
    )

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found"
        )

    # Get only the fields supplied by the user
    update_data = profile_data.model_dump(
        exclude_unset=True
    )

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update"
        )

    # Update only the supplied fields
    for field, value in update_data.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)

    return profile
