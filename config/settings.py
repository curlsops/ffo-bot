"""Application settings and configuration."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Environment
    environment: str = Field(default="production", description="Environment name")

    # Discord Configuration
    discord_bot_token: str = Field(..., description="Discord bot token")
    discord_public_key: str = Field(..., description="Discord public key for webhook verification")

    # Database Configuration
    database_url: str = Field(..., description="PostgreSQL connection URL")
    db_pool_min_size: int = Field(default=5, description="Minimum database pool size")
    db_pool_max_size: int = Field(default=20, description="Maximum database pool size")

    # Media Storage
    media_storage_path: str = Field(default="/media", description="Base path for media storage")
    media_max_file_size: int = Field(
        default=104857600, description="Max file size in bytes (100MB)"
    )

    # Cache Configuration
    cache_max_size: int = Field(default=10000, description="Maximum cache entries")
    cache_default_ttl: int = Field(default=300, description="Default cache TTL in seconds")

    # Rate Limiting
    rate_limit_user_capacity: int = Field(default=10, description="User rate limit capacity")
    rate_limit_server_capacity: int = Field(default=100, description="Server rate limit capacity")

    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format (json or text)")

    # Health Check
    health_check_port: int = Field(default=8080, description="Health check HTTP port")

    # Graceful Shutdown
    shutdown_timeout_seconds: int = Field(default=30, description="Graceful shutdown timeout")

    # Feature Flags
    feature_media_download: bool = Field(default=True, description="Enable media download")
    feature_reaction_roles: bool = Field(default=True, description="Enable reaction roles")
    feature_rotating_status: bool = Field(default=False, description="Enable rotating status")
    feature_giveaways: bool = Field(default=True, description="Enable giveaway system")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v_upper

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        valid_formats = ["json", "text"]
        v_lower = v.lower()
        if v_lower not in valid_formats:
            raise ValueError(f"Log format must be one of {valid_formats}")
        return v_lower

    @field_validator("media_storage_path")
    @classmethod
    def validate_storage_path(cls, v: str) -> str:
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return str(path.absolute())
