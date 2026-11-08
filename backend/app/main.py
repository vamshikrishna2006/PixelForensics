"""FastAPI entrypoint: CORS, logging, routes, DB init, admin seed and workers."""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.monitoring import router as monitoring_router
from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.core.observability import ObservabilityMiddleware, log_event, setup_logging
from app.services.backups import backup_scheduler_loop
from app.services.health import monitoring_loop, readiness

settings = get_settings()
setup_logging()
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(os.path.abspath(settings.LOCAL_STORAGE_PATH), exist_ok=True)
    # Fail fast if Supabase storage is required but not configured
    if settings.STORAGE_MODE in ("supabase", "hybrid") and settings.SUPABASE_STORAGE_ENABLED:
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError("STORAGE_MODE requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
    await init_db()

    # Seed the default admin only when no administrator exists.
    from sqlalchemy import select
    from app.models.models import Profile
    from app.core.security import hash_password
    import uuid

    async with SessionLocal() as db:
        has_admin = (await db.execute(select(Profile).where(Profile.role == "ADMIN"))).scalar_one_or_none()
        if not has_admin:
            db.add(
                Profile(
                    id=str(uuid.uuid4()),
                    username=settings.DEFAULT_ADMIN_USERNAME,
                    email=settings.DEFAULT_ADMIN_EMAIL,
                    password_hash=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
                    role="ADMIN",
                    status="active",
                )
            )
            await db.commit()

    tasks: list[asyncio.Task] = []
    if settings.MONITORING_ENABLED:
        tasks.append(asyncio.create_task(monitoring_loop(), name="pf-monitoring"))
    if settings.BACKUP_ENABLED:
        tasks.append(asyncio.create_task(backup_scheduler_loop(), name="pf-backup-scheduler"))

    log_event(
        "info",
        "application",
        "application started",
        alert=False,
        module="main",
        environment=settings.ENVIRONMENT,
        version=settings.APP_VERSION,
        monitoring_enabled=settings.MONITORING_ENABLED,
        backup_enabled=settings.BACKUP_ENABLED,
    )
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        log_event("info", "application", "application stopped", alert=False, module="main")


app = FastAPI(title="PixelForensics", version=settings.APP_VERSION, lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Content-Disposition"],
)
# Outermost middleware: correlation ID, safe 500s, security headers and error logs.
app.add_middleware(ObservabilityMiddleware)

app.include_router(auth_router)
app.include_router(analysis_router)
app.include_router(monitoring_router)


@app.get("/api/health")
async def health():
    """Liveness probe. Does not touch the database."""
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "algorithm": settings.FORENSIC_ALGORITHM_VERSION,
    }


@app.get("/api/ready")
async def ready():
    """Readiness probe for uptime monitors. Checks database and storage."""
    result = await readiness()
    if result["status"] != "ready":
        return JSONResponse(status_code=503, content=result)
    return result