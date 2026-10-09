"""Application configuration using pydantic-settings."""

from __future__ import annotations

import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    DATABASE_URL: str = "sqlite:///./release_board.db"
    SECRET_KEY: str = secrets.token_urlsafe(32)

    APP_ENV: str = "development"
    COOKIE_SECURE: bool = True
    FRONTEND_URL: str = "http://127.0.0.1:5173"
    OIDC_REDIRECT_URI: str = "http://127.0.0.1:5173/api/auth/callback"
    OIDC_ROLE_CLAIM: str = "realm_access.roles"
    DEMO_MODE: bool = False
    DEMO_BIND_HOST: str = "127.0.0.1"

    OIDC_ISSUER_URL: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_AUDIENCE: str = ""

    LLM_API_KEY: str = ""
    LLM_PROVIDER: str = "auto"
    LLM_MODEL: str = ""
    LLM_BASE_URL: str = ""

    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("DEMO_BIND_HOST")
    @classmethod
    def validate_demo_host(cls, v: str, info) -> str:
        return v

    def check_demo_safety(self) -> None:
        """Refuse demo mode when not bound to localhost."""
        if self.DEMO_MODE and self.APP_ENV=="production":
            raise ValueError("Demo mode is forbidden in production")
        if self.DEMO_MODE and self.DEMO_BIND_HOST not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(
                "DEMO_MODE=true is only allowed when DEMO_BIND_HOST is 127.0.0.1 or localhost. "
                "Refusing to start demo mode in production."
            )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    settings = Settings()
    settings.check_demo_safety()
    return settings
