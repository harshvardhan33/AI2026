import asyncio

from cryptography.exceptions import InvalidTag
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from app.sessions import session_store
from app.storage import chunk_exists, file_exists, read_chunk_decrypted, read_manifest

router = APIRouter(prefix="/reveal", tags=["reveal"])


@router.post("/start/{file_id}")
async def reveal_start(file_id: str) -> JSONResponse:
    """
    Mint a short-lived session token for the given file.
    Token is bound to file_id — cannot be reused across files.

    Returns:
        200 { token, ttl }
        404 if file_id does not exist
    """
    exists = await asyncio.to_thread(file_exists, file_id)
    if not exists:
        raise HTTPException(status_code=404, detail="File not found.")

    token = await session_store.create(file_id)
    return JSONResponse(content={"token": token, "ttl": 30})


@router.get("/chunk/{token}/{file_id}/{chunk_index}")
async def reveal_chunk(token: str, file_id: str, chunk_index: int) -> Response:
    """
    Decrypt and return a single chunk in plaintext bytes.

    Token is validated against:
      1. Existence and TTL
      2. file_id binding (prevents cross-file token reuse)
      3. chunk_index bounds

    Returns:
        200 [raw bytes] with original mime_type
        401 if token invalid or expired
        403 if token is for a different file
        404 if file or chunk not found
        422 if GCM authentication tag fails (tampered ciphertext)
    """
    session = await session_store.get(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    if session.file_id != file_id:
        raise HTTPException(status_code=403, detail="Token not valid for this file.")

    manifest = await asyncio.to_thread(read_manifest, file_id)

    if chunk_index < 0 or chunk_index >= manifest["total_chunks"]:
        raise HTTPException(status_code=404, detail="Chunk index out of range.")

    exists = await asyncio.to_thread(chunk_exists, file_id, chunk_index)
    if not exists:
        raise HTTPException(status_code=404, detail="Chunk file missing on disk.")

    try:
        plaintext = await asyncio.to_thread(read_chunk_decrypted, file_id, chunk_index)
    except InvalidTag:
        raise HTTPException(
            status_code=422,
            detail="Chunk authentication failed — possible data corruption or tampering.",
        )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Storage error: {exc}")

    mime = manifest.get("mime_type", "application/octet-stream")
    return Response(content=plaintext, media_type=mime)


@router.delete("/end/{token}")
async def reveal_end(token: str) -> JSONResponse:
    """
    Invalidate a session token immediately.
    Idempotent — returns 200 even if token was already expired or absent.
    """
    revoked = await session_store.revoke(token)
    note = None if revoked else "token not found (already expired or invalid)"
    return JSONResponse(content={"status": "ok", **({"note": note} if note else {})})
