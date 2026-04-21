import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.context import ToolContext
from app.agents.copilot import Copilot
from app.api.deps import get_copilot, get_current_user_id, get_spotify_api
from app.services.spotify.api import SpotifyAPI

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ToolCallTrace(BaseModel):
    name: str
    input: dict
    output: dict


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallTrace]


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user_id: str = Depends(get_current_user_id),
    spotify: SpotifyAPI = Depends(get_spotify_api),
    copilot: Copilot = Depends(get_copilot),
):
    ctx = ToolContext(user_id=user_id, spotify=spotify)
    try:
        result = await copilot.chat(body.message, ctx)
    except Exception as e:
        logger.exception("copilot_chat_failed")
        raise HTTPException(500, f"{type(e).__name__}: {e}")
    return ChatResponse(**result)