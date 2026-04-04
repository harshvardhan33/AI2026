import asyncio
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from app.config import settings


@dataclass
class SessionToken:
    token: str
    file_id: str
    expires_at: float  # monotonic timestamp


class SessionStore:
    """
    In-memory store for short-lived reveal session tokens.

    Uses asyncio.Lock for safe concurrent access.
    time.monotonic() is used for TTL to avoid system clock jumps.
    """

    def __init__(self) -> None:
        self._store: dict[str, SessionToken] = {}
        self._lock = asyncio.Lock()

    async def create(self, file_id: str) -> str:
        """Mint a new token for file_id. Returns the token string."""
        token = secrets.token_urlsafe(32)  # 256 bits of URL-safe randomness
        session = SessionToken(
            token=token,
            file_id=file_id,
            expires_at=time.monotonic() + settings.TOKEN_TTL,
        )
        async with self._lock:
            self._store[token] = session
        return token

    async def get(self, token: str) -> Optional[SessionToken]:
        """Return session if token exists and has not expired, else None."""
        async with self._lock:
            session = self._store.get(token)
        if session is None:
            return None
        if time.monotonic() > session.expires_at:
            await self.revoke(token)
            return None
        return session

    async def revoke(self, token: str) -> bool:
        """Remove token. Returns True if it existed."""
        async with self._lock:
            return self._store.pop(token, None) is not None

    async def sweep_expired(self) -> int:
        """Remove all expired tokens. Returns count removed."""
        now = time.monotonic()
        async with self._lock:
            expired = [t for t, s in self._store.items() if now > s.expires_at]
            for t in expired:
                del self._store[t]
        return len(expired)


# Module-level singleton shared across all routers
session_store = SessionStore()


async def _sweep_loop() -> None:
    """Background coroutine: sweep expired sessions every 10 seconds."""
    while True:
        await asyncio.sleep(10)
        await session_store.sweep_expired()
