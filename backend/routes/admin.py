import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pwdlib import PasswordHash
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import AdminAuditEvent, AuthSession, EmailDelivery, User, UserInvitation
from backend.schemas.internship_schema import (
    IndexRebuildResponse,
    IndexStatusResponse,
)
from backend.schemas.user_schema import (
    AdminUserCreate,
    AdminUserResponse,
    AuditEventPage,
    EmailDeliveryItem,
    InvitationListItem,
    InvitationSummary,
    RoleUpdateRequest,
    UserResponse,
)
from backend.services import audit, embeddings, invitations, mailer, vector_index
from backend.services.email_service import send_invitation_email
from backend.utils.dependencies import require_admin, require_super_admin
from backend.utils.roles import (
    ROLE_ADMIN,
    VALID_ROLES,
    is_admin_role,
    is_super_admin_role,
)

# Every endpoint in this router requires an administrator (admin or super admin).
router = APIRouter(
    prefix="/admin",
    tags=["Administration"],
    dependencies=[Depends(require_admin)],
)

password_hasher = PasswordHash.recommended()


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def ensure_can_manage(actor: User, target: User) -> None:
    """Who may change whom.

    * Nobody changes the super admin through the API.
    * Nobody changes their own role or status here.
    * Only the super admin manages admins; admins manage students.
    """
    if is_super_admin_role(target.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="The super admin account is protected and cannot be changed here")
    if target.user_id == actor.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="You cannot change your own role or status")
    if is_admin_role(target.role) and not is_super_admin_role(actor.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only the super admin can manage administrator accounts")


def invitation_summary(invitation: UserInvitation | None) -> dict | None:
    if invitation is None:
        return None
    return InvitationSummary(
        invitation_id=invitation.invitation_id, status=invitations.status_of(invitation),
        delivery_status=invitation.delivery_status, delivery_error=invitation.delivery_error,
        created_at=invitation.created_at, expires_at=invitation.expires_at,
    ).model_dump()


def with_invitations(db: Session, users: list[User]) -> list[dict]:
    """UserResponse fields plus each user's latest invitation (one query)."""
    ids = [u.user_id for u in users]
    latest: dict[int, UserInvitation] = {}
    if ids:
        for inv in db.scalars(select(UserInvitation).where(UserInvitation.user_id.in_(ids))
                              .order_by(UserInvitation.invitation_id)):
            latest[inv.user_id] = inv
    return [{**UserResponse.model_validate(u).model_dump(), "invitation": invitation_summary(latest.get(u.user_id))}
            for u in users]


def send_and_record(db: Session, user: User, invitation: UserInvitation, raw_token: str, invited_by: User) -> None:
    """Send the invitation email after the invitation is committed, then store the outcome."""
    result = send_invitation_email(
        user.email, raw_token, first_name=user.first_name,
        invited_by=f"{invited_by.first_name} {invited_by.last_name}".strip() or None,
        user_id=user.user_id, invitation_id=invitation.invitation_id,
    )
    invitation.delivery_status = result.status
    invitation.delivery_error = result.error_code
    db.commit()


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ============================================================
# LIST / SEARCH USERS
# GET /admin/users
# ============================================================

@router.get(
    "/users",
    response_model=list[AdminUserResponse]
)
def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, min_length=1, max_length=100,
                          description="Search name or email (case-insensitive)"),
    role: str | None = Query(default=None, max_length=30),
    is_active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = select(User)
    if q and q.strip():
        pattern = f"%{escape_like(q.strip().lower())}%"
        full_name = func.lower(User.first_name + " " + User.last_name)
        query = query.where(or_(
            func.lower(User.email).like(pattern, escape="\\"),
            full_name.like(pattern, escape="\\"),
        ))
    if role is not None:
        role = role.strip().lower()
        if role not in VALID_ROLES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail=f"Role must be one of: {', '.join(sorted(VALID_ROLES))}")
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active.is_(is_active))
    return with_invitations(db, db.scalars(query.order_by(User.user_id).offset(skip).limit(limit)).all())


