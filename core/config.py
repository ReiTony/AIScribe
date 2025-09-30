from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="LegalGenie API", alias="APP_NAME")
    environment: Literal["development", "staging", "production"] = Field(default="development", alias="ENVIRONMENT")
    database_url: str = Field(default="sqlite:///./app.db", alias="DATABASE_URL")
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")

    jwt_secret_key: str = Field(default="change-me", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"], alias="CORS_ALLOW_ORIGINS")
    cors_allow_credentials: bool = Field(default=True, alias="CORS_ALLOW_CREDENTIALS")
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"], alias="CORS_ALLOW_METHODS")
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"], alias="CORS_ALLOW_HEADERS")

    api_prefix: str = Field(default="/api", alias="API_PREFIX")
    docs_url: Optional[str] = Field(default="/docs", alias="DOCS_URL")
    redoc_url: Optional[str] = Field(default="/redoc", alias="REDOC_URL")


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings()  # type: ignore[call-arg]
