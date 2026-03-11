from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _build_database_url(host: str, port: int, name: str, user: str, password: Optional[str]) -> str:
    pw = quote_plus(password) if password else ""
    return f"postgresql://{user}:{pw}@{host}:{port}/{name}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    environment: str = Field(default="production", description="Environment name")
    openai_api_key: Optional[str] = Field(
        default=None, description="OpenAI API key for voice transcription"
    )

    discord_bot_token: str = Field(..., description="Discord bot token")
    discord_public_key: str = Field(..., description="Discord public key for webhook verification")

    database_url: Optional[str] = Field(
        default=None,
        description="PostgreSQL connection URL (or use DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD)",
    )
    db_host: Optional[str] = Field(
        default=None, description="Database host (when not using DATABASE_URL)"
    )
    db_port: int = Field(default=5432, description="Database port (when not using DATABASE_URL)")
    db_name: Optional[str] = Field(
        default=None, description="Database name (when not using DATABASE_URL)"
    )
    db_user: Optional[str] = Field(
        default=None, description="Database user (when not using DATABASE_URL)"
    )
    db_password: Optional[str] = Field(
        default=None, description="Database password (when not using DATABASE_URL)"
    )
    db_pool_min_size: int = Field(default=5, description="Minimum database pool size")
    db_pool_max_size: int = Field(default=20, description="Maximum database pool size")
    db_connection_timeout: float = Field(
        default=10.0, description="Timeout in seconds for establishing new DB connections"
    )
    db_acquire_timeout: float = Field(
        default=5.0, description="Timeout in seconds for acquiring a connection from the pool"
    )

    media_storage_path: str = Field(default="/media", description="Base path for media storage")
    media_max_file_size: int = Field(
        default=104857600, description="Max file size in bytes (100MB)"
    )

    cache_max_size: int = Field(default=10000, description="Maximum cache entries")
    cache_max_memory_mb: float = Field(
        default=0.0,
        description="Maximum cache memory in MB (0=unlimited). Evicts proactively when approaching limit.",
    )
    cache_default_ttl: int = Field(
        default=86400,
        description="Default cache TTL in seconds (24h). Eviction is by memory/count limits, not TTL.",
    )

    rate_limit_user_capacity: int = Field(default=10, description="User rate limit capacity")
    rate_limit_server_capacity: int = Field(default=100, description="Server rate limit capacity")

    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format (json or text)")

    health_check_port: int = Field(default=8080, description="Health check HTTP port")
    interactions_endpoint_enabled: bool = Field(
        default=False,
        description="Enable /interactions HTTP endpoint for Discord Interactions Endpoint URL",
    )

    shutdown_timeout_seconds: int = Field(default=30, description="Graceful shutdown timeout")

    feature_media_download: bool = Field(default=True, description="Enable media download")
    feature_reaction_roles: bool = Field(default=True, description="Enable reaction roles")
    feature_rotating_status: bool = Field(default=False, description="Enable rotating status")
    feature_giveaways: bool = Field(default=True, description="Enable giveaway system")
    feature_voice_transcription: bool = Field(
        default=False, description="Transcribe voice messages (requires OPENAI_API_KEY)"
    )
    feature_quotebook: bool = Field(default=True, description="Enable quotebook submissions")
    feature_conversion: bool = Field(
        default=False, description="Auto currency/measurement conversion"
    )
    feature_minecraft_whitelist: bool = Field(
        default=False, description="Enable Minecraft whitelist via RCON"
    )
    feature_faq: bool = Field(default=True, description="Enable FAQ commands")
    feature_faq_submissions: bool = Field(
        default=True, description="Allow users to submit FAQ questions for admins"
    )
    feature_notify_moderation: bool = Field(default=True, description="Notify on moderation events")
    feature_notify_rate_limit: bool = Field(
        default=False, description="Notify when users hit rate limit (can be noisy)"
    )
    bot_owner_server_id: Optional[int] = Field(
        default=None,
        description="Server ID for owner notifications (e.g. bot added to new server)",
    )
    bot_owner_notify_channel_id: Optional[int] = Field(
        default=None,
        description="Channel ID in bot_owner_server_id for owner notifications",
    )

    feature_anonymous_post: bool = Field(
        default=False,
        description="Enable anonymous post button with modal and anonymization",
    )
    feature_music: bool = Field(
        default=False, description="Enable music commands (requires Lavalink)"
    )
    lavalink_host: Optional[str] = Field(default="127.0.0.1", description="Lavalink server host")
    lavalink_port: int = Field(default=2333, description="Lavalink server port")
    lavalink_password: Optional[str] = Field(default=None, description="Lavalink server password")
    spotify_client_id: Optional[str] = Field(
        default=None,
        description="Spotify app client ID for playlist support (SPOTIFY_CLIENT_ID env)",
    )
    spotify_client_secret: Optional[str] = Field(
        default=None,
        description="Spotify app client secret for playlist support (SPOTIFY_CLIENT_SECRET env)",
    )
    minecraft_rcon_host: Optional[str] = Field(
        default=None, description="Minecraft server host for RCON"
    )
    minecraft_rcon_port: int = Field(default=25575, description="RCON port (default 25575)")
    minecraft_rcon_password: Optional[str] = Field(
        default=None, description="RCON password (from secret)"
    )

    @model_validator(mode="after")
    def resolve_database_url(self) -> "Settings":
        if self.database_url:
            return self
        if self.db_host and self.db_name and self.db_user is not None:
            url = _build_database_url(
                self.db_host, self.db_port, self.db_name, self.db_user, self.db_password
            )
            object.__setattr__(self, "database_url", url)
            return self
        raise ValueError(
            "Provide DATABASE_URL or all of DB_HOST, DB_NAME, DB_USER (and optionally DB_PORT, DB_PASSWORD)"
        )

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
