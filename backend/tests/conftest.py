"""Tests opt into offline mode; they never spend API credits implicitly."""

import pytest


@pytest.fixture(autouse=True)
def offline_mode(monkeypatch):
    monkeypatch.setenv("EXTRACTION_MODE", "offline_sample_parser")
