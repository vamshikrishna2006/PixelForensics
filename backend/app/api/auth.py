"""Auth routes: register / login / me. Roles assigned server-side only."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.observability import log_event
from app.core.security import create_access_token, hash_password, verify_password
from app.models.models import AuditLog, Profile
from app.schemas.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.security.deps import current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

# A valid bcrypt hash used only to equalise login timing when the account does
# not exist. It is not a real account password.
DUMMY_HASH = "$2b$12$Ms4.rxlJcbVHWUE7gRw9BeBIsrKOG.NLg3ZC7xV6Tm5GemucC.lay"


@router.post("/register", response_model=TokenOut, status_code=201)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    exists = (await db.execute(select(Profile).where(
        or_(Profile.email == body.email, Profile.username == body.username)))).scalar_one_or_none()
    if exists:
        log_event(
            "warning",
            "auth",
            "registration rejected",
            alert=False,
            module="auth",
            reason="duplicate_username_or_email",
        )
        raise HTTPException(400, "Username or email already registered.")
    user = Profile(id=str(uuid.uuid4()), username=body.username, email=body.email,
                   password_hash=hash_password(body.password), role="CUSTOMER", status="active")
    db.add(user)
    # Flush the profile first: audit_logs.user_id has a real FK to profiles.id,
    # and without a declared ORM relationship SQLAlchemy may insert the audit
    # row before the profile, which Postgres rejects.
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="register", detail=user.email))
    await db.commit()
    await db.refresh(user)
    return TokenOut(access_token=create_access_token(user.id, user.role),
                    user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    ident = body.identifier.strip()
    user = (await db.execute(select(Profile).where(
        or_(Profile.email == ident, Profile.username == ident)))).scalar_one_or_none()
    # Always perform one bcrypt check, even for unknown or Supabase-managed
    # accounts, so response timing does not reveal account type or existence.
    password_ok = False
    if user and user.password_hash and str(user.password_hash).startswith("$2"):
        password_ok = verify_password(body.password, user.password_hash)
    else:
        verify_password(body.password, DUMMY_HASH)
    if not user or not password_ok:
        log_event(
            "warning",
            "auth",
            "login failed",
            alert=False,
            module="auth",
            reason="invalid_credentials",
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials.")
    if user.status != "active":
        log_event(
            "warning",
            "auth",
            "login rejected",
            alert=False,
            module="auth",
            reason="account_disabled",
        )
        raise HTTPException(403, "Account disabled.")
    db.add(AuditLog(user_id=user.id, action="login", detail="ok"))
    await db.commit()
    log_event(
        "info",
        "auth",
        "login succeeded",
        alert=False,
        module="auth",
        role=user.role,
    )
    return TokenOut(access_token=create_access_token(user.id, user.role),
                    user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: Profile = Depends(current_user)):
    return UserOut.model_validate(user)


@router.post("/sync", response_model=UserOut)
async def sync(user: Profile = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Ensure Supabase user has a profiles row (used when DB trigger is disabled)."""
    db.add(AuditLog(user_id=user.id, action="sync", detail=user.email))
    await db.commit()
    return UserOut.model_validate(user)

