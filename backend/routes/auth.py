
import smtplib

from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status
)

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pwdlib import PasswordHash

from backend.database import get_db

from backend.models import (
    User,
    AuthSession,
    EmailVerificationToken,
    PasswordResetToken
)
from backend.schemas.user_schema import (
    UserCreate,
    UserResponse,
    UserLogin,
    TokenResponse,
    RefreshTokenRequest,
    UserDeleteRequest,
    ForgotPasswordRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    ChangePasswordRequest
)
from backend.services.email_service import (
    send_verification_email,
    send_password_reset_email
)
from backend.utils.security import (
    create_access_token,
    create_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS
)

from backend.utils.tokens import (
    generate_secure_token,
    hash_token,
    get_token_expiry
)

from backend.utils.dependencies import get_current_user


# Verification links stay valid for 24 hours.
VERIFICATION_TOKEN_EXPIRE_MINUTES = 1440

# Minimum wait between verification emails for one account.
RESEND_VERIFICATION_COOLDOWN_SECONDS = 60


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

password_hasher = PasswordHash.recommended()


# ============================================================
# REGISTER
# POST /auth/register
# ============================================================

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):

    email = str(user_data.email).strip().lower()

    existing_user = db.scalar(
        select(User).where(func.lower(User.email) == email)
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered"
        )

    hashed_password = password_hasher.hash(user_data.password)

    new_user = User(
    first_name=user_data.first_name,
    last_name=user_data.last_name,
    phone_number=user_data.phone_number,
    email=email,
    password_hash=hashed_password
)

    raw_token = generate_secure_token()

    try:
        db.add(new_user)
        db.flush()

        verification_record = EmailVerificationToken(
            user_id=new_user.user_id,
            token_hash=hash_token(raw_token),
            expires_at=get_token_expiry(
                minutes=VERIFICATION_TOKEN_EXPIRE_MINUTES
            )
        )

        db.add(verification_record)
        db.commit()
        db.refresh(new_user)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not register user. Email may already exist."
        )

    try:
        send_verification_email(
            to_email=new_user.email,
            token=raw_token
        )

    except (smtplib.SMTPException, OSError, RuntimeError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Account created, but verification email could not "
                "be sent. Please try again later."
            )
        )

    return new_user


# ============================================================
# VERIFY EMAIL
# GET /auth/verify-email
# ============================================================

@router.get(
    "/verify-email",
    status_code=status.HTTP_200_OK
)
def verify_email(
    token: str = Query(..., min_length=20, max_length=256),
    db: Session = Depends(get_db)
):

    hashed_token = hash_token(token)

    verification_record = db.scalar(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == hashed_token
        )
    )

    if verification_record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification link"
        )

    if verification_record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link has already been used"
        )

    now = datetime.now(timezone.utc)
    expiry = verification_record.expires_at

    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    if expiry <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification link has expired"
        )

    user = db.get(User, verification_record.user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found"
        )

    user.is_verified = True
    verification_record.used_at = now

    db.commit()

    return {
        "message": "Email verified successfully. You can now log in."
    }


# ============================================================
# RESEND VERIFICATION EMAIL
# POST /auth/resend-verification
# ============================================================

