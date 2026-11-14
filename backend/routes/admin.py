
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User
from backend.schemas.internship_schema import (
    IndexRebuildResponse,
    IndexStatusResponse,
)
from backend.schemas.user_schema import RoleUpdateRequest, UserResponse
from backend.services import embeddings, vector_index
from backend.utils.dependencies import require_admin
from backend.utils.roles import ROLE_ADMIN


# Every endpoint in this router requires the admin role.
router = APIRouter(
    prefix="/admin",
    tags=["Administration"],
    dependencies=[Depends(require_admin)],
)


# ============================================================
# LIST USERS
# GET /admin/users
# ============================================================

@router.get(
    "/users",
    response_model=list[UserResponse]
)
def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(User)
        .order_by(User.user_id)
        .offset(skip)
        .limit(limit)
    ).all()


# ============================================================
# UPDATE USER ROLE
# PATCH /admin/users/{user_id}/role
# ============================================================

@router.patch(
    "/users/{user_id}/role",
    response_model=UserResponse
)
def update_user_role(
    user_id: int,
    request: RoleUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Prevent an admin from locking themselves out.
    if (
        user.user_id == current_admin.user_id
        and request.role != ROLE_ADMIN
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own admin role"
        )

    user.role = request.role
    db.commit()
    db.refresh(user)

    return user


# ============================================================
# SEARCH INDEX STATUS
# GET /admin/index/status
# ============================================================

@router.get(
    "/index/status",
    response_model=IndexStatusResponse
)
def get_index_status(db: Session = Depends(get_db)):
    return vector_index.index_status(db)


# ============================================================
# REBUILD SEARCH INDEX FROM POSTGRESQL
# POST /admin/index/rebuild
# ============================================================

@router.post(
    "/index/rebuild",
    response_model=IndexRebuildResponse
)
def rebuild_search_index():
    try:
        result = vector_index.rebuild_index(embeddings.get_embedder())

    except vector_index.IndexBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc)
        )

    except embeddings.EmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc)
        )

    return result.__dict__
