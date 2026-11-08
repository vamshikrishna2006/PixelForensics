"""Shared test helpers (kept outside conftest for clean imports)."""
from __future__ import annotations

import io

from PIL import Image
from fastapi.testclient import TestClient


def make_jpeg(seed: int = 1, size: int = 256) -> bytes:
    """Small deterministic JPEG that exercises the real forensic pipeline."""
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            pixels[x, y] = (
                (x * 3 + seed * 17) % 256,
                (y * 5 + seed * 29) % 256,
                ((x ^ y) + seed * 41) % 256,
            )
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def analyze(client: TestClient, headers: dict, seed: int = 1) -> dict:
    response = client.post(
        "/api/analyze",
        headers=headers,
        files={"file": (f"sample-{seed}.jpg", make_jpeg(seed), "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    return response.json()