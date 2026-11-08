"""Central configuration — all secrets come from environment."""
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    APP_NAME: str = "PixelForensics"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    SECRET_KEY: str = "please-change-me-to-a-long-random-string-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Auth mode: "local" (custom JWT+bcrypt, SQLite dev) or "supabase" (Supabase Auth, Postgres prod)
    # dual = accept BOTH (local JWT + Supabase JWT) — safe migration mode
    AUTH_MODE: str = "dual"

    SUPABASE_JWT_SECRET: str = ""  # legacy HS256 JWT secret (old projects)
    SUPABASE_JWKS_URL: str = ""  # e.g. https://xyz.supabase.co/auth/v1/.well-known/jwks.json (new RS256 projects)

    DATABASE_URL: str = "sqlite:///./pixelforensics.db"

    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "images"

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    RATE_LIMIT_PER_MINUTE: int = 60

    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_MIME_TYPES: str = "image/jpeg,image/png,image/webp"
    LOCAL_STORAGE_PATH: str = "./storage"
    # RAM & analysis limits
    ANALYSIS_CONCURRENCY: int = 1
    MAX_IMAGE_DIMENSION: int = 4096
    MAX_PIXEL_COUNT: int = 8388608
    # Storage backend
    STORAGE_MODE: str = "local"
    SUPABASE_STORAGE_ENABLED: bool = False

    FORENSIC_ALGORITHM_VERSION: str = "1.0.0"

    # ---------------------------------------------------------------- logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/app.jsonl"
    LOG_MAX_BYTES: int = 5_000_000
    LOG_BACKUP_COUNT: int = 5

    # ------------------------------------------------------------- alerting
    # Leave empty to keep alerts dashboard-only (no external delivery).
    ALERT_WEBHOOK_URL: str = ""
    ALERT_WEBHOOK_TYPE: str = "generic"  # generic | slack | discord
    ALERT_EMAIL_SMTP_HOST: str = ""
    ALERT_EMAIL_SMTP_PORT: int = 587
    ALERT_EMAIL_SMTP_USER: str = ""
    ALERT_EMAIL_SMTP_PASSWORD: str = ""
    ALERT_EMAIL_FROM: str = ""
    ALERT_EMAIL_TO: str = ""
    ALERT_EMAIL_USE_TLS: bool = True
    ALERT_COOLDOWN_MINUTES: int = 30
    ALERT_MIN_SEVERITY: str = "error"  # warning | error | critical

    # --------------------------------------------------------- health checks
    MONITORING_ENABLED: bool = True
    MONITOR_INTERVAL_SECONDS: int = 300

    # --------------------------------------------------------------- backups
    # Set BACKUP_ENABLED=false to use an external scheduler instead.
    BACKUP_ENABLED: bool = True
    BACKUP_DIR: str = "./backups"
    BACKUP_HOUR_UTC: int = 2
    BACKUP_CHECK_INTERVAL_MINUTES: int = 60
    BACKUP_RETENTION_DAYS: int = 14
    BACKUP_PG_DUMP_TIMEOUT_SECONDS: int = 600
    BACKUP_VERIFY_AFTER_RUN: bool = True
    # auto: use pg_dump when available, otherwise a read-only logical JSONL dump
    # (works on hosts without PostgreSQL client tools, e.g. Supabase).
    BACKUP_POSTGRES_MODE: str = "auto"  # auto | pg_dump | logical
    # Must point at an isolated test database, never production.
    RESTORE_TEST_DATABASE_URL: str = ""

    DEFAULT_ADMIN_EMAIL: str = "admin@pixelforensics.com"
    DEFAULT_ADMIN_PASSWORD: str = "Admin@12345"
    DEFAULT_ADMIN_USERNAME: str = "admin"

    GUEST_ACCESS_MODE: bool = False

    @field_validator('SUPABASE_URL', 'SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY', mode='before')
    @classmethod
    def strip_supabase_strings(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_mime_list(self) -> list[str]:
        return [m.strip() for m in self.ALLOWED_MIME_TYPES.split(",") if m.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
