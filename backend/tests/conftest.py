"""Tests opt into offline mode; they never spend API credits implicitly."""

import pytest


@pytest.fixture(autouse=True)
def offline_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("EXTRACTION_MODE", "offline_sample_parser")
    monkeypatch.setenv("REVIEW_DATA_DIR", str(tmp_path / "review-data"))
