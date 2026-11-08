"""Password hashing + JWT handling. Never store plaintext passwords.

Dual-mode (Option B migration):
- local JWT (SECRET_KEY/HS256 via python-jose) for SQLite dev
- Supabase JWT: legacy HS256 (SUPABASE_JWT_SECRET) OR new RS256 via JWKS (SUPABASE_JWKS_URL)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from jose import JWTError, jwt as jose_jwt
from passlib.context import CryptContext
from .config import get_settings

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()

_JWKS_CLIENT = None


def _jwks_client():
    global _JWKS_CLIENT
    if _JWKS_CLIENT is not None:
        return _JWKS_CLIENT
    url = (get_settings().SUPABASE_JWKS_URL or "").strip()
    if not url:
        # derive from SUPABASE_URL
        base = (get_settings().SUPABASE_URL or "").strip().rstrip("/")
        if base:
            url = base + "/auth/v1/.well-known/jwks.json"
    if not url:
        return None
    try:
        import jwt as pyjwt
        _JWKS_CLIENT = pyjwt.PyJWKClient(url, cache_keys=True)
        return _JWKS_CLIENT
    except Exception:
        return None


def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed or not str(hashed).startswith("$2"):
        return False
    try:
        return pwd_ctx.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(sub: str, role: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jose_jwt.encode({"sub": sub, "role": role, "exp": exp}, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        # leeway=10s tolerates second-granularity `exp`/`nbf` boundaries and
        # small clock skew between issuing and verifying hosts. (python-jose
        # takes leeway through the options dict; it does not accept a leeway kwarg.)
        return jose_jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM],
                               options={"leeway": 10})
    except JWTError:
        return None


def decode_supabase_legacy(token: str) -> Optional[dict]:
    """Legacy HS256 Supabase JWT (old projects)."""
    secret = (get_settings().SUPABASE_JWT_SECRET or "").strip()
    if not secret:
        return None
    try:
        return jose_jwt.decode(token, secret, algorithms=["HS256"],
                               options={"verify_aud": False, "leeway": 10})
    except JWTError:
        return None


def decode_supabase_jwks(token: str) -> Optional[dict]:
    """New RS256/ES256 Supabase JWT via JWKS (current Supabase projects)."""
    client = _jwks_client()
    if not client:
        return None
    try:
        import jwt as pyjwt
        last_err: Exception = Exception("unknown")
        for attempt in range(2):  # retry once — JWKS fetch can hiccup transiently
            try:
                key = client.get_signing_key_from_jwt(token).key
                # leeway=10s tolerates second-granularity iat boundaries and
                # small clock skew between issuing (Supabase) and verifying hosts.
                return pyjwt.decode(token, key, algorithms=["RS256", "ES256"],
                                    options={"verify_aud": False}, leeway=10)
            except Exception as e:  # noqa: BLE001
                last_err = e
                # force-refresh the cached key set before retrying
                try:
                    client.get_signing_keys(refresh=True)
                except Exception:  # noqa: BLE001
                    pass
                if attempt == 0:
                    continue
        return None
    except Exception:
        return None


def decode_supabase_token(token: str) -> Optional[dict]:
    return decode_supabase_legacy(token) or decode_supabase_jwks(token)


def decode_any_token(token: str) -> Tuple[Optional[dict], Optional[str]]:
    """Try local JWT first, then Supabase JWT. Returns (payload, source)."""
    mode = (get_settings().AUTH_MODE or "dual").lower()
    if mode in ("local", "dual"):
        p = decode_token(token)
        if p:
            return p, "local"
    if mode in ("supabase", "dual"):
        p = decode_supabase_token(token)
        if p:
            return p, "supabase"
    return None, None
