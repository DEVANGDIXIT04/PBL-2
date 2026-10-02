"""Environment-backed settings. Secrets come from the environment, never from code."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the API and ML jobs."""

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "Smart Personal Finance Tracker"
    database_url: str = "postgresql+psycopg://pfm:pfm@localhost:5432/pfm"
    secret_key: str = "dev-only-change-me"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cors_origins: str = "http://localhost:3000"
    rate_limit_enabled: bool = True
    rate_limit_auth: int = 10
    rate_limit_window_seconds: int = 60
    enable_scheduler: bool = False
    model_dir: str = "models"
    log_level: str = "INFO"
    bcrypt_rounds: int = 12
    demo_email: str = "demo@example.com"
    demo_password: str = "Demo1234!"
    min_user_transactions: int = 50

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings object."""
    return Settings()
