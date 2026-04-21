import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.exceptions import SpotifyAPIError, SpotifyAuthError
from app.services.spotify.auth import SpotifyAuth

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.spotify.com/v1"
DEFAULT_TIMEOUT = 10.0
MAX_RATE_LIMIT_RETRIES = 3


class SpotifyClient:
    """Async HTTP client for the Spotify Web API.

    Responsibilities:
      - Fetches a valid access token via SpotifyAuth.
      - Handles 401 by forcing a token refresh and retrying once.
      - Handles 429 with bounded backoff honoring Retry-After.
      - Raises typed SpotifyAPIError for other 4xx/5xx responses.
    """

    def __init__(self, auth: SpotifyAuth):
        self._auth = auth

    async def request(
        self,
        user_id: str,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Execute a Spotify API request. Returns parsed JSON or None for 204."""
        url = f"{API_BASE_URL}{endpoint}"

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as http:
            return await self._request_with_retries(
                http, user_id, method, url, params=params, json=json
            )

    async def _request_with_retries(
        self,
        http: httpx.AsyncClient,
        user_id: str,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None,
        json: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        refreshed_once = False

        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            token = await self._auth.get_valid_access_token(user_id)
            headers = {"Authorization": f"Bearer {token}"}

            start = time.monotonic()
            resp = await http.request(
                method, url, headers=headers, params=params, json=json
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "spotify_request",
                extra={
                    "method": method,
                    "url": url,
                    "status": resp.status_code,
                    "latency_ms": latency_ms,
                    "attempt": attempt,
                },
            )

            # 401: token went stale between our check and the API hitting it.
            # Force a refresh and retry once.
            if resp.status_code == 401 and not refreshed_once:
                logger.warning("spotify_401_forcing_refresh", extra={"user_id": user_id})
                await self._force_refresh(user_id)
                refreshed_once = True
                continue

            # 429: respect Retry-After, up to MAX_RATE_LIMIT_RETRIES times.
            if resp.status_code == 429 and attempt < MAX_RATE_LIMIT_RETRIES:
                retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                logger.warning(
                    "spotify_429_backoff",
                    extra={"retry_after": retry_after, "attempt": attempt},
                )
                await asyncio.sleep(retry_after)
                continue

            if resp.status_code >= 400:
                raise _build_api_error(resp)

            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()

        # Exhausted retries on 429
        raise SpotifyAPIError(429, "Rate limited after retries")

    async def _force_refresh(self, user_id: str) -> None:
        """Invalidate the current token so the next get_valid_access_token refreshes."""
        bundle = await self._auth._tokens.get(user_id)
        if bundle is None:
            raise SpotifyAuthError("No tokens to refresh")
        # Mark it expired; get_valid_access_token will now refresh on next call.
        bundle.expires_at = 0
        await self._auth._tokens.set(user_id, bundle)


def _parse_retry_after(value: str | None) -> float:
    if not value:
        return 1.0
    try:
        return max(0.0, float(value))
    except ValueError:
        return 1.0


def _build_api_error(resp: httpx.Response) -> SpotifyAPIError:
    try:
        payload = resp.json()
        msg = payload.get("error", {}).get("message", "Unknown error")
    except Exception:
        payload = {}
        msg = resp.text or "Unknown error"
    return SpotifyAPIError(resp.status_code, msg, payload)