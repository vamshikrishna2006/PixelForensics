"""SQLAlchemy models. Every row is owned by user_id for isolation."""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

# Native jsonb on Postgres (matches supabase/migrations/0001_init.sql),
# plain JSON on SQLite so local dev still works.
JSONType = JSON().with_variant(JSONB(), "postgresql")


def uid() -> str:
    return str(uuid.uuid4())


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="CUSTOMER")  # CUSTOMER | ADMIN
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="owner", cascade="all,delete")


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(512))
    mime: Mapped[str] = mapped_column(String(64), default="image/jpeg")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="completed")  # processing|completed|failed
    verdict: Mapped[str] = mapped_column(String(32), default="INCONCLUSIVE")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, default=0.5)
    processing_time_s: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    owner: Mapped[Profile] = relationship(back_populates="analyses")
    result: Mapped["AnalysisResult"] = relationship(back_populates="analysis", uselist=False, cascade="all,delete")
    regions: Mapped[list["SuspiciousRegion"]] = relationship(back_populates="analysis", cascade="all,delete")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("analyses.id"), unique=True)
    full_json: Mapped[dict] = mapped_column(JSONType)  # full pipeline dict as JSON(B)
    analysis: Mapped[Analysis] = relationship(back_populates="result")


class SuspiciousRegion(Base):
    __tablename__ = "suspicious_regions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("analyses.id"), index=True)
    x: Mapped[int] = mapped_column(Integer); y: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer); height: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text, default="")
    analysis: Mapped[Analysis] = relationship(back_populates="regions")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
