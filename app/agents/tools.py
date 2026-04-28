"""
Tool registry for the Copilot agent.

Design principles:
  - One Pydantic model per tool argument schema. The LLM sees JSON Schema derived
    from these models, so editing the model = editing the contract.
  - Tools receive a ToolContext, not module-level globals. Makes them unit-testable
    without spinning up FastAPI.
  - Tools never hold state. Any state lives in services (token store, future DB).
"""

import re
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field, field_validator

from app.agents.context import ToolContext


# =========================================================================
# Argument schemas
# =========================================================================

class GetMeArgs(BaseModel):
    """No arguments — returns the current user's profile."""


class GetTopTracksArgs(BaseModel):
    limit: int = Field(10, ge=1, le=50, description="Number of tracks to return")
    time_range: Literal["short_term", "medium_term", "long_term"] = Field(
        "medium_term",
        description=(
            "short_term ~ last 4 weeks, "
            "medium_term ~ last 6 months, "
            "long_term = all time"
        ),
    )


class SearchTracksArgs(BaseModel):
    query: str = Field(..., description="Spotify search query (artist, track, or both)")
    limit: int = Field(
        20,
        ge=1,
        le=50,
        description="Number of results to return (1-50). Default 20.",
    )


class CreatePlaylistArgs(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Playlist name")
    description: str | None = Field(
        None, max_length=300, description="Optional description shown on Spotify"
    )
    public: bool = Field(
        False,
        description="Whether the playlist is public. Default false (private).",
    )


_TRACK_URI_RE = re.compile(r"^spotify:track:[A-Za-z0-9]+$")
_BARE_ID_RE = re.compile(r"^[A-Za-z0-9]+$")


class AddTracksToPlaylistArgs(BaseModel):
    playlist_id: str = Field(..., description="The Spotify playlist ID to add tracks to")
    track_uris: list[str] = Field(
        ...,
        min_length=1,
        max_length=200,
        description=(
            "List of Spotify track URIs in the form 'spotify:track:<id>'. "
            "These come from the 'uri' field of get_top_tracks or search_tracks results - "
            "do NOT pass the bare 'id' field."
        ),
    )

    @field_validator("track_uris", mode="before")
    @classmethod
    def normalize_uris(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        normalized = []
        for item in value:
            if not isinstance(item, str):
                normalized.append(item)
                continue
            if _TRACK_URI_RE.match(item):
                normalized.append(item)
            elif _BARE_ID_RE.match(item):
                normalized.append(f"spotify:track:{item}")
            else:
                normalized.append(item)
        return normalized


# =========================================================================
# Tool implementations
# =========================================================================

async def tool_get_me(args: GetMeArgs, ctx: ToolContext) -> dict:
    user = await ctx.spotify.get_me(ctx.user_id)
    return user.model_dump()


async def tool_get_top_tracks(args: GetTopTracksArgs, ctx: ToolContext) -> dict:
    tracks = await ctx.spotify.get_top_tracks(
        ctx.user_id, limit=args.limit, time_range=args.time_range
    )
    return {"tracks": [t.model_dump() for t in tracks]}


async def tool_search_tracks(args: SearchTracksArgs, ctx: ToolContext) -> dict:
    tracks = await ctx.spotify.search_tracks(
        ctx.user_id, query=args.query, limit=args.limit
    )
    return {"tracks": [t.model_dump() for t in tracks]}


async def tool_create_playlist(args: CreatePlaylistArgs, ctx: ToolContext) -> dict:
    me = await ctx.spotify.get_me(ctx.user_id)
    playlist = await ctx.spotify.create_playlist(
        ctx.user_id,
        spotify_user_id=me.id,
        name=args.name,
        description=args.description,
        public=args.public,
    )
    return playlist.model_dump()


async def tool_add_tracks_to_playlist(
    args: AddTracksToPlaylistArgs, ctx: ToolContext
) -> dict:
    return await ctx.spotify.add_tracks_to_playlist(
        ctx.user_id,
        playlist_id=args.playlist_id,
        track_uris=args.track_uris,
    )


# =========================================================================
# Tool wrapper + registry
# =========================================================================

class Tool(BaseModel):
    name: str
    description: str
    args_schema: type[BaseModel]
    handler: Callable[[Any, ToolContext], Awaitable[dict]]

    model_config = {"arbitrary_types_allowed": True}

    def to_anthropic_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.args_schema.model_json_schema(),
        }

    async def invoke(self, raw_args: dict, ctx: ToolContext) -> dict:
        args = self.args_schema.model_validate(raw_args)
        return await self.handler(args, ctx)


TOOLS: list[Tool] = [
    Tool(
        name="get_me",
        description="Get the current user's Spotify profile (id, display name, email, country).",
        args_schema=GetMeArgs,
        handler=tool_get_me,
    ),
    Tool(
        name="get_top_tracks",
        description=(
            "Get the user's top tracks over a time range. "
            "Use short_term for recent taste, long_term for all-time favorites."
        ),
        args_schema=GetTopTracksArgs,
        handler=tool_get_top_tracks,
    ),
    Tool(
        name="search_tracks",
        description="Search Spotify's catalog for tracks matching a query.",
        args_schema=SearchTracksArgs,
        handler=tool_search_tracks,
    ),
    Tool(
        name="create_playlist",
        description=(
            "Create a new EMPTY playlist on the user's account. "
            "Returns a playlist object with an 'id' - pass that id to add_tracks_to_playlist "
            "in a follow-up call to actually populate the playlist. "
            "Defaults to private; only set public=true when the user explicitly asks."
        ),
        args_schema=CreatePlaylistArgs,
        handler=tool_create_playlist,
    ),
    Tool(
        name="add_tracks_to_playlist",
        description=(
            "Add tracks to an existing playlist. "
            "track_uris must be Spotify URIs in the form 'spotify:track:<id>' - "
            "these come from the 'uri' field of get_top_tracks or search_tracks results, "
            "NOT the 'id' field. Call this AFTER create_playlist."
        ),
        args_schema=AddTracksToPlaylistArgs,
        handler=tool_add_tracks_to_playlist,
    ),
]

TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in TOOLS}
