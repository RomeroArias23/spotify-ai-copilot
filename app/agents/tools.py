from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field

from app.agents.context import ToolContext

# ---------- Tool argument schemas ----------

class GetMeArgs(BaseModel):
    """No arguments — returns the current user's profile."""


class GetTopTracksArgs(BaseModel):
    limit: int = Field(10, ge=1, le=50, description="Number of tracks to return")
    time_range: Literal["short_term", "medium_term", "long_term"] = Field(
        "medium_term",
        description="short_term≈last 4 weeks, medium_term≈last 6 months, long_term=all time",
    )


class SearchTracksArgs(BaseModel):
    query: str = Field(..., description="Spotify search query (artist, track, or both)")
    limit: int = Field(10, ge=1, le=50)


# ---------- Tool implementations ----------

async def tool_get_me(args: GetMeArgs, ctx: ToolContext) -> dict:
    user = await ctx.spotify.get_me(ctx.user_id)
    return user.model_dump()


async def tool_get_top_tracks(args: GetTopTracksArgs, ctx: ToolContext) -> dict:
    tracks = await ctx.spotify.get_top_tracks(
        ctx.user_id, limit=args.limit, time_range=args.time_range
    )
    return {"tracks": [t.model_dump() for t in tracks]}


async def tool_search_tracks(args: SearchTracksArgs, ctx: ToolContext) -> dict:
    # We'll add this method to SpotifyAPI in a moment.
    tracks = await ctx.spotify.search_tracks(ctx.user_id, query=args.query, limit=args.limit)
    return {"tracks": [t.model_dump() for t in tracks]}


# ---------- Tool registry ----------

class Tool(BaseModel):
    name: str
    description: str
    args_schema: type[BaseModel]
    handler: Callable[[Any, ToolContext], Awaitable[dict]]

    model_config = {"arbitrary_types_allowed": True}

    def to_anthropic_schema(self) -> dict:
        """Shape Anthropic's tool-use API expects."""
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
]

TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in TOOLS}