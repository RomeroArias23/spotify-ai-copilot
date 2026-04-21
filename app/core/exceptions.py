class SpotifyError(Exception):
    """Base Spotify-related error."""


class SpotifyAuthError(SpotifyError):
    """User is not authenticated or token exchange failed."""


class SpotifyAPIError(SpotifyError):
    def __init__(self, status_code: int, message: str, spotify_error: dict | None = None):
        self.status_code = status_code
        self.message = message
        self.spotify_error = spotify_error or {}
        super().__init__(f"Spotify API {status_code}: {message}")