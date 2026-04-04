import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.logger import get_logger
from app.storage import delete_file, file_exists, list_manifests

router = APIRouter(tags=["files"])
log    = get_logger("files")


@router.get("/files")
async def list_files() -> JSONResponse:
    """Return metadata for all stored files. Never returns key material."""
    manifests = await asyncio.to_thread(list_manifests)
    log.info(f"File list requested — {len(manifests)} file(s) returned")
    return JSONResponse(content={"files": manifests})


@router.delete("/files/{file_id}")
async def remove_file(file_id: str) -> JSONResponse:
    """Permanently delete all chunks, manifest, key, and analysis for a file."""
    log.info(f"[{file_id[:8]}] Delete requested")
    exists = await asyncio.to_thread(file_exists, file_id)
    if not exists:
        log.warning(f"[{file_id[:8]}] Delete failed — file not found")
        raise HTTPException(status_code=404, detail="File not found.")
    await asyncio.to_thread(delete_file, file_id)
    log.info(f"[{file_id[:8]}] File deleted (chunks + manifest + key)")
    return JSONResponse(content={"status": "deleted"})
