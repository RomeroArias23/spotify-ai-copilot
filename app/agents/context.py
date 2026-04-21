from dataclasses import dataclass

from app.services.spotify.api import SpotifyAPI


@dataclass
class ToolContext:
    """Passed to every tool invocation. Keeps tools stateless and testable."""
    user_id: str
    spotify: SpotifyAPI