@router.post(
    "/resend-verification",
    status_code=status.HTTP_200_OK
)
def resend_verification_email(
    request: ResendVerificationRequest,
    db: Session = Depends(get_db)
):
    # Same response for unknown, verified and unverified emails
    # so the endpoint cannot be used to discover accounts.
    generic_response = {
        "message": (
            "If an unverified account exists with this email, "
            "a new verification link will be sent."
        )
    }

    email = str(request.email).strip().lower()

    user = db.scalar(
        select(User).where(func.lower(User.email) == email)
    )

    if user is None or user.is_verified:
        return generic_response

    now = datetime.now(timezone.utc)

    # Lock this user's outstanding tokens while replacing them.
    outstanding_tokens = db.scalars(
        select(EmailVerificationToken)
        .where(
            EmailVerificationToken.user_id == user.user_id,
            EmailVerificationToken.used_at.is_(None)
        )
        .with_for_update()
    ).all()

    # Throttle: skip sending if a link was issued very recently.
    for token_record in outstanding_tokens:
        created_at = token_record.created_at

        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        if (now - created_at).total_seconds() < (
            RESEND_VERIFICATION_COOLDOWN_SECONDS
        ):
            db.rollback()
            return generic_response

    # Invalidate older links so only the newest one works.
    for token_record in outstanding_tokens:
        token_record.used_at = now

    raw_token = generate_secure_token()

    new_record = EmailVerificationToken(
        user_id=user.user_id,
        token_hash=hash_token(raw_token),
        expires_at=get_token_expiry(
            minutes=VERIFICATION_TOKEN_EXPIRE_MINUTES
        )
    )

    try:
        db.add(new_record)
        db.commit()

    except Exception:
        db.rollback()
        raise

    try:
        send_verification_email(
            to_email=user.email,
            token=raw_token
        )

    except (smtplib.SMTPException, OSError, RuntimeError):
        # The link was never delivered, so disable it.
        new_record.used_at = datetime.now(timezone.utc)
        db.commit()

    return generic_response


# ============================================================
# LOGIN
# POST /auth/login
# ============================================================

@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK
)
def login_user(
    user_data: UserLogin,
    db: Session = Depends(get_db)
):

    email = str(user_data.email).strip().lower()

    user = db.scalar(
        select(User).where(func.lower(User.email) == email)
    )

    if (
        user is None
        or not password_hasher.verify(
            user_data.password,
            user.password_hash
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in."
        )

    # Generate a new refresh token.
    raw_refresh_token = create_refresh_token()

    refresh_expiry_minutes = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60

    # Store only the refresh-token hash.
    new_session = AuthSession(
        user_id=user.user_id,
        refresh_token_hash=hash_token(raw_refresh_token),
        expires_at=get_token_expiry(
            minutes=refresh_expiry_minutes
        )
    )

    try:
        db.add(new_session)
        db.flush()

        # Include the database session ID in the access JWT.
        access_token = create_access_token(
            subject=str(user.user_id),
            session_id=new_session.session_id
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "refresh_expires_in": REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    }


# ============================================================
# REFRESH TOKEN
# POST /auth/refresh
# ============================================================

@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK
)
def refresh_access_token(
    token_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
):

    hashed_refresh_token = hash_token(token_data.refresh_token)

    # Lock the database record while rotating the token.
    auth_session = db.scalar(
        select(AuthSession)
        .where(
            AuthSession.refresh_token_hash == hashed_refresh_token
        )
        .with_for_update()
    )

    if auth_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    now = datetime.now(timezone.utc)
    expiry = auth_session.expires_at

    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    if auth_session.revoked_at is not None or expiry <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is expired or revoked"
        )

    user = db.get(User, auth_session.user_id)

    if user is None or not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is unavailable"
        )

    # Rotate the refresh token.
    new_refresh_token = create_refresh_token()

    auth_session.refresh_token_hash = hash_token(new_refresh_token)
    auth_session.expires_at = get_token_expiry(
        minutes=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60
    )
    auth_session.last_used_at = now

    new_access_token = create_access_token(
        subject=str(user.user_id),
        session_id=auth_session.session_id
    )

    try:
        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "refresh_expires_in": REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    }


# ============================================================
# LOGOUT
# POST /auth/logout
# ============================================================

@router.post(
    "/logout",
    status_code=status.HTTP_200_OK
)
def logout_user(
    token_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
):

    hashed_refresh_token = hash_token(token_data.refresh_token)

    auth_session = db.scalar(
        select(AuthSession)
        .where(
            AuthSession.refresh_token_hash == hashed_refresh_token
        )
        .with_for_update()
    )

    if auth_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    if auth_session.revoked_at is not None:
        return {"message": "Session is already logged out"}

    auth_session.revoked_at = datetime.now(timezone.utc)

    db.commit()

    return {"message": "Logout successful"}


# ============================================================
# GET CURRENT USER
# GET /auth/me
# ============================================================

