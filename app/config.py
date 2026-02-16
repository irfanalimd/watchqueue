"""Configuration settings for WatchQueue."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # MongoDB settings
    mongodb_url: str = "mongodb://localhost:27017,localhost:27018,localhost:27019/?replicaSet=rs0"
    mongodb_database: str = "watchqueue"

    # TMDB API settings
    tmdb_api_key: str = ""
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    default_region: str = "US"
    google_client_id: str = ""
    auth_session_ttl_seconds: int = 60 * 60 * 24 * 30

    # Application settings
    app_name: str = "WatchQueue"
    debug: bool = False

    # Room settings
    default_voting_duration: int = 60
    room_code_length: int = 6

    # WebSocket settings
    ws_heartbeat_interval: int = 30

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
