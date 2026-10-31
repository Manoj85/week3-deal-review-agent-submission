"""Read only this project's configuration; never print keys."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    mode: str
    key: str = field(repr=False)
    model: str
    base_url: str


def settings() -> Settings:
    values = {**dotenv_values(ROOT / ".env", interpolate=False), **os.environ}
    return Settings(
        mode=values.get("EXTRACTION_MODE") or "nebius",
        key=values.get("NEBIUS_API_KEY") or "",
        model=values.get("NEBIUS_CHAT_MODEL") or "",
        base_url=values.get("NEBIUS_BASE_URL") or "https://api.tokenfactory.nebius.com/v1/",
    )


def review_data_directory() -> Path:
    values = {**dotenv_values(ROOT / ".env", interpolate=False), **os.environ}
    path = Path(values.get("REVIEW_DATA_DIR") or "local_data")
    return path if path.is_absolute() else ROOT / path
