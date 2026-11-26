
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
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
from backend.services import avatars
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



# ============================================================
# PROFILE PICTURE (owner only)
# POST   /profiles/me/avatar   upload or replace (PNG / JPEG / WebP, <= 2 MB)
# GET    /profiles/me/avatar   the picture itself (404 when none)
# DELETE /profiles/me/avatar   remove it (initials are shown again)
# ============================================================

def _own_profile(db: Session, user: User, create: bool = False) -> StudentProfile | None:
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.user_id))
    if profile is None and create:
        profile = StudentProfile(user_id=user.user_id)
        db.add(profile)
        db.flush()
    return profile


@router.post("/me/avatar", response_model=ProfileResponse)
async def upload_avatar(file: UploadFile = File(...), db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    data = await file.read(avatars.MAX_BYTES + 1)
    try:
        info = avatars.inspect(data)
    except avatars.AvatarError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    profile = _own_profile(db, current_user, create=True)
    previous = profile.avatar_path
    stored = avatars.save(current_user.user_id, data, info)
    profile.avatar_path, profile.avatar_content_type = stored, info.content_type
    profile.avatar_updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        avatars.remove(current_user.user_id, stored)
        raise
    avatars.remove(current_user.user_id, previous)        # the old picture is replaced, not kept
    db.refresh(profile)
    return profile


@router.get("/me/avatar")
def get_avatar(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    profile = _own_profile(db, current_user)
    path = avatars.resolve(current_user.user_id, profile.avatar_path if profile else None)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No profile picture")
    return FileResponse(path, media_type=profile.avatar_content_type or "application/octet-stream",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
                                 "Content-Disposition": "inline"})


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
def delete_avatar(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    profile = _own_profile(db, current_user)
    if profile is None or not profile.avatar_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No profile picture")
    stored = profile.avatar_path
    profile.avatar_path = profile.avatar_content_type = profile.avatar_updated_at = None
    db.commit()
    avatars.remove(current_user.user_id, stored)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
