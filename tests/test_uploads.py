"""Upload-validation + isolation tests (lightweight, no DB needed)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from app.security.uploads import sniff_mime, safe_storage_name, MAX_BYTES_DEFAULT, storage_file_path


def test_sniff_jpeg_png():
    assert sniff_mime(b"\xff\xd8\xff" + b"\x00" * 200) == "image/jpeg"
    assert sniff_mime(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200) == "image/png"


def test_sniff_rejects_garbage():
    assert sniff_mime(b"hello world" * 50) is None


def test_storage_names_unique_and_scoped():
    a = safe_storage_name("user-1", ".jpg")
    b = safe_storage_name("user-1", ".jpg")
    c = safe_storage_name("user-2", ".jpg")
    assert a != b
    assert a.startswith("user-1/") and c.startswith("user-2/")
    assert ".." not in a and "\\" not in a


def test_storage_ext_sanitized():
    n = safe_storage_name("u", ".exe")
    assert n.endswith(".jpg")


def test_max_bytes_sane():
    assert MAX_BYTES_DEFAULT == 10 * 1024 * 1024


def test_storage_file_path_rejects_traversal(tmp_path):
    root = tmp_path / "storage"
    root.mkdir()
    assert storage_file_path(str(root), "user-1/file.jpg") == (root / "user-1" / "file.jpg").resolve()
    with pytest.raises(ValueError):
        storage_file_path(str(root), "../outside.jpg")
    with pytest.raises(ValueError):
        storage_file_path(str(root), str(tmp_path / "outside.jpg"))
