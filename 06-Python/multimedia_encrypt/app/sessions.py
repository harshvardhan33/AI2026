import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

from app.config import settings


@dataclass
class SessionToken:
    token:         str
    file_id:       str
    expires_at:    float        # monotonic timestamp
    started_at:    float = field(default_factory=time.monotonic)
    chunks_served: int   = 0
    bytes_served:  int   = 0


class SessionStore:
    """
    In-memory store for short-lived reveal session tokens.
    Tracks per-session chunk and byte counts for summary logging.
    """

    def __init__(self) -> None:
        self._store: dict[str, SessionToken] = {}
        self._lock  = asyncio.Lock()

    async def create(self, file_id: str) -> str:
        token   = secrets.token_urlsafe(32)
        session = SessionToken(
            token      = token,
            file_id    = file_id,
            expires_at = time.monotonic() + settings.TOKEN_TTL,
        )
        async with self._lock:
            self._store[token] = session
        return token

    async def get(self, token: str) -> Optional[SessionToken]:
        async with self._lock:
            session = self._store.get(token)
        if session is None:
            return None
        if time.monotonic() > session.expires_at:
            await self.revoke(token)
            return None
        return session

    async def record_chunk(self, token: str, byte_count: int) -> None:
        """Increment per-session chunk and byte counters."""
        async with self._lock:
            s = self._store.get(token)
            if s:
                s.chunks_served += 1
                s.bytes_served  += byte_count

    async def revoke(self, token: str) -> Optional[SessionToken]:
        """Remove token. Returns the session object if it existed, else None."""
        async with self._lock:
            return self._store.pop(token, None)

    async def sweep_expired(self) -> int:
        now = time.monotonic()
        async with self._lock:
            expired = [t for t, s in self._store.items() if now > s.expires_at]
            for t in expired:
                del self._store[t]
        return len(expired)


session_store = SessionStore()


async def _sweep_loop() -> None:
    while True:
        await asyncio.sleep(10)
        await session_store.sweep_expired()
