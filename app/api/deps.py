from functools import lru_cache
from fastapi import Depends

from app.config import Settings, get_settings
from app.services.token_store import InMemoryTokenStore, TokenStore
from app.services.spotify.auth import SpotifyAuth
from app.services.spotify.client import SpotifyClient
from app.services.spotify.api import SpotifyAPI


@lru_cache
def get_token_store() -> TokenStore:
    return InMemoryTokenStore()


@lru_cache
def _build_spotify_auth() -> SpotifyAuth:
    return SpotifyAuth(get_settings(), get_token_store())


@lru_cache
def _build_spotify_client() -> SpotifyClient:
    return SpotifyClient(_build_spotify_auth())


@lru_cache
def _build_spotify_api() -> SpotifyAPI:
    return SpotifyAPI(_build_spotify_client())


def get_spotify_auth(
    settings: Settings = Depends(get_settings),
    store: TokenStore = Depends(get_token_store),
) -> SpotifyAuth:
    return _build_spotify_auth()


def get_spotify_api() -> SpotifyAPI:
    return _build_spotify_api()


def get_current_user_id() -> str:
    """Dev fallback — single user. Replace with real session/JWT auth later."""
    return "test_user"