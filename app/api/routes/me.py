from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_spotify_api, get_current_user_id
from app.core.exceptions import SpotifyAuthError, SpotifyAPIError
from app.services.spotify.api import SpotifyAPI, SpotifyUser, Track

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=SpotifyUser)
async def me(
    user_id: str = Depends(get_current_user_id),
    api: SpotifyAPI = Depends(get_spotify_api),
):
    try:
        return await api.get_me(user_id)
    except SpotifyAuthError as e:
        raise HTTPException(401, f"Not authenticated: {e}")
    except SpotifyAPIError as e:
        raise HTTPException(e.status_code, e.message)


@router.get("/top-tracks", response_model=list[Track])
async def top_tracks(
    limit: int = Query(10, ge=1, le=50),
    time_range: Literal["short_term", "medium_term", "long_term"] = "medium_term",
    user_id: str = Depends(get_current_user_id),
    api: SpotifyAPI = Depends(get_spotify_api),
):
    try:
        return await api.get_top_tracks(user_id, limit=limit, time_range=time_range)
    except SpotifyAuthError as e:
        raise HTTPException(401, f"Not authenticated: {e}")
    except SpotifyAPIError as e:
        raise HTTPException(e.status_code, e.message)