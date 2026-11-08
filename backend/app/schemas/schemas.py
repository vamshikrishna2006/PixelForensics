"""Pydantic request/response schemas — every input is validated."""
import re
from pydantic import BaseModel, EmailStr, field_validator

PWD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")


class RegisterIn(BaseModel):
    username: str
    email: EmailStr
    password: str
    confirm_password: str

    @field_validator("username")
    @classmethod
    def _u(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", v):
            raise ValueError("Username: 3-32 chars, letters/numbers/._-")
        return v

    @field_validator("password")
    @classmethod
    def _p(cls, v: str) -> str:
        if not PWD_RE.match(v):
            raise ValueError("Password needs 8+ chars with upper, lower, number, special.")
        return v

    @field_validator("confirm_password")
    @classmethod
    def _c(cls, v, info):
        if "password" in (info.data or {}) and v != info.data["password"]:
            raise ValueError("Passwords do not match.")
        return v


class LoginIn(BaseModel):
    identifier: str  # username OR email
    password: str


class UserOut(BaseModel):
    id: str; username: str; email: EmailStr; role: str; status: str
    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str; token_type: str = "bearer"; user: UserOut


class DetectorOut(BaseModel):
    method: str; score: float; confidence: float; interpretation: str; details: dict = {}


class AnalysisOut(BaseModel):
    id: str; filename: str; status: str; verdict: str; confidence: float
    final_score: float; created_at: str; processing_time_s: float = 0.0


class ReportOut(BaseModel):
    analysis: AnalysisOut
    detectors: list[DetectorOut]
    breakdown: list[dict]
    explanation: str
    regions: list[dict]
    artifacts: dict
    image_info: dict
    narrative: dict = {}
    report_name: str = ""


class ComparePairOut(BaseModel):
    a: str; b: str; correlation: float; interpretation: str


class CompareOut(BaseModel):
    pairs: list[ComparePairOut]; mean_correlation: float; verdict: str; note: str
