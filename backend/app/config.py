from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env by absolute path so it loads regardless of the working directory
# (uvicorn from backend/ vs repo root). A backend/.env overrides the repo-root
# one. In Docker these files are absent and env vars are injected directly.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILES = (str(_REPO_ROOT / ".env"), str(_BACKEND_DIR / ".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, extra="ignore")

    # --- AI (Google Gemini) ---------------------------------------------
    # Free-tier DAILY request quotas differ wildly per model:
    #   gemini-2.0-flash / 2.0-flash-lite -> 0 (no free quota)
    #   gemini-2.5-flash                  -> 20/day (too low for real use)
    #   gemini-2.5-flash-lite             -> ~1000/day (the sweet spot)
    # So we default to flash-lite. If billing is enabled, gemini-2.5-flash is a
    # quality upgrade — set GEMINI_MODEL=gemini-2.5-flash.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768

    # When the API is rate-limited or no key is set, the app degrades to a
    # deterministic heuristic engine instead of crashing. demo_mode forces it.
    demo_mode: bool = False

    # --- Rate-limit handling (free tier is ~10-15 RPM) ------------------
    # Cap concurrent Gemini calls and retry 429s with exponential backoff so a
    # 20+ CV batch completes under 60s without tripping the quota.
    max_concurrency: int = 4
    max_retries: int = 5
    retry_base_delay: float = 1.5

    # --- Pipeline tuning ------------------------------------------------
    # Bigger batches => fewer LLM calls => fits the tiny free-tier daily quota
    # (~20 generate req/day/model). A 25-CV run lands at ~7 calls.
    cv_parse_batch_size: int = 8   # CVs parsed per LLM call
    explain_batch_size: int = 6    # candidates explained per LLM call
    shortlist_size: int = 10       # candidates given a full LLM explanation

    # --- Server ---------------------------------------------------------
    cors_origins: str = "http://localhost:3000"
    cors_origin_regex: str = ""
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 10

    @property
    def use_real_ai(self) -> bool:
        return bool(self.gemini_api_key) and not self.demo_mode

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
