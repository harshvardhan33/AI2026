import asyncio
import time

from cryptography.exceptions import InvalidTag
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from app.logger import get_logger
from app.sessions import session_store
from app.storage import chunk_exists, file_exists, read_chunk_decrypted, read_manifest

router = APIRouter(prefix="/reveal", tags=["reveal"])
log    = get_logger("reveal")


@router.post("/start/{file_id}")
async def reveal_start(file_id: str) -> JSONResponse:
    """Mint a short-lived session token bound to file_id."""
    t0 = time.perf_counter()
    log.info(f"[{file_id[:8]}] Reveal start requested")

    exists = await asyncio.to_thread(file_exists, file_id)
    if not exists:
        log.warning(f"[{file_id[:8]}] Reveal start failed — file not found")
        raise HTTPException(status_code=404, detail="File not found.")

    token = await session_store.create(file_id)
    ms    = (time.perf_counter() - t0) * 1000
    log.info(f"[{file_id[:8]}] Session token minted in {ms:.1f}ms (TTL=30s)")
    return JSONResponse(content={"token": token, "ttl": 30})


@router.get("/chunk/{token}/{file_id}/{chunk_index}")
async def reveal_chunk(token: str, file_id: str, chunk_index: int) -> Response:
    """Decrypt and return a single chunk. Per-chunk logs suppressed — see reveal_end for summary."""
    session = await session_store.get(token)
    if session is None:
        log.warning(f"[{file_id[:8]}] Chunk {chunk_index} denied — invalid/expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    if session.file_id != file_id:
        log.warning(f"[{file_id[:8]}] Chunk {chunk_index} denied — token bound to different file")
        raise HTTPException(status_code=403, detail="Token not valid for this file.")

    manifest = await asyncio.to_thread(read_manifest, file_id)

    if chunk_index < 0 or chunk_index >= manifest["total_chunks"]:
        log.warning(f"[{file_id[:8]}] Chunk {chunk_index} out of range (total={manifest['total_chunks']})")
        raise HTTPException(status_code=404, detail="Chunk index out of range.")

    exists = await asyncio.to_thread(chunk_exists, file_id, chunk_index)
    if not exists:
        log.error(f"[{file_id[:8]}] Chunk {chunk_index} missing on disk")
        raise HTTPException(status_code=404, detail="Chunk file missing on disk.")

    try:
        t0        = time.perf_counter()
        plaintext = await asyncio.to_thread(read_chunk_decrypted, file_id, chunk_index)
        ms        = (time.perf_counter() - t0) * 1000
        # Record stats — summary logged on session end, not here
        await session_store.record_chunk(token, len(plaintext))
    except InvalidTag:
        log.error(f"[{file_id[:8]}] Chunk {chunk_index} — authentication FAILED (tampered?)")
        raise HTTPException(
            status_code=422,
            detail="Chunk authentication failed — possible data corruption or tampering.",
        )
    except OSError as exc:
        log.error(f"[{file_id[:8]}] Chunk {chunk_index} — storage error: {exc}")
        raise HTTPException(status_code=500, detail=f"Storage error: {exc}")

    mime = manifest.get("mime_type", "application/octet-stream")
    return Response(content=plaintext, media_type=mime)


@router.delete("/end/{token}")
async def reveal_end(token: str) -> JSONResponse:
    """Invalidate session and log a single cumulative reveal summary."""
    session = await session_store.revoke(token)

    if session:
        duration = time.monotonic() - session.started_at
        kb       = session.bytes_served / 1024
        log.info(
            f"[{session.file_id[:8]}] Reveal session closed — "
            f"{session.chunks_served} chunk(s), {kb:.1f} KB delivered "
            f"in {duration:.2f}s"
        )
    else:
        log.debug(f"Revoke called on already-expired/absent token: {token[:12]}...")

    note = None if session else "token not found (already expired or invalid)"
    return JSONResponse(content={"status": "ok", **({"note": note} if note else {})})
