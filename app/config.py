import logging
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_DEV_JWT_SECRET = "dev-insecure-secret-change-me"


class Settings(BaseSettings):
    """Runtime configuration, read from the environment or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="TAWI_", extra="ignore")

    environment: Literal["local", "ci", "staging", "production"] = "local"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Postgres. The default matches docker-compose.yml exactly so `docker compose up db`
    # is the only setup a fresh clone needs.
    database_url: str = "postgresql+asyncpg://tawi:tawi@127.0.0.1:5433/tawi"

    # Access tokens are short-lived JWTs; refresh tokens are opaque strings stored hashed.
    jwt_secret: str = _DEV_JWT_SECRET
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60

    # Pairing codes a listener hands to a caregiver/therapist to authorise linking.
    pairing_code_ttl_seconds: int = 15 * 60

    def validate_runtime(self) -> None:
        """Refuse to run with the development JWT secret anywhere but local/ci."""
        if self.jwt_secret == _DEV_JWT_SECRET and self.environment not in {"local", "ci"}:
            raise RuntimeError(
                "TAWI_JWT_SECRET is still the development default. "
                "Set a real secret before running outside local/ci."
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
