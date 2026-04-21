from typing import Protocol
from dataclasses import dataclass, asdict
import time


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str | None
    expires_at: float  # epoch seconds

    @property
    def is_expired(self) -> bool:
        # 60s safety buffer
        return time.time() > (self.expires_at - 60)


class TokenStore(Protocol):
    async def get(self, user_id: str) -> TokenBundle | None: ...
    async def set(self, user_id: str, tokens: TokenBundle) -> None: ...
    async def delete(self, user_id: str) -> None: ...


class InMemoryTokenStore:
    def __init__(self) -> None:
        self._data: dict[str, TokenBundle] = {}

    async def get(self, user_id: str) -> TokenBundle | None:
        return self._data.get(user_id)

    async def set(self, user_id: str, tokens: TokenBundle) -> None:
        self._data[user_id] = tokens

    async def delete(self, user_id: str) -> None:
        self._data.pop(user_id, None)