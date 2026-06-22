from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path

# Resolve .env by absolute path so it loads no matter what the working
# directory is (e.g. running uvicorn from backend/ vs the repo root).
# A backend/.env, if present, overrides the repo-root .env. Inside Docker
# these files are absent and env vars are injected directly — both are fine.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILES = (str(_REPO_ROOT / ".env"), str(_BACKEND_DIR / ".env"))


class Settings(BaseSettings):
    # No database: the app stores everything in an in-memory SQLite engine
    # (see app/database.py). There is no DATABASE_URL / Postgres anymore.
    gemini_api_key: str = ""
    demo_mode: bool = True
    cors_origins: str = "http://localhost:3000"
    # Optional regex for additional allowed origins, e.g. Vercel preview URLs:
    #   CORS_ORIGIN_REGEX=https://.*\.vercel\.app
    cors_origin_regex: str = ""
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 10
    rate_limit_per_minute: int = 60
    gemini_model: str = "gemini-2.0-flash"
    embedding_model: str = "gemini-embedding-001"

    @property
    def use_mock_ai(self) -> bool:
        return self.demo_mode and not self.gemini_api_key

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    class Config:
        env_file = _ENV_FILES
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
