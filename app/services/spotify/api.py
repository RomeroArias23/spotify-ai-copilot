from typing import Literal

from pydantic import BaseModel

from app.services.spotify.client import SpotifyClient

TimeRange = Literal["short_term", "medium_term", "long_term"]


# ---------- Pydantic response models ----------

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
    uri: str
    artists: list[Artist]
    album_name: str | None = None
    popularity: int | None = None


# ---------- API surface ----------

class SpotifyAPI:
    def __init__(self, client: SpotifyClient):
        self._c = client

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


def _parse_track(item: dict) -> Track:
    return Track(
        id=item["id"],
        name=item["name"],
        uri=item["uri"],
        artists=[Artist(id=a["id"], name=a["name"]) for a in item.get("artists", [])],
        album_name=item.get("album", {}).get("name"),
        popularity=item.get("popularity"),
    )