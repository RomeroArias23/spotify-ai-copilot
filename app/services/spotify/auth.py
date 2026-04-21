import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.core.exceptions import SpotifyAuthError
from app.services.token_store import TokenBundle, TokenStore

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"


class SpotifyAuth:
    def __init__(self, settings: Settings, token_store: TokenStore):
        self._s = settings
        self._tokens = token_store
        # state -> {code_verifier, created_at}. In prod: Redis with TTL.
        self._pending: dict[str, dict] = {}

    def build_authorize_url(self) -> tuple[str, str]:
        """Returns (url, state). Caller must store state in session cookie."""
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

        self._pending[state] = {"verifier": verifier, "created_at": time.time()}

        params = {
            "client_id": self._s.spotify_client_id,
            "response_type": "code",
            "redirect_uri": self._s.spotify_redirect_uri,
            "scope": self._s.spotify_scopes,
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
        }
        return f"{AUTH_URL}?{urlencode(params)}", state

    async def exchange_code(self, user_id: str, code: str, state: str) -> TokenBundle:
        pending = self._pending.pop(state, None)
        if not pending:
            raise SpotifyAuthError("Invalid or expired state")
        if time.time() - pending["created_at"] > 600:  # 10 min
            raise SpotifyAuthError("State expired")

        data = {
            "client_id": self._s.spotify_client_id,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._s.spotify_redirect_uri,
            "code_verifier": pending["verifier"],
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(TOKEN_URL, data=data)

        if resp.status_code != 200:
            raise SpotifyAuthError(f"Token exchange failed: {resp.text}")

        td = resp.json()
        bundle = TokenBundle(
            access_token=td["access_token"],
            refresh_token=td.get("refresh_token"),
            expires_at=time.time() + td["expires_in"],
        )
        await self._tokens.set(user_id, bundle)
        return bundle

    async def get_valid_access_token(self, user_id: str) -> str:
        bundle = await self._tokens.get(user_id)
        if not bundle:
            raise SpotifyAuthError("User not authenticated")
        if bundle.is_expired:
            bundle = await self._refresh(user_id, bundle)
        return bundle.access_token

    async def _refresh(self, user_id: str, bundle: TokenBundle) -> TokenBundle:
        if not bundle.refresh_token:
            raise SpotifyAuthError("No refresh token available")

        data = {
            "client_id": self._s.spotify_client_id,
            "grant_type": "refresh_token",
            "refresh_token": bundle.refresh_token,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(TOKEN_URL, data=data)

        if resp.status_code != 200:
            raise SpotifyAuthError(f"Token refresh failed: {resp.text}")

        td = resp.json()
        new_bundle = TokenBundle(
            access_token=td["access_token"],
            # Spotify may or may not return a new refresh token
            refresh_token=td.get("refresh_token") or bundle.refresh_token,
            expires_at=time.time() + td["expires_in"],
        )
        await self._tokens.set(user_id, new_bundle)
        return new_bundle