@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK
)
def get_logged_in_user(
    current_user: User = Depends(get_current_user)
):
    return current_user


# ============================================================
# DELETE ACCOUNT
# DELETE /auth/account
# ============================================================

@router.delete(
    "/account",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response
)
def delete_user_account(
    delete_data: UserDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    if not password_hasher.verify(
        delete_data.current_password,
        current_user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )

    try:
        db.delete(current_user)
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to delete account because related records exist"
        )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )

# ============================================================
# FORGOT PASSWORD
# POST /auth/forgot-password
# ============================================================

@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK
)
def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    email = str(request.email).strip().lower()

    # Find the registered user.
    user = db.scalar(
        select(User).where(func.lower(User.email) == email)
    )

    # Use the same response whether the email exists or not.
    generic_response = {
        "message": (
            "If an account exists with this email, "
            "password reset instructions will be sent."
        )
    }

    if user is None:
        return generic_response

    now = datetime.now(timezone.utc)

    # Invalidate previous unused reset tokens.
    previous_tokens = db.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.user_id,
            PasswordResetToken.used_at.is_(None)
        )
    ).all()

    for old_token in previous_tokens:
        old_token.used_at = now

    # Generate a new secure reset token.
    raw_token = generate_secure_token()

    reset_record = PasswordResetToken(
        user_id=user.user_id,
        token_hash=hash_token(raw_token),
        expires_at=get_token_expiry(minutes=30)
    )

    try:
        db.add(reset_record)
        db.commit()

    except Exception:
        db.rollback()
        raise

    # Send the original token by email.
    try:
        send_password_reset_email(
            to_email=user.email,
            token=raw_token
        )

    except (smtplib.SMTPException, OSError, RuntimeError):
        # Invalidate the token if email delivery fails.
        reset_record.used_at = datetime.now(timezone.utc)
        db.commit()

        # Keep the response generic to prevent email enumeration.
        return generic_response

    return generic_response

# ============================================================
# RESET PASSWORD
# POST /auth/reset-password
# ============================================================

@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK
)
def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    # Hash the token received from the email.
    hashed_token = hash_token(request.token)

    # Lock the token record to prevent simultaneous reuse.
    reset_record = db.scalar(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == hashed_token
        )
        .with_for_update()
    )

    if reset_record is None or reset_record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or already used password reset token"
        )

    now = datetime.now(timezone.utc)
    expiry = reset_record.expires_at

    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    if expiry <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token has expired"
        )

    user = db.get(User, reset_record.user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found"
        )

    try:
        # Update the user's password using Argon2.
        user.password_hash = password_hasher.hash(
            request.new_password
        )

        # Invalidate all unused password-reset tokens
        # belonging to this user.
        outstanding_tokens = db.scalars(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.user_id,
                PasswordResetToken.used_at.is_(None)
            )
        ).all()

        for record in outstanding_tokens:
            record.used_at = now

        # Revoke every active login session.
        active_sessions = db.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user.user_id,
                AuthSession.revoked_at.is_(None)
            )
        ).all()

        for session in active_sessions:
            session.revoked_at = now

        # Save password update, token consumption and
        # session revocation together.
        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "message": (
            "Password reset successful. "
            "Please log in using your new password."
        )
    }

# ============================================================
# CHANGE PASSWORD
# POST /auth/change-password
# ============================================================

@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK
)
def change_password(
    request: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify the current password.
    if not password_hasher.verify(
        request.current_password,
        current_user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )

    # Prevent using the same password again.
    if password_hasher.verify(
        request.new_password,
        current_user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password"
        )

    now = datetime.now(timezone.utc)

    try:
        # Hash and update the new password.
        current_user.password_hash = password_hasher.hash(
            request.new_password
        )

        # Revoke all existing login sessions.
        active_sessions = db.scalars(
            select(AuthSession).where(
                AuthSession.user_id == current_user.user_id,
                AuthSession.revoked_at.is_(None)
            )
        ).all()

        for session in active_sessions:
            session.revoked_at = now

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "message": (
            "Password changed successfully. "
            "Please log in again using your new password."
        )
    }
