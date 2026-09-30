"""Application configuration loaded from environment variables / .env files."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

logger = logging.getLogger(__name__)

DEFAULT_SECRET = "change-me-in-production-please-use-a-long-random-string"  # noqa: S105 - placeholder, rejected in prod


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ---- App ----
    APP_NAME: str = "AutoApply AI"
    ENVIRONMENT: str = "development"  # development | test | production
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    API_PREFIX: str = "/api/v1"
    FRONTEND_URL: str = "http://localhost:3000"
    PUBLIC_API_URL: str = "http://localhost:8000"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    ALLOW_REGISTRATION: bool = True

    # ---- Security ----
    SECRET_KEY: str = DEFAULT_SECRET
    ENCRYPTION_KEY: str | None = None  # base64 (urlsafe) encoded 32-byte key for AES-256-GCM
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    EXTENSION_TOKEN_EXPIRE_DAYS: int = 180
    COOKIE_NAME: str = "autoapply_session"
    COOKIE_SECURE: bool = False
    RATE_LIMIT_DEFAULT: str = "300/minute"

    # ---- Database / cache ----
    DATABASE_URL: str = "postgresql+psycopg://autoapply:autoapply@localhost:5432/autoapply"
    DB_POOL_SIZE: int = 10
    DB_CONNECT_RETRIES: int = 5
    REDIS_URL: str | None = "redis://localhost:6379/0"

    # ---- Celery ----
    CELERY_BROKER_URL: str | None = None  # defaults to REDIS_URL
    CELERY_RESULT_BACKEND: str | None = None
    CELERY_TASK_ALWAYS_EAGER: bool = False  # run tasks inline (no worker needed)

    # ---- LLM ----
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-opus-5-5"
    ANTHROPIC_EFFORT: str = "medium"  # low | medium | high | xhigh | max
    ANTHROPIC_REFUSAL_FALLBACK: bool = True  # server-side `fallbacks: "default"`
    ANTHROPIC_MAX_TOKENS: int = 32000
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MAX_RETRIES: int = 3
    LLM_TIMEOUT_SECONDS: float = 300.0
    EMBEDDING_PROVIDER: str = "local"  # local | openai
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536

    # ---- Google OAuth / Gmail / Calendar ----
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None  # defaults to {FRONTEND_URL}{API_PREFIX}/auth/google/callback
    GMAIL_PUBSUB_TOPIC: str | None = None  # projects/<project>/topics/<topic> for push notifications
    GMAIL_PUBSUB_VERIFICATION_TOKEN: str | None = None
    GMAIL_LOOKBACK_DAYS: int = 14

    # ---- Storage ----
    STORAGE_BACKEND: str = "local"  # local | s3
    LOCAL_STORAGE_PATH: str = str(BACKEND_DIR / "data" / "storage")
    S3_BUCKET: str | None = None
    S3_ENDPOINT_URL: str | None = None  # set for Cloudflare R2 / MinIO
    S3_REGION: str = "auto"
    S3_ACCESS_KEY_ID: str | None = None
    S3_SECRET_ACCESS_KEY: str | None = None

    # ---- Browser automation ----
    BROWSER_HEADLESS: bool = True
    PLAYWRIGHT_CHROMIUM_EXECUTABLE: str | None = None
    BROWSER_TIMEOUT_MS: int = 30000
    HUMAN_EMULATION: bool = True
    PROXY_URLS: str = ""  # comma-separated http://user:pass@host:port (e.g. BrightData / Oxylabs)
    CAPTCHA_PROVIDER: str = "2captcha"
    CAPTCHA_API_KEY: str | None = None
    SUBMISSION_DRY_RUN: bool = False  # when true, the final "Submit" click is never performed
    SCREENSHOT_FULL_PAGE: bool = True

    # ---- Agent behaviour ----
    SCAN_INTERVAL_HOURS: int = 3
    EMAIL_POLL_MINUTES: int = 5
    MAX_JOBS_PER_SOURCE: int = 50
    MAX_LLM_EVALUATIONS_PER_SCAN: int = 40
    AUTO_STAGE_APPLICATIONS: bool = True  # fill forms automatically after preparation
    DATA_RETENTION_DAYS: int = 730

    # ---- Notifications ----
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str = "AutoApply AI <no-reply@example.com>"
    SMTP_STARTTLS: bool = True
    DISCORD_WEBHOOK_URL: str | None = None
    SLACK_WEBHOOK_URL: str | None = None

    # ---- Monitoring ----
    SENTRY_DSN: str | None = None

    # ---- Paths ----
    PROMPTS_DIR: str = Field(default_factory=lambda: str(REPO_ROOT / "prompts"))

    # ---------------------------------------------------------------- helpers
    @property
    def cors_origins(self) -> list[str]:
        return _csv(self.CORS_ORIGINS)

    @property
    def proxy_urls(self) -> list[str]:
        return _csv(self.PROXY_URLS)

    @property
    def celery_broker(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL or "memory://"

    @property
    def celery_backend(self) -> str | None:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    @property
    def google_redirect_uri(self) -> str:
        # Default: through the dashboard's same-origin /api proxy so the session cookie is first-party.
        return self.GOOGLE_REDIRECT_URI or f"{self.FRONTEND_URL.rstrip('/')}{self.API_PREFIX}/auth/google/callback"

    @property
    def google_configured(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    def validate_for_production(self) -> list[str]:
        """Return a list of configuration problems that must be fixed before production use."""
        problems: list[str] = []
        if self.SECRET_KEY == DEFAULT_SECRET or len(self.SECRET_KEY) < 32:
            problems.append("SECRET_KEY must be set to a random string of at least 32 characters")
        if not self.ENCRYPTION_KEY:
            problems.append("ENCRYPTION_KEY must be set (python -c \"import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())\")")
        if not self.COOKIE_SECURE:
            problems.append("COOKIE_SECURE should be true when served over HTTPS")
        return problems


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production:
        for problem in settings.validate_for_production():
            logger.warning("CONFIG: %s", problem)
    return settings


settings = get_settings()
