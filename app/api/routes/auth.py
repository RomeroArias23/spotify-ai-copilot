import time
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

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