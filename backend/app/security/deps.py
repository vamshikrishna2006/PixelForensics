"""Auth dependencies — role is ALWAYS read from DB, never trusted from client.

Dual-mode Option B:
- local JWT: sub = profiles.id (custom UUID)
- supabase JWT: sub = auth.users.id -> auto-provision profiles row (id=sub)
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import decode_any_token
from app.models.models import Profile

bearer = HTTPBearer(auto_error=False)


async def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                       db: AsyncSession = Depends(get_db)) -> Profile:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload, source = decode_any_token(creds.credentials)
    if not payload or not payload.get("sub"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    sub = str(payload.get("sub"))
    user = (await db.execute(select(Profile).where(Profile.id == sub))).scalar_one_or_none()
    if source == "supabase" and not user:
        # auto-provision profile linked to Supabase auth.users.id
        import re
        raw_email = str(payload.get("email") or "").strip()
        email = raw_email or f"{sub[:8]}@supabase.local"
        base = re.sub(r"[^a-zA-Z0-9_.-]", "", email.split("@")[0])[:24] or f"user_{sub[:8]}"
        if len(base) < 3:
            base = f"user_{sub[:8]}"
        username = f"{base}_{sub[:4]}"
        # retry on username collision
        import uuid as _uuid
        for _ in range(5):
            exists = (await db.execute(select(Profile).where(Profile.username == username))).scalar_one_or_none()
            if not exists:
                break
            username = f"{base[:20]}_{_uuid.uuid4().hex[:6]}"
        # also guard email collision (local row with same email)
        email_exists = (await db.execute(select(Profile).where(Profile.email == email))).scalar_one_or_none()
        if email_exists and email_exists.id != sub:
            email = f"{sub[:8]}+{email}" if "@" in email else f"{sub[:8]}@supabase.local"
        user = Profile(id=sub, username=username, email=email,
                       password_hash="supabase-auth", role="CUSTOMER", status="active")
        db.add(user)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            # id was created concurrently (trigger race) — refetch
            user = (await db.execute(select(Profile).where(Profile.id == sub))).scalar_one_or_none()
            if not user:
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Profile sync failed, retry login.")
        else:
            await db.refresh(user)
    if not user or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account unavailable")
    return user


async def admin_user(user: Profile = Depends(current_user)) -> Profile:
    if user.role != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user
