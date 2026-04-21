from functools import lru_cache
from fastapi import Depends

from app.config import Settings, get_settings
from app.services.token_store import InMemoryTokenStore, TokenStore
from app.services.spotify.auth import SpotifyAuth


@lru_cache
def get_token_store() -> TokenStore:
    return InMemoryTokenStore()


@lru_cache
def _build_spotify_auth() -> SpotifyAuth:
    return SpotifyAuth(get_settings(), get_token_store())


def get_spotify_auth(
    settings: Settings = Depends(get_settings),
    store: TokenStore = Depends(get_token_store),
) -> SpotifyAuth:
    # settings/store are unused at call time — kept as Depends to preserve the
    # DI shape in case you later swap implementations per-request.
    return _build_spotify_auth()


def get_current_user_id() -> str:
    """Dev fallback — single user. Replace with real session/JWT auth later."""
    return "test_user"