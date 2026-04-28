from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str = "http://127.0.0.1:8000/auth/callback"
    spotify_scopes: str = (
    "user-top-read user-read-private user-read-email "
    "playlist-read-private "
    "playlist-modify-public playlist-modify-private"
    )


    # Session secret for signing state/cookies
    session_secret: str

    # Where to store tokens
    token_store_backend: str = "memory"  # memory | redis
    redis_url: str | None = None

    anthropic_api_key: str


@lru_cache
def get_settings() -> Settings:
    return Settings()