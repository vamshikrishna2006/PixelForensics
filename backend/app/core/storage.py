"""Storage abstraction for local filesystem and Supabase Storage."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
from app.core.config import get_settings
from app.security.uploads import safe_storage_name, storage_file_path

settings = get_settings()

def _local_store(user_id: str, relative_path: str, data: bytes) -> Path:
    root = Path(settings.LOCAL_STORAGE_PATH).expanduser().resolve()
    target = storage_file_path(str(root), relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as f:
        f.write(data)
    return target

def _local_delete(relative_path: str) -> None:
    try:
        p = storage_file_path(settings.LOCAL_STORAGE_PATH, relative_path)
        p.unlink(missing_ok=True)
    except Exception:
        pass

def store_image(user_id: str, analysis_id: str, raw: bytes, filename: str, relative_path: str | None = None) -> str:
    """Store image and return relative storage path. Raises on failure."""
    ext = os.path.splitext(filename)[1].lower() or ".jpg"
    if relative_path is None:
        relative_path = safe_storage_name(user_id, ext)

    mode = settings.STORAGE_MODE
    supabase_needed = mode in ("supabase", "hybrid") and settings.SUPABASE_STORAGE_ENABLED

    # Validate Supabase config early for modes that require it
    if supabase_needed:
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError("Supabase storage is enabled but SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing")
        # Basic sanity checks to avoid opaque 401s
        url = settings.SUPABASE_URL.strip()
        key = settings.SUPABASE_SERVICE_ROLE_KEY.strip()
        if not url.startswith('http'):
            raise RuntimeError("SUPABASE_URL must start with http/https")
        if len(key) < 20:
            raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY appears invalid or empty")
        from supabase import create_client, Client
        client: Client = create_client(url, key)
        bucket = settings.SUPABASE_STORAGE_BUCKET
        # Upload to Supabase Storage; do not proceed if upload fails
        try:
            client.storage.from_(bucket).upload(
                path=relative_path,
                file=raw,
                file_options={"content-type": "application/octet-stream", "upsert": False}
            )
        except Exception as e:
            # Provide clearer context for auth failures
            msg = str(e)
            if "Invalid API key" in msg or "401" in msg:
                raise RuntimeError("Supabase storage upload failed: Invalid API key. Check SUPABASE_SERVICE_ROLE_KEY and SUPABASE_URL environment variables.") from e
            raise RuntimeError(f"Supabase storage upload failed: {e}") from e
        # In hybrid mode also persist locally for fallback/dev
        if mode == "hybrid":
            _local_store(user_id, relative_path, raw)
    else:
        # Local-only mode
        if mode not in ("local", "unknown"):
            # Unknown mode is treated as local to avoid silent fallback
            raise RuntimeError(f"Unsupported STORAGE_MODE: {mode}")
        _local_store(user_id, relative_path, raw)

    return relative_path

def delete_image(relative_path: str) -> None:
    if settings.STORAGE_MODE in ("local", "hybrid"):
        _local_delete(relative_path)
    if settings.STORAGE_MODE in ("supabase", "hybrid") and settings.SUPABASE_STORAGE_ENABLED:
        try:
            from supabase import create_client, Client
            client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
            client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([relative_path])
        except Exception:
            pass

def get_image_bytes(relative_path: str) -> Optional[bytes]:
    """Retrieve image bytes from configured storage. Prefer Supabase when enabled."""
    if settings.STORAGE_MODE in ("supabase", "hybrid") and settings.SUPABASE_STORAGE_ENABLED:
        try:
            from supabase import create_client, Client
            client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
            data = client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).download(relative_path)
            return bytes(data)
        except Exception:
            pass
    # fallback to local
    if settings.STORAGE_MODE in ("local", "hybrid"):
        try:
            p = storage_file_path(settings.LOCAL_STORAGE_PATH, relative_path)
            if p.exists():
                return p.read_bytes()
        except Exception:
            pass
    return None

def get_signed_url(relative_path: str, expires_in: int = 300) -> Optional[str]:
    if settings.STORAGE_MODE in ("supabase", "hybrid") and settings.SUPABASE_STORAGE_ENABLED:
        try:
            from supabase import create_client, Client
            client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
            url = client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_url(relative_path, expires_in)
            # supabase-py returns dict with 'signedURL'
            signed = url.get("signedURL") if isinstance(url, dict) else None
            return signed
        except Exception:
            pass
    return None
