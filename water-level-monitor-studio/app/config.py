from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class AppConfig:
    api_base_url: str = os.getenv("WLM_API_BASE_URL", "http://localhost:8080").rstrip("/")
    default_username: str = os.getenv("WLM_DEFAULT_USERNAME", "admin")
    default_password: str = os.getenv("WLM_DEFAULT_PASSWORD", "")
    cache_path: Path = ROOT_DIR / os.getenv("WLM_CACHE_PATH", "data/studio_cache.sqlite3")
    request_timeout: float = float(os.getenv("WLM_REQUEST_TIMEOUT", "5"))


def ensure_dirs() -> None:
    (ROOT_DIR / "data").mkdir(parents=True, exist_ok=True)
    (ROOT_DIR / "exports").mkdir(parents=True, exist_ok=True)
