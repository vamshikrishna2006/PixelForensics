"""Schema validation tests (needs pydantic + email-validator)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from pydantic import ValidationError
from app.schemas.schemas import RegisterIn


def test_register_ok():
    r = RegisterIn(username="analyst_1", email="a@x.com",
                   password="Strong@123", confirm_password="Strong@123")
    assert r.username == "analyst_1"


def test_register_weak_password_rejected():
    with pytest.raises(ValidationError):
        RegisterIn(username="analyst_1", email="a@x.com",
                   password="weak", confirm_password="weak")


def test_register_mismatch_rejected():
    with pytest.raises(ValidationError):
        RegisterIn(username="analyst_1", email="a@x.com",
                   password="Strong@123", confirm_password="Other@123")


def test_register_bad_username_rejected():
    with pytest.raises(ValidationError):
        RegisterIn(username="ab", email="a@x.com",
                   password="Strong@123", confirm_password="Strong@123")