@router.get(
    "/users/{user_id}",
    response_model=AdminUserResponse
)
def get_user(user_id: int, db: Session = Depends(get_db)):
    return with_invitations(db, [get_user_or_404(db, user_id)])[0]


# ============================================================
# CREATE USER (pending account)
# POST /admin/users
# ============================================================

@router.post(
    "/users",
    response_model=AdminUserResponse,
    status_code=status.HTTP_201_CREATED
)
def create_user(
    payload: AdminUserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    """Create a pending account. The admin never sets or sees a password.

    The account gets an unusable random password and is not verified, so it
    cannot sign in until the person activates it through the invitation link
    and chooses their own password. The invitation email is sent after the
    account is saved; its delivery status is returned and shown to admins
    (a failed delivery can be re-sent).
    """
    if payload.role == ROLE_ADMIN and not is_super_admin_role(current_admin.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only the super admin can create administrator accounts")

    email = str(payload.email).strip().lower()
    if db.scalar(select(User.user_id).where(func.lower(User.email) == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="An account with this email already exists")

    user = User(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=email,
        phone_number=payload.phone_number,
        role=payload.role,
        is_verified=False,
        is_active=True,
        # Unusable: a random secret that is hashed and immediately discarded.
        password_hash=password_hasher.hash(secrets.token_urlsafe(48)),
    )
    invitation = raw_token = None
    try:
        db.add(user)
        db.flush()
        audit.record(db, "user.create", actor=current_admin, target=user,
                     details={"role": user.role, "pending_activation": True},
                     ip_address=client_ip(request))
        if payload.send_invitation:
            invitation, raw_token = invitations.issue(db, user, current_admin)
            audit.record(db, "user.invite", actor=current_admin, target=user,
                         details={"invitation_id": invitation.invitation_id, "resend": False},
                         ip_address=client_ip(request))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="An account with this email already exists")
    if invitation is not None:
        send_and_record(db, user, invitation, raw_token, current_admin)
    db.refresh(user)
    return with_invitations(db, [user])[0]


# ============================================================
# INVITATIONS
# POST /admin/users/{user_id}/invitation          (send / re-send)
# POST /admin/users/{user_id}/invitation/revoke
# GET  /admin/invitations
# ============================================================

@router.post(
    "/users/{user_id}/invitation",
    response_model=AdminUserResponse
)
def send_invitation(
    user_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    """Issue a new invitation link (the previous one stops working) and email it."""
    user = get_user_or_404(db, user_id)
    ensure_can_manage(current_admin, user)
    try:
        invitations.check_send_allowed(db, user)
    except invitations.InvitationError as exc:
        code = status.HTTP_429_TOO_MANY_REQUESTS if exc.code in ("cooldown", "daily_limit") else status.HTTP_409_CONFLICT
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": exc.message}, headers=headers)
    invitation, raw_token = invitations.issue(db, user, current_admin)
    audit.record(db, "user.invite", actor=current_admin, target=user,
                 details={"invitation_id": invitation.invitation_id, "resend": True}, ip_address=client_ip(request))
    db.commit()
    send_and_record(db, user, invitation, raw_token, current_admin)
    return with_invitations(db, [user])[0]


@router.post(
    "/users/{user_id}/invitation/revoke",
    response_model=AdminUserResponse
)
def revoke_invitation(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    user = get_user_or_404(db, user_id)
    ensure_can_manage(current_admin, user)
    revoked = invitations.revoke_open(db, user)
    if revoked:
        audit.record(db, "user.invite_revoke", actor=current_admin, target=user,
                     details={"revoked": revoked}, ip_address=client_ip(request))
    db.commit()
    return with_invitations(db, [user])[0]


@router.get(
    "/invitations",
    response_model=list[InvitationListItem]
)
def list_invitations(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(UserInvitation, User).join(User, User.user_id == UserInvitation.user_id)
        .order_by(UserInvitation.invitation_id.desc()).offset(skip).limit(limit)
    ).all()
    return [{**invitation_summary(inv), "user_id": user.user_id, "email": user.email,
             "first_name": user.first_name, "last_name": user.last_name,
             "invited_by_user_id": inv.invited_by_user_id} for inv, user in rows]


# ============================================================
# EMAIL STATUS
# GET /admin/email/status       (configuration check; never secrets)
# GET /admin/email/deliveries   (recent delivery outcomes)
# ============================================================

@router.get("/email/status")
def email_status(db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc).replace(microsecond=0)
    counts = dict(db.execute(
        select(EmailDelivery.status, func.count()).group_by(EmailDelivery.status)
    ).tuples().all())
    return {**mailer.validate_config(), "delivery_counts": counts, "checked_at": since}


@router.get(
    "/email/deliveries",
    response_model=list[EmailDeliveryItem]
)
def list_email_deliveries(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    db: Session = Depends(get_db),
):
    query = select(EmailDelivery)
    if status_filter:
        query = query.where(EmailDelivery.status == status_filter)
    return db.scalars(query.order_by(EmailDelivery.delivery_id.desc()).offset(skip).limit(limit)).all()


# ============================================================
# UPDATE USER ROLE (super admin only)
# PATCH /admin/users/{user_id}/role
# ============================================================

@router.patch(
    "/users/{user_id}/role",
    response_model=UserResponse
)
def update_user_role(
    user_id: int,
    payload: RoleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_super_admin),
):
    if is_super_admin_role(payload.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The super admin role can only be assigned with the create-superadmin command"
        )

    user = get_user_or_404(db, user_id)
    ensure_can_manage(current_admin, user)

    if user.role == payload.role:
        return user

    previous = user.role
    user.role = payload.role
    audit.record(db, "user.role_change", actor=current_admin, target=user,
                 details={"from": previous, "to": payload.role}, ip_address=client_ip(request))
    db.commit()
    db.refresh(user)
    return user


# ============================================================
# DEACTIVATE / REACTIVATE
# POST /admin/users/{user_id}/deactivate
# POST /admin/users/{user_id}/reactivate
# ============================================================

@router.post(
    "/users/{user_id}/deactivate",
    response_model=UserResponse
)
def deactivate_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    """Block sign-in and every API request; all data is kept."""
    user = get_user_or_404(db, user_id)
    ensure_can_manage(current_admin, user)
    if not user.is_active:
        return user

    now = datetime.now(timezone.utc)
    user.is_active = False
    user.deactivated_at = now
    revoked = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    ).rowcount
    audit.record(db, "user.deactivate", actor=current_admin, target=user,
                 details={"signed_out_devices": revoked}, ip_address=client_ip(request))
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/users/{user_id}/reactivate",
    response_model=UserResponse
)
def reactivate_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    user = get_user_or_404(db, user_id)
    ensure_can_manage(current_admin, user)
    if user.is_active:
        return user

    user.is_active = True
    user.deactivated_at = None
    audit.record(db, "user.reactivate", actor=current_admin, target=user,
                 ip_address=client_ip(request))
    db.commit()
    db.refresh(user)
    return user


# ============================================================
# AUDIT LOG
# GET /admin/audit-events
# ============================================================

@router.get(
    "/audit-events",
    response_model=AuditEventPage
)
def list_audit_events(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    action: str | None = Query(default=None, max_length=50),
    target_user_id: int | None = Query(default=None, ge=1),
    actor_user_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    conditions = []
    if action:
        conditions.append(AdminAuditEvent.action == action)
    if target_user_id is not None:
        conditions.append(AdminAuditEvent.target_user_id == target_user_id)
    if actor_user_id is not None:
        conditions.append(AdminAuditEvent.actor_user_id == actor_user_id)
    total = db.scalar(select(func.count()).select_from(AdminAuditEvent).where(*conditions))
    items = db.scalars(
        select(AdminAuditEvent).where(*conditions)
        .order_by(AdminAuditEvent.event_id.desc()).offset(skip).limit(limit)
    ).all()
    return {"total": total, "skip": skip, "limit": limit, "items": items}


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
def rebuild_search_index(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
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
    audit.record(db, "index.rebuild", actor=current_admin,
                 details={"indexed": result.indexed, "deactivated_documents": result.deactivated_documents},
                 ip_address=client_ip(request))
    db.commit()
    return result.__dict__
