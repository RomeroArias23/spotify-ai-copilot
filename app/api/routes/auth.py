import time
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
import httpx

from app.services.spotify.auth import SpotifyAuth
from app.core.exceptions import SpotifyAuthError
from app.api.deps import get_spotify_auth, get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login(auth: SpotifyAuth = Depends(get_spotify_auth)):
    url, state = auth.build_authorize_url()
    response = RedirectResponse(url)
    response.set_cookie(
        "spotify_oauth_state",
        state,
        httponly=True,
        max_age=600,
        samesite="lax",
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    auth: SpotifyAuth = Depends(get_spotify_auth),
    user_id: str = Depends(get_current_user_id),
):
    if error:
        raise HTTPException(400, f"Spotify returned error: {error}")
    if not code or not state:
        raise HTTPException(400, "Missing code or state")

    cookie_state = request.cookies.get("spotify_oauth_state")
    if not cookie_state or cookie_state != state:
        raise HTTPException(400, "State mismatch — possible CSRF")

    try:
        bundle = await auth.exchange_code(user_id, code, state)
    except SpotifyAuthError as e:
        logger.exception("Token exchange failed")
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("Unexpected error during token exchange")
        raise HTTPException(500, f"{type(e).__name__}: {e}")

    expires_in = max(0, int(bundle.expires_at - time.time()))
    return {"message": "Authenticated ✅", "expires_in": expires_in}

@router.get("/debug")
async def debug_token(
    auth: SpotifyAuth = Depends(get_spotify_auth),
    user_id: str = Depends(get_current_user_id),
):
    try:
        token = await auth.get_valid_access_token(user_id)
    except SpotifyAuthError as e:
        raise HTTPException(401, str(e))

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    results = {}

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Test 1: read /me (should work — sanity check)
        me_resp = await client.get("https://api.spotify.com/v1/me", headers=headers)
        results["read_me"] = {"status": me_resp.status_code}
        if me_resp.status_code != 200:
            results["read_me"]["body"] = me_resp.text
            return results

        spotify_user_id = me_resp.json()["id"]

        # Test 2: read user's playlists (no scope needed — public list)
        list_resp = await client.get(
            "https://api.spotify.com/v1/me/playlists",
            headers=headers,
            params={"limit": 1},
        )
        results["read_playlists"] = {"status": list_resp.status_code}

        # Test 3: write — create playlist
        create_resp = await client.post(
            f"https://api.spotify.com/v1/users/{spotify_user_id}/playlists",
            headers=headers,
            json={"name": "DEBUG", "public": False},
        )
        results["create_playlist"] = {
            "status": create_resp.status_code,
            "body": create_resp.text,
        }

        # Test 4: another write — follow an artist (uses user-follow-modify, but try anyway)
        follow_resp = await client.put(
            "https://api.spotify.com/v1/me/following",
            headers=headers,
            params={"type": "artist", "ids": "7Ln80lUS6He07XvHI8qqHH"},  # Arctic Monkeys
        )
        results["follow_artist"] = {
            "status": follow_resp.status_code,
            "body": follow_resp.text or "(empty body)",
        }

    return results