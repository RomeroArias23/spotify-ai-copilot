"""
Spotify Web API client — business methods.

This is the layer that exposes Spotify endpoints as typed Python methods.
Keeping responses as Pydantic models (rather than raw dicts) gives us:
  - Free JSON Schema generation (used by the AI agent's tool registry).
  - Compile-time-ish safety: the agent can't reference a field that doesn't exist.
  - A natural place to evolve the response shape without touching every caller.

All HTTP concerns (auth, retries, rate limiting) live one layer below in client.py.
"""

from typing import Literal

from pydantic import BaseModel

from app.services.spotify.client import SpotifyClient

TimeRange = Literal["short_term", "medium_term", "long_term"]


# ---------- Response models ----------

class SpotifyUser(BaseModel):
    id: str
    display_name: str | None = None
    email: str | None = None
    country: str | None = None


class Artist(BaseModel):
    id: str
    name: str


class Track(BaseModel):
    id: str
    name: str
    uri: str  # e.g. "spotify:track:6rqhFgbbKwnb9MLmUQDhG6" — required to add to playlists
    artists: list[Artist]
    album_name: str | None = None
    popularity: int | None = None


class Playlist(BaseModel):
    """Returned by create_playlist. Mirrors the subset of Spotify's playlist object we care about."""
    id: str
    name: str
    description: str | None = None
    url: str  # Spotify share URL — the thing we actually surface to the user
    track_count: int = 0


# ---------- API surface ----------

class SpotifyAPI:
    """Thin facade over Spotify endpoints. One method per logical operation."""

    def __init__(self, client: SpotifyClient):
        self._c = client

    # ----- READ methods -----

    async def get_me(self, user_id: str) -> SpotifyUser:
        data = await self._c.request(user_id, "GET", "/me")
        return SpotifyUser(
            id=data["id"],
            display_name=data.get("display_name"),
            email=data.get("email"),
            country=data.get("country"),
        )

    async def get_top_tracks(
        self,
        user_id: str,
        *,
        limit: int = 10,
        time_range: TimeRange = "medium_term",
    ) -> list[Track]:
        data = await self._c.request(
            user_id,
            "GET",
            "/me/top/tracks",
            params={"limit": limit, "time_range": time_range},
        )
        return [_parse_track(item) for item in data.get("items", [])]

    async def search_tracks(
        self, user_id: str, *, query: str, limit: int = 20
    ) -> list[Track]:
        data = await self._c.request(
            user_id,
            "GET",
            "/search",
            params={"q": query, "type": "track", "limit": str(limit)},  # explicit str cast
        )
        items = data.get("tracks", {}).get("items", [])
        return [_parse_track(item) for item in items]

    # ----- WRITE methods (NEW in step A) -----

    async def create_playlist(
        self,
        user_id: str,
        *,
        spotify_user_id: str,
        name: str,
        description: str | None = None,
        public: bool = False,
    ) -> Playlist:
        """Create a new (empty) playlist on the user's account.

        Note: ``user_id`` is our internal user identifier (used to fetch the access token),
        while ``spotify_user_id`` is Spotify's ID for the same account (used in the URL path).
        We separate them because they conceptually represent different things — and once we
        add multi-user support, the mapping from user_id -> spotify_user_id will live in our DB.

        Defaults to private (public=False) — never silently make user content public.
        """
        body: dict = {"name": name, "public": public}
        if description:
            body["description"] = description

        data = await self._c.request(
            user_id,
            "POST",
            f"/users/{spotify_user_id}/playlists",
            json=body,
        )
        return Playlist(
            id=data["id"],
            name=data["name"],
            description=data.get("description"),
            url=data.get("external_urls", {}).get("spotify", ""),
            track_count=data.get("tracks", {}).get("total", 0),
        )

    async def add_tracks_to_playlist(
        self,
        user_id: str,
        *,
        playlist_id: str,
        track_uris: list[str],
    ) -> dict:
        """Add tracks to an existing playlist.

        Spotify's API caps each request at 100 URIs, so we chunk transparently.
        Callers (including the AI agent) don't need to know about this limit.

        Returns a small summary dict with the total added and the snapshot IDs from each chunk.
        Snapshot IDs are Spotify's optimistic-concurrency token; we don't use them today
        but they're useful if we later add 'undo' support.
        """
        if not track_uris:
            return {"added": 0, "snapshot_ids": []}

        snapshot_ids: list[str] = []
        for i in range(0, len(track_uris), 100):
            chunk = track_uris[i:i + 100]
            data = await self._c.request(
                user_id,
                "POST",
                f"/playlists/{playlist_id}/tracks",
                json={"uris": chunk},
            )
            if data and "snapshot_id" in data:
                snapshot_ids.append(data["snapshot_id"])

        return {"added": len(track_uris), "snapshot_ids": snapshot_ids}


# ---------- Helpers ----------

def _parse_track(item: dict) -> Track:
    return Track(
        id=item["id"],
        name=item["name"],
        uri=item["uri"],
        artists=[Artist(id=a["id"], name=a["name"]) for a in item.get("artists", [])],
        album_name=item.get("album", {}).get("name"),
        popularity=item.get("popularity"),
    